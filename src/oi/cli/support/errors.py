"""CLI error helpers."""

from __future__ import annotations

from typing import NoReturn

import click

from oi.infra.errors import OiError


def fail_oi(exc: OiError) -> NoReturn:
    click.echo(f"error: {exc.message}", err=True)
    raise SystemExit(1) from exc
