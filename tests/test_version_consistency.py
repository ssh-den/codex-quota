from __future__ import annotations

import re
import tomllib
from pathlib import Path

import codex_quota

ROOT = Path(__file__).resolve().parents[1]


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_project_version_matches_package_version() -> None:
    data = tomllib.loads(read_text("pyproject.toml"))

    assert data["project"]["version"] == codex_quota.__version__


def test_changelog_contains_current_version_section() -> None:
    changelog = read_text("CHANGELOG.md")
    version = re.escape(codex_quota.__version__)

    assert re.search(
        rf"^## {version} - \d{{4}}-\d{{2}}-\d{{2}}$",
        changelog,
        re.MULTILINE,
    )


def test_app_server_client_info_uses_package_version_constant() -> None:
    app_server = read_text("src/codex_quota/app_server.py")

    assert "from . import __version__" in app_server
    assert '"version": __version__' in app_server
