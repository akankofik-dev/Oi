"""``oi plugin`` — install and manage plugins."""

from __future__ import annotations

import json
from pathlib import Path

import click

from oi.infra.agents.plugins.manager import PluginManager
from oi.infra.errors import OiError
from oi.infra.utils.paths import PathLayout


@click.group()
def plugin() -> None:
    """Install and manage Oi plugins."""


def _manager() -> PluginManager:
    paths = PathLayout.from_env()
    paths.ensure_root()
    return PluginManager(plugins_dir=paths.plugins_dir, config_path=paths.config)


@plugin.command("list")
@click.pass_context
def list_plugins(ctx: click.Context) -> None:
    """List installed plugins."""
    items = _manager().list_installed()
    if ctx.obj.get("json_out"):
        click.echo(json.dumps(items, ensure_ascii=False, indent=2))
        return
    if not items:
        click.echo("No plugins installed.")
        return
    for item in items:
        if item.get("error"):
            click.echo(f"- {item['id']}: ERROR {item['error']}")
            continue
        loaded = "loaded" if item.get("loaded") else "not loaded"
        click.echo(f"- {item['id']} v{item.get('version')} ({item.get('kind')}) [{loaded}]")


@plugin.command("install")
@click.argument("source")
@click.option("--force", is_flag=True, help="Reinstall if the plugin id already exists.")
def install_plugin(source: str, force: bool) -> None:
    """Install from a local directory or ZIP URL."""
    from oi.cli.support.style import captured, echo_error, echo_success, step_list

    mgr = _manager()
    path = Path(source).expanduser()
    is_url = source.startswith("http://") or source.startswith("https://")
    if not path.is_dir() and not is_url:
        raise click.ClickException(f"not a directory or URL: {source}")

    # NOTE: plugin dep installs (pip inside oi_harness) are captured —
    # the user only sees the clean checklist, never raw installer output.
    step_label = (
        "Downloading plugin" if is_url else "Copying plugin files"
    )
    with step_list("Installing plugin") as steps:
        steps.begin(step_label)
        try:
            with captured():
                if path.is_dir():
                    loaded = mgr.install_path(path, force=force)
                else:
                    loaded = mgr.install_url(source, force=force)
        except OiError as exc:
            steps.fail(step_label, "install failed")
            echo_error(exc.message)
            raise SystemExit(1)
        steps.succeed(step_label)

    echo_success(f"Installed plugin {loaded.manifest.id} v{loaded.manifest.version}")
    click.echo(
        "Note: if oi run is already running, call POST /api/plugins/reload "
        "(Admin → Plugins → Reload) or restart the server so status becomes loaded.",
    )


@plugin.command("uninstall")
@click.argument("plugin_id")
def uninstall_plugin(plugin_id: str) -> None:
    """Remove an installed plugin."""
    _manager().uninstall(plugin_id)
    click.echo(f"Uninstalled {plugin_id}")


@plugin.command("reload")
def reload_plugins() -> None:
    """Reload plugins from disk (offline; restart ``oi run`` to apply to agents)."""
    loaded = _manager().load_installed(install_deps=False)
    click.echo(f"Reloaded {len(loaded)} plugin(s). Restart oi run if the server is running.")
