"""oi version command."""

from __future__ import annotations

import click

from oi.cli.support.style import echo_banner


def _get_version() -> str:
    try:
        from importlib.metadata import version as _v

        return _v("oi")
    except Exception:
        return "unknown"


@click.command("version")
def version() -> None:
    """Show the installed oi version."""
    echo_banner()
    click.echo(f"Oi v{_get_version()}")
