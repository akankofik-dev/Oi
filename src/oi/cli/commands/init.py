"""`oi init` — bootstrap a fresh Oi install (DB + first admin)."""

from __future__ import annotations

import shutil

import click

from oi.cli.support.style import echo_error, echo_success, step_list


@click.command("init")
@click.option(
    "--admin-username",
    envvar="OI_ADMIN_USERNAME",
    default=None,
    help="First admin username (or set OI_ADMIN_USERNAME).",
)
@click.option(
    "--admin-password",
    envvar="OI_ADMIN_PASSWORD",
    default=None,
    help="First admin password (or set OI_ADMIN_PASSWORD).",
)
@click.option(
    "--admin-display-name",
    envvar="OI_ADMIN_DISPLAY_NAME",
    default=None,
    help="Optional display name for the admin user.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Wipe existing ~/.oi contents before bootstrapping.",
)
@click.option(
    "--yes",
    "non_interactive",
    is_flag=True,
    default=False,
    help="Skip all interactive prompts.",
)
@click.option(
    "--skip-admin",
    is_flag=True,
    default=False,
    help="Skip creating the first admin user. The setup wizard in the web UI "
    "will create it on first visit (default Oi behaviour).",
)
def init(
    admin_username: str | None,
    admin_password: str | None,
    admin_display_name: str | None,
    force: bool,
    non_interactive: bool,
    skip_admin: bool,
) -> None:
    """Bootstrap an Oi server (~/.oi dir, DB migrations, first admin)."""
    from oi.config import load_config
    from oi.infra.agents.plugins.manager import PluginManager
    from oi.infra.db.factory import open_database
    from oi.infra.db.migrate import run_migrations
    from oi.infra.db.repos.users import UserRepo
    from oi.infra.errors import OiError
    from oi.infra.users.password import hash_password, validate_password_policy
    from oi.infra.utils.env_file import apply_env_file, env_file_path
    from oi.infra.utils.paths import PathLayout

    paths = PathLayout.from_env()
    home = paths.root

    # Sidecar files (oi-login.txt, NAS share metadata) must not block first
    # bootstrap. Only an existing control-plane DB counts as an install.
    has_db = (home / "oi.db").is_file()
    if home.exists() and any(home.iterdir()):
        if has_db and not force:
            echo_error(
                f"{home} already exists and is not empty. Use --force to reset."
            )
            raise SystemExit(1)
        if force:
            if not non_interactive:
                from oi.cli.support import prompts as _prompts

                if not _prompts.confirm(
                    f"Wipe {home}? This deletes ALL Oi state.", default=False
                ):
                    echo_error("aborted")
                    raise SystemExit(1)
            shutil.rmtree(home)

    # Interactive input is collected BEFORE the checklist, so no prompt
    # ever appears while a step is pulsing.
    username = admin_username
    password = admin_password
    display_name = admin_display_name
    if not non_interactive:
        from oi.cli.support import prompts as _prompts

        if not username:
            username = _prompts.text("Admin username:")
        if not password:
            password = _prompts.password("Admin password:")
        if display_name is None:
            display_name = _prompts.text("Display name (optional):", default="") or None

    plugin_mgr = PluginManager(plugins_dir=paths.plugins_dir, config_path=paths.config)
    with step_list("Bootstrapping Oi") as steps:
        steps.run("Preparing directories", paths.ensure_root)
        steps.run("Seeding bundled plugins", plugin_mgr.seed_bundled)
        steps.run(
            "Applying environment file",
            lambda: apply_env_file(env_file_path(paths.root)),
        )
        config = steps.run("Loading configuration", lambda: load_config(paths.config))
        db = steps.run("Opening database", lambda: open_database(config, paths))
        try:
            steps.run(
                "Running database migrations", lambda: run_migrations(db)
            )

            if not username and not skip_admin:
                echo_error("admin username is required")
                raise SystemExit(1)
            if not skip_admin:
                try:
                    validate_password_policy(password or "")
                except OiError as exc:
                    echo_error(exc.message)
                    raise SystemExit(1)
            if skip_admin:
                steps.run(
                    "Skipping admin user (setup wizard in web UI will create it)",
                    lambda: None,
                )
            else:
                steps.run(
                    "Creating admin user",
                    lambda: UserRepo(db).create(
                        username=username,
                        password_hash=hash_password(password or ""),
                        role="admin",
                        display_name=display_name,
                    ),
                )
        finally:
            db.close()

    echo_success(f"Oi bootstrapped at {home}")
    click.echo(f"   admin user: {username}")
    click.echo("   next: `oi run` (optional: `oi agent use <id>` to pin default agent)")
