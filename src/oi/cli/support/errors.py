"""CLI error helpers."""

from __future__ import annotations

from typing import NoReturn

import click

from oi.cli.support.style import error as _style_error
from oi.infra.errors import OiError


def fail_oi(exc: OiError) -> NoReturn:
    click.echo(_style_error(f"error: {exc.message}"), err=True)
    raise SystemExit(1) from exc
