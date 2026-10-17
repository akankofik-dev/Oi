"""tests/unit/test_shared.py"""

from __future__ import annotations

from pathlib import Path

from oi.config import OiConfig
from oi.infra.db.migrate import run_migrations
from oi.infra.db.pool import SqlitePool
from oi.infra.db.repos.sso import SsoRepo
from oi.infra.db.services import SharedServices, build_shared_services
from oi.infra.utils.paths import PathLayout


def test_build_shared_services(tmp_path: Path):
    cfg = OiConfig()
    paths = PathLayout(tmp_path / ".oi")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=cfg)
    assert isinstance(services, SharedServices)
    assert services.db is db
    assert services.paths is paths
    assert services.config is cfg
    # all repos resolved
    assert services.user_repo.count() == 0
    assert isinstance(services.sso_repo, SsoRepo)
