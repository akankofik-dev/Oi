"""oi version command."""

from __future__ import annotations

import click


@click.command("version")
def version() -> None:
    """Show the installed oi version."""
    try:
        from importlib.metadata import version as _v

        v = _v("oi")
    except Exception:
        v = "unknown"
    click.echo(f"oi v{v}")
