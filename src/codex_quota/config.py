from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .filesystem import ensure_private_dir
from .models import AppConfig
from .paths import default_paths

CONFIG_KEYS = {"profiles_dir", "codex_bin", "default_model", "reasoning_effort", "refresh_seconds"}


def create_default_config() -> AppConfig:
    paths = default_paths()
    return AppConfig(profiles_dir=paths.profiles_dir)


def _as_path(value: object, fallback: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        return fallback
    return Path(value).expanduser()


def load_config(path: Path | None = None) -> AppConfig:
    paths = default_paths()
    config_file = path or paths.config_file
    if not config_file.exists():
        return create_default_config()

    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise ConfigError(f"Malformed config JSON: {config_file}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read config: {config_file}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Config must be a JSON object: {config_file}")

    refresh = data.get("refresh_seconds", 30.0)
    try:
        refresh_seconds = float(refresh)
    except (TypeError, ValueError) as exc:
        raise ConfigError("config refresh_seconds must be a number") from exc

    extra = {key: value for key, value in data.items() if key not in CONFIG_KEYS}
    return AppConfig(
        profiles_dir=_as_path(data.get("profiles_dir"), paths.profiles_dir),
        codex_bin=str(data.get("codex_bin", "codex")),
        default_model=str(data.get("default_model", "gpt-5.4-mini")),
        reasoning_effort=str(data.get("reasoning_effort", "low")),
        refresh_seconds=refresh_seconds,
        extra=extra,
    )


def config_to_json(config: AppConfig, *, preserve_extra: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = dict(config.extra) if preserve_extra else {}
    data.update(
        {
            "profiles_dir": str(config.profiles_dir),
            "codex_bin": config.codex_bin,
            "default_model": config.default_model,
            "reasoning_effort": config.reasoning_effort,
            "refresh_seconds": config.refresh_seconds,
        }
    )
    return data


def save_config(
    config: AppConfig,
    path: Path | None = None,
    *,
    preserve_extra: bool = True,
) -> Path:
    paths = default_paths()
    config_file = path or paths.config_file
    ensure_private_dir(config_file.parent, parents=True, exist_ok=True)
    data = config_to_json(config, preserve_extra=preserve_extra)
    try:
        config_file.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ConfigError(f"Could not write config: {config_file}: {exc}") from exc
    return config_file


def ensure_config(path: Path | None = None, *, overwrite: bool = False) -> AppConfig:
    paths = default_paths()
    config_file = path or paths.config_file
    ensure_private_dir(config_file.parent, parents=True, exist_ok=True)
    if config_file.exists() and not overwrite:
        return load_config(config_file)
    config = create_default_config()
    save_config(config, config_file, preserve_extra=False)
    return config
