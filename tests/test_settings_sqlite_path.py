from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine.url import make_url

from api.paths import repo_root


def test_relative_sqlite_url_anchored_to_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///./from_env_relative.db")
    from api import config as config_mod

    config_mod.get_settings.cache_clear()
    url = config_mod.get_settings().database_url
    expected = str((repo_root() / "from_env_relative.db").resolve())
    assert make_url(url).database == expected
    config_mod.get_settings.cache_clear()
