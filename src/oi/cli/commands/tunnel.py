"""`oi tunnel` — expose the local Oi server to the internet via a Cloudflare Quick Tunnel.

One command, no account, no open ports::

    oi tunnel

Prints a public ``https://*.trycloudflare.com`` URL that forwards to the
local Oi server. Runs in the foreground — press Ctrl+C to stop.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import socket
import subprocess
import time

import click

from oi.cli.support import style
from oi.cli.support.style import dim, echo_banner, highlight, step_list

#: Pattern matching the public URL cloudflared prints in its Quick Tunnel banner.
#: The ``(?!api\.)`` guard excludes Cloudflare's own API endpoint
#: (``https://api.trycloudflare.com/tunnel``), which appears in error lines
#: and must never be mistaken for the public tunnel URL.
_QUICK_TUNNEL_URL_RE = re.compile(r"https://(?!api\.)[a-zA-Z0-9-]+\.trycloudflare\.com")

#: Marker line printed right before the URL banner — only a URL seen after
#: this line is a real, working tunnel address.
_TUNNEL_CREATED_MARKER = "quick Tunnel has been created"

#: How long to wait for cloudflared to hand us a public URL.
_URL_TIMEOUT_SECONDS = 45

#: Install hints per platform when ``cloudflared`` is missing.
_INSTALL_HINTS = (
    "Install cloudflared first:\n"
    "  Ubuntu/Debian:  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/\n"
    "  macOS:          brew install cloudflared\n"
    "  Windows:        winget install cloudflare.cloudflared"
)


def _resolve_local(host: str | None, port: int | None) -> tuple[str, int]:
    """Resolve the local Oi address: CLI flags > env > config.json > defaults.

    Reuses ``oi run``'s own resolution so the tunnel always points at the
    address Oi actually listens on.
    """
    # Local import: keeps this module light and avoids any import cycle
    # with the sibling command module.
    from oi.cli.commands.run import resolve_bind

    resolved_host, resolved_port = resolve_bind(host, port)
    return resolved_host or "127.0.0.1", resolved_port or 8088


def _check_cloudflared() -> str:
    """Return the cloudflared binary path, or raise if it is not installed."""
    binary = shutil.which("cloudflared")
    if not binary:
        raise click.ClickException(
            style.error("cloudflared is not installed") + "\n" + dim(_INSTALL_HINTS)
        )
    return binary


def _check_local_server(host: str, port: int) -> bool:
    """Best-effort check that Oi is reachable locally (non-fatal)."""
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _spawn_cloudflared(binary: str, local_url: str) -> subprocess.Popen:
    """Start ``cloudflared tunnel --url <local_url>`` with piped stderr."""
    try:
        return subprocess.Popen(
            [binary, "tunnel", "--url", local_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        raise click.ClickException(style.error(f"could not start cloudflared: {exc}")) from exc


def _wait_for_url(proc: subprocess.Popen) -> str:
    """Read cloudflared's stderr until the public URL appears.

    Raises a ClickException if cloudflared exits early or the URL never
    arrives within the timeout.
    """
    assert proc.stderr is not None
    deadline = time.monotonic() + _URL_TIMEOUT_SECONDS
    created_seen = False
    recent_lines: list[str] = []  # last few lines, for a useful error hint
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            hint = "cloudflared exited unexpectedly"
            for past in reversed(recent_lines):
                if past.strip():
                    hint = past.strip()
                    break
            raise click.ClickException(style.error(f"tunnel failed to start — {hint}"))
        line = proc.stderr.readline()
        if not line:
            time.sleep(0.1)
            continue
        recent_lines.append(line)
        del recent_lines[:-5]
        if _TUNNEL_CREATED_MARKER in line:
            created_seen = True
        # Only trust a URL that arrives after the "has been created" banner;
        # error lines can mention trycloudflare.com hosts too.
        if created_seen:
            match = _QUICK_TUNNEL_URL_RE.search(line)
            if match:
                return match.group(0)
    proc.terminate()
    raise click.ClickException(style.error("timed out waiting for the public URL from cloudflared"))


def _print_active_panel(public_url: str, local_url: str) -> None:
    """Print the cool "tunnel is live" panel."""
    click.echo()
    click.echo(click.style("\U0001f310 Oi Tunnel Active!", fg=style.fg("success"), bold=True))
    click.echo()
    click.echo(
        f"  {highlight('Public URL:')}  {click.style(public_url, fg=style.fg('active'), bold=True)}"
    )
    click.echo(f"  {highlight('Local:')}       {dim(local_url)}")
    click.echo()
    click.echo(dim("  Press Ctrl+C to stop"))
    click.echo()


def _relay_logs(proc: subprocess.Popen) -> None:
    """Forward cloudflared's remaining stderr (dimmed) until it exits."""
    assert proc.stderr is not None
    try:
        for line in proc.stderr:
            stripped = line.rstrip()
            if stripped:
                click.echo(dim(f"  {stripped}"), err=True)
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


@click.command("tunnel")
@click.option("--host", default=None, help="Local Oi host (default: same as oi run).")
@click.option(
    "--port",
    default=None,
    type=click.IntRange(0, 65535),
    help="Local Oi port (default: same as oi run).",
)
def tunnel(host: str | None, port: int | None) -> None:
    """Expose Oi to the internet via a Cloudflare Quick Tunnel.

    Prints a public https://*.trycloudflare.com URL. No account, no
    open ports. Runs in the foreground — Ctrl+C stops it.
    """
    echo_banner()
    local_host, local_port = _resolve_local(host, port)
    local_url = f"http://{local_host}:{local_port}"

    with step_list("Starting Oi tunnel") as steps:
        binary = steps.run("Checking cloudflared", _check_cloudflared)

        if not _check_local_server(local_host, local_port):
            steps.begin("Checking Oi server")
            steps.succeed(
                "Checking Oi server",
                detail="not reachable — start it with `oi run` first",
            )
            click.echo(
                style.warning(
                    f"Oi doesn't seem to be running on {local_url} — "
                    "start it with `oi run` first, or the tunnel will serve nothing."
                ),
                err=True,
            )
        else:
            steps.run("Checking Oi server", lambda: True)

        steps.begin("Starting tunnel")
        proc = _spawn_cloudflared(binary, local_url)
        try:
            public_url = _wait_for_url(proc)
        except click.ClickException:
            steps.fail("Starting tunnel")
            with contextlib.suppress(OSError):
                proc.terminate()
            raise
        steps.succeed("Starting tunnel")

    _print_active_panel(public_url, local_url)
    _relay_logs(proc)
    click.echo(style.success("Tunnel closed."))


# Keep module importable even on interpreters without ``sys.stderr`` quirks;
# nothing to do here — the guard below is intentional documentation.
