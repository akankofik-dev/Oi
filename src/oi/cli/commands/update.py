"""`oi update` — self-upgrade via pip or uv."""

from __future__ import annotations

import click

from oi.cli.support.style import echo_error, echo_success, step_list
from oi.infra.setup.self_update import (
    fetch_pypi_info,
    get_editable_path,
    get_local_version,
    is_newer,
    is_prerelease,
    resolve_venv_python,
    run_upgrade,
)


@click.command("update")
@click.option("--check", is_flag=True, default=False, help="Only check, do not install.")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose installer output.")
@click.option(
    "--allow-prerelease",
    "allow_prerelease",
    is_flag=True,
    default=False,
    help="Include and allow installing pre-releases (alpha / beta / rc / dev).",
)
def update(check: bool, yes: bool, verbose: bool, allow_prerelease: bool) -> None:
    """Check for and install a newer Oi release."""
    # NOTE: installer output is never shown raw — run_upgrade() already
    # captures pip/uv stdout+stderr unless --verbose is passed. The user
    # only ever sees the clean per-step checklist below.
    with step_list("Updating Oi") as steps:
        current = steps.run("Reading installed version", get_local_version)
        info = steps.run("Checking GitHub Releases", fetch_pypi_info)
        if info is None:
            echo_error(
                "could not reach GitHub Releases — "
                "check your network or proxy settings and retry"
            )
            raise SystemExit(1)
        latest = info.version if allow_prerelease else info.latest_stable
        if latest is None:
            echo_error(
                "no stable release available "
                "(pass --allow-prerelease to include pre-releases)"
            )
            raise SystemExit(1)
        if not is_newer(latest, current):
            steps.run(f"Already up to date (v{current})", None)
            return
        if check:
            steps.run(f"Update available: v{current} → v{latest}", None)
            return

        editable_path = get_editable_path()
        if editable_path:
            echo_error(
                f"This installation is running from source ({editable_path})."
            )
            echo_error(f"To upgrade: cd {editable_path} && git pull")
            raise SystemExit(1)

        if not yes:
            # Asked while no step is active, so the prompt renders cleanly.
            click.confirm(f"Upgrade oi from {current} to {latest}?", abort=True)

        if verbose:
            # Debug escape hatch only — never shown in normal runs.
            click.echo(f"target python: {resolve_venv_python()}", err=True)

        mirror_errors: list[str] = []

        def _do_upgrade():
            res = run_upgrade(
                verbose=verbose,
                allow_prerelease=is_prerelease(latest),
                version=latest,
            )
            if not res.success:
                # Raise so the step is marked ✗ with a simple reason.
                mirror_errors.extend(res.mirror_errors)
                raise RuntimeError(res.error or "unknown error")
            return res

        try:
            result = steps.run(f"Installing oi v{latest}", _do_upgrade)
        except RuntimeError as exc:
            echo_error(f"upgrade failed: {exc}")
            for err in mirror_errors:
                echo_error(f"  {err}")
            raise SystemExit(1)

    echo_success(result.message or "upgrade complete")
    if result.installed_version:
        echo_success(f"installed: {result.installed_version}")
