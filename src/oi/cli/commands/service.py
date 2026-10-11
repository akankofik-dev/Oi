"""`oi service` — install and manage the Oi system service."""

from __future__ import annotations

from typing import NoReturn

import click

from oi.infra.errors import OiError
from oi.infra.setup.service import (
    DEFAULT_HEALTH_ATTEMPTS,
    DEFAULT_HEALTH_DELAY_SECONDS,
    SERVICE_NAME,
    ServiceRuntime,
    ServiceScope,
    ServiceStatus,
    _cmd_ok,
    _systemd_enable_linger,
    _systemd_run,
    _write_unit,
    build_runtime,
    collect_service_status,
    ensure_nofile_dropin,
    install_service,
    is_service_installed,
    launchd_domain,
    persist_bind_options,
    restart_service,
    start_service,
    stop_service,
    unit_path,
)


@click.group()
def service() -> None:
    """Manage the Oi system service (systemd on Linux, launchd on macOS)."""


def _runtime(host: str | None, port: int | None, scope: ServiceScope | None) -> ServiceRuntime:
    try:
        return build_runtime(host=host, port=port, scope=scope)
    except (FileNotFoundError, RuntimeError) as exc:
        click.echo(f"error: {exc}", err=True)
        raise SystemExit(1) from exc


def _fail(exc: Exception) -> NoReturn:
    click.echo(f"error: {exc}", err=True)
    raise SystemExit(1) from exc


def _resolve_scope(value: str) -> ServiceScope | None:
    """Convert a `--scope` CLI value into the value `build_runtime` expects.

    Returns ``None`` to mean "auto-detect"; ``"user"`` / ``"system"`` for
    explicit scopes.  Click-level validation already filters out anything
    other than these three tokens, so this raises on a programming error.
    """
    if value == "auto":
        return None
    if value not in ("user", "system"):
        raise click.BadParameter(f"scope must be 'user', 'system', or 'auto' (got {value!r})")
    return value  # type: ignore[return-value]


def _health_failure_hint(runtime: ServiceRuntime) -> str:
    log_path = runtime.home / "logs" / "oi.log"
    if runtime.mode == "systemd":
        journal = (
            "journalctl --user -u oi -n 80 --no-pager"
            if runtime.scope == "user"
            else "journalctl -u oi -n 80 --no-pager"
        )
        return f"hint: inspect logs with `{journal}` or `tail -n 80 {log_path}`"
    return (
        f"hint: inspect logs with `tail -n 80 {log_path}` "
        f"or `launchctl print {launchd_domain(runtime.scope)}`"
    )


def _describe_runtime(runtime: ServiceRuntime) -> str:
    path = unit_path(runtime.mode, scope=runtime.scope, run_as_user=runtime.run_as_user)
    if runtime.mode == "systemd":
        return f"scope: {runtime.scope}, unit: {path}"
    return f"scope: {runtime.scope}, plist: {path}, domain: {launchd_domain(runtime.scope)}"


def _echo_health(status: ServiceStatus, *, warn_only: bool, runtime: ServiceRuntime) -> None:
    from oi.cli.support.style import echo_error, echo_success

    if status.health_ok:
        echo_success(f"health: OK {status.health_detail}")
        return
    if status.health_detail is None:
        return
    echo_error(f"health: unreachable ({status.health_detail})")
    click.echo(_health_failure_hint(runtime), err=True)
    if not warn_only:
        raise SystemExit(1)


def _echo_summary_for(runtime: ServiceRuntime, *, warn_health: bool) -> None:
    info = collect_service_status(
        runtime,
        check_health=True,
        health_retries=DEFAULT_HEALTH_ATTEMPTS,
        health_delay_seconds=DEFAULT_HEALTH_DELAY_SECONDS,
    )
    click.echo(_describe_runtime(runtime))
    click.echo(f"service: {info.mode} active={info.active}")
    _echo_health(info, warn_only=warn_health, runtime=runtime)


def _install_write_files(runtime: ServiceRuntime, *, force: bool) -> bool:
    """Write the systemd unit + LimitNOFILE drop-in. Returns True if changed.

    Mirrors the file-writing half of ``install_service`` so the CLI can show
    it as its own step.  Couples to ``oi.infra.setup.service`` internals —
    keep in sync with ``install_service``.
    """
    was_installed = is_service_installed(
        runtime.mode, scope=runtime.scope, run_as_user=runtime.run_as_user
    )
    write_unit = force or not was_installed
    if write_unit:
        _write_unit(runtime)
    wrote_dropin = ensure_nofile_dropin(runtime)
    return write_unit or wrote_dropin


def _install_daemon_reload(runtime: ServiceRuntime) -> None:
    """``systemctl daemon-reload`` — pick up the new/changed unit."""
    proc = _systemd_run(runtime, "daemon-reload")
    _cmd_ok(proc, "daemon-reload failed")


def _install_enable(runtime: ServiceRuntime) -> None:
    """``systemctl enable oi`` — auto-start on boot (+ linger for user scope)."""
    proc = _systemd_run(runtime, "enable", SERVICE_NAME)
    _cmd_ok(proc, "systemctl enable failed")
    _systemd_enable_linger(runtime)


@service.command("start")
@click.option("--host", default=None, help="Bind host saved to config.json before install.")
@click.option(
    "--port", default=None, type=int, help="Bind port saved to config.json before install."
)
@click.option(
    "--force-install",
    is_flag=True,
    default=False,
    help="Rewrite the unit file even if it already matches.",
)
@click.option(
    "--scope",
    default="auto",
    type=click.Choice(["user", "system", "auto"], case_sensitive=False),
    show_default=True,
    help=(
        "Install scope.  Like LightClaw: root → system unit (/etc/systemd/system); "
        "other users → user unit (~/.config/systemd/user).  ``sudo`` from a normal "
        "user still installs a user unit for that user."
    ),
)
def start(host: str | None, port: int | None, force_install: bool, scope: str) -> None:
    """Install if needed, ensure the NOFILE drop-in, then start the service."""
    runtime = _runtime(host, port, _resolve_scope(scope))
    try:
        if host is not None or port is not None:
            persist_bind_options(runtime.home, host=host, port=port)
            runtime = _runtime(host, port, _resolve_scope(scope))
        wrote = install_service(runtime, force=force_install)
        start_service(runtime, apply_unit=wrote)
    except (RuntimeError, OiError) as exc:
        _fail(exc)
    _echo_summary_for(runtime, warn_health=True)


@service.command("install")
@click.option("--host", default=None, help="Bind host saved to config.json before install.")
@click.option(
    "--port", default=None, type=int, help="Bind port saved to config.json before install."
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Rewrite the unit file even if it already exists.",
)
@click.option(
    "--no-start",
    is_flag=True,
    default=False,
    help="Install and enable auto-start, but do not start the service now.",
)
@click.option(
    "--scope",
    default="auto",
    type=click.Choice(["user", "system", "auto"], case_sensitive=False),
    show_default=True,
    help=(
        "Install scope.  root → system unit (/etc/systemd/system); "
        "other users → user unit (~/.config/systemd/user)."
    ),
)
def install(host: str | None, port: int | None, force: bool, no_start: bool, scope: str) -> None:
    """Install the service, enable auto-start on boot, and start Oi."""
    from oi.cli.support.style import step_list

    runtime = _runtime(host, port, _resolve_scope(scope))
    try:
        if host is not None or port is not None:
            persist_bind_options(runtime.home, host=host, port=port)
            runtime = _runtime(host, port, _resolve_scope(scope))
        with step_list("Installing Oi service") as steps:
            if runtime.mode == "systemd":
                wrote = steps.run(
                    "Creating service file",
                    lambda: _install_write_files(runtime, force=force),
                )
                steps.run("Reloading systemd", lambda: _install_daemon_reload(runtime))
                steps.run("Enabling auto-start", lambda: _install_enable(runtime))
            else:
                # launchd (macOS): keep the existing all-in-one installer.
                wrote = steps.run(
                    "Creating service file",
                    lambda: install_service(runtime, force=force),
                )
            if no_start:
                steps.run("Starting service (skipped)", lambda: None)
            else:
                steps.run(
                    "Starting service",
                    lambda: start_service(runtime, apply_unit=wrote),
                )
    except (RuntimeError, OiError) as exc:
        _fail(exc)
    _echo_summary_for(runtime, warn_health=True)


@service.command("stop")
@click.option(
    "--scope",
    default="auto",
    type=click.Choice(["user", "system", "auto"], case_sensitive=False),
    show_default=True,
    help="Stop scope.  Must match the scope the service was installed under.",
)
def stop(scope: str) -> None:
    """Stop the system service."""
    runtime = _runtime(None, None, _resolve_scope(scope))
    try:
        stop_service(runtime)
    except RuntimeError as exc:
        _fail(exc)
    info = collect_service_status(runtime, check_health=False)
    click.echo(_describe_runtime(runtime))
    click.echo(f"service: {info.mode} active={info.active}")


@service.command("restart")
@click.option(
    "--scope",
    default="auto",
    type=click.Choice(["user", "system", "auto"], case_sensitive=False),
    show_default=True,
    help="Restart scope.  Must match the scope the service was installed under.",
)
def restart(scope: str) -> None:
    """Restart the system service. Adds a LimitNOFILE drop-in if missing."""
    runtime = _runtime(None, None, _resolve_scope(scope))
    try:
        restart_service(runtime)
    except RuntimeError as exc:
        _fail(exc)
    _echo_summary_for(runtime, warn_health=True)


@service.command("status")
@click.option("--host", default=None, help="Health-check host (defaults from config.json).")
@click.option(
    "--port", default=None, type=int, help="Health-check port (defaults from config.json)."
)
@click.option(
    "--scope",
    default="auto",
    type=click.Choice(["user", "system", "auto"], case_sensitive=False),
    show_default=True,
    help="Service scope to inspect (must match the installed scope).",
)
@click.option("--no-health", is_flag=True, default=False, help="Skip HTTP health probe.")
def status(host: str | None, port: int | None, scope: str, no_health: bool) -> None:
    """Show system service and HTTP health status."""
    runtime = _runtime(host, port, _resolve_scope(scope))
    info = collect_service_status(
        runtime,
        check_health=not no_health,
        health_retries=DEFAULT_HEALTH_ATTEMPTS,
        health_delay_seconds=DEFAULT_HEALTH_DELAY_SECONDS,
    )
    if info.mode is None:
        click.echo(f"error: {info.detail}", err=True)
        raise SystemExit(1)
    click.echo(f"mode:      {info.mode}")
    click.echo(_describe_runtime(runtime))
    click.echo(f"installed: {info.installed}")
    click.echo(f"active:    {info.active}")
    if info.enabled is not None:
        click.echo(f"enabled:   {info.enabled}")
    if info.detail:
        click.echo(info.detail)
    if not no_health:
        _echo_health(info, warn_only=False, runtime=runtime)
