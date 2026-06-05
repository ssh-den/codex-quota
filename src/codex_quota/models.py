from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Paths:
    config_dir: Path
    config_file: Path
    profiles_dir: Path


@dataclass(frozen=True)
class Profile:
    name: str
    codex_home: Path

    @property
    def auth_file(self) -> Path:
        return self.codex_home / "auth.json"

    @property
    def config_file(self) -> Path:
        return self.codex_home / "config.toml"

    @property
    def has_auth(self) -> bool:
        return self.auth_file.is_file()

    @property
    def has_config(self) -> bool:
        return self.config_file.is_file()


@dataclass(frozen=True)
class AppConfig:
    profiles_dir: Path
    codex_bin: str = "codex"
    default_model: str = "gpt-5.4-mini"
    reasoning_effort: str = "low"
    refresh_seconds: float = 30.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountInfo:
    account: dict[str, Any] | None
    requires_openai_auth: bool
    raw: dict[str, Any]


@dataclass(frozen=True)
class WindowLimit:
    used_percent: int
    window_duration_mins: int
    resets_at: int | None
    raw: dict[str, Any]

    @property
    def remaining_percent(self) -> int:
        return max(0, 100 - int(self.used_percent))


@dataclass(frozen=True)
class RateLimits:
    primary: WindowLimit | None
    secondary: WindowLimit | None
    plan_type: str | None
    rate_limit_reached_type: str | None
    credits: dict[str, Any]
    raw: dict[str, Any]

    @property
    def is_blocked(self) -> bool:
        return self.rate_limit_reached_type is not None


@dataclass(frozen=True)
class ProfileStatus:
    profile: Profile
    rate_limits: RateLimits | None = None
    auth_ok: bool = False
    codex_ok: bool = True
    error: str | None = None
    status: str | None = None

    @property
    def ok(self) -> bool:
        return (
            self.status != "AUTH_REQUIRED"
            and self.error is None
            and self.codex_ok
            and self.auth_ok
            and self.rate_limits is not None
            and not self.rate_limits.is_blocked
        )
