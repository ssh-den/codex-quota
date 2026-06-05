from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .filesystem import ensure_private_dir
from .models import AppConfig
from .paths import default_paths

CONFIG_KEYS = {
    "profiles_dir",
    "codex_bin",
    "default_model",
    "reasoning_effort",
    "refresh_seconds",
}
AUTH_REFRESH_KEY = "auth_refresh"
AUTH_REFRESH_INTERVAL = timedelta(hours=4)


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


def auth_refresh_map(config: AppConfig) -> dict[str, str]:
    value = config.extra.get(AUTH_REFRESH_KEY)
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def parse_auth_refresh_timestamp(value: str) -> datetime | None:
    if not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def format_auth_refresh_timestamp(value: datetime) -> str:
    return (
        value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def get_last_auth_refresh(config: AppConfig, profile_name: str) -> datetime | None:
    value = auth_refresh_map(config).get(profile_name)
    if value is None:
        return None
    return parse_auth_refresh_timestamp(value)


def auth_refresh_due(
    config: AppConfig,
    profile_name: str,
    *,
    now: datetime | None = None,
    interval: timedelta = AUTH_REFRESH_INTERVAL,
) -> bool:
    current_time = now or datetime.now(UTC)
    last_refresh = get_last_auth_refresh(config, profile_name)
    if last_refresh is None:
        return True
    if last_refresh > current_time:
        return True
    return current_time - last_refresh >= interval


def with_auth_refresh(
    config: AppConfig,
    profile_name: str,
    refreshed_at: datetime,
) -> AppConfig:
    extra = dict(config.extra)
    existing = extra.get(AUTH_REFRESH_KEY)
    refresh_data = dict(existing) if isinstance(existing, dict) else {}
    refresh_data[profile_name] = format_auth_refresh_timestamp(refreshed_at)
    extra[AUTH_REFRESH_KEY] = refresh_data
    return replace(config, extra=extra)


def persist_auth_refresh(
    config: AppConfig,
    profile_name: str,
    refreshed_at: datetime,
    *,
    path: Path | None = None,
) -> AppConfig:
    updated = with_auth_refresh(config, profile_name, refreshed_at)
    save_config(updated, path=path)
    return updated


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
