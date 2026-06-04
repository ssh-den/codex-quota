from __future__ import annotations

import os
from pathlib import Path

PRIVATE_DIR_MODE = 0o700


def _missing_directories(path: Path) -> list[Path]:
    missing: list[Path] = []
    current = path

    while not current.exists():
        missing.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent

    missing.reverse()
    return missing


def _chmod_private(path: Path) -> None:
    if os.name != "posix":
        return
    path.chmod(PRIVATE_DIR_MODE)


def ensure_private_dir(
    path: Path,
    *,
    parents: bool = False,
    exist_ok: bool = True,
) -> Path:
    targets = _missing_directories(path)
    path.mkdir(mode=PRIVATE_DIR_MODE, parents=parents, exist_ok=exist_ok)

    if not targets or targets[-1] != path:
        targets.append(path)

    for directory in targets:
        _chmod_private(directory)

    return path
