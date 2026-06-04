from __future__ import annotations

from datetime import datetime

from rich import box
from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import Profile, ProfileStatus, RateLimits


def fmt_reset(ts: int | None) -> str:
    if not ts:
        return "unknown"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def fmt_refreshed_at(value: datetime | None) -> str:
    if value is None:
        return "Not refreshed yet"
    return f"Refreshed at {value.strftime('%H:%M %d.%m.%Y')}"


def status_text(limits: RateLimits | None, auth_ok: bool, error: str | None = None) -> str:
    if error and error != "auth_required":
        return f"error: {error}"
    if not auth_ok:
        return "auth_required"
    if not limits:
        return "unknown"
    return limits.rate_limit_reached_type or "available"


def _percent(value: int | float | None) -> str:
    if value is None:
        return "?"
    return f"{round(value)}%"


def _status_style(text: str) -> str:
    if text == "available":
        return "green"
    if text == "auth_required":
        return "yellow"
    if text.startswith("error:") or text not in {"unknown", "available"}:
        return "red"
    return "dim"


def render_profile_table(profiles: list[Profile]) -> Table:
    table = Table(title="Codex Profiles", box=box.ROUNDED, expand=True)
    table.add_column("Profile", no_wrap=True)
    table.add_column("Path", overflow="fold")
    table.add_column("auth.json", justify="center", no_wrap=True)
    table.add_column("config.toml", justify="center", no_wrap=True)
    for profile in profiles:
        table.add_row(
            profile.name,
            str(profile.codex_home),
            "yes" if profile.has_auth else "no",
            "yes" if profile.has_config else "no",
        )
    return table


def render_status_table(statuses: list[ProfileStatus]) -> Table:
    table = Table(title="Codex Usage", box=box.ROUNDED, expand=True, show_lines=False)
    table.add_column("Profile", no_wrap=True)
    table.add_column("5h left", justify="right", no_wrap=True)
    table.add_column("Week left", justify="right", no_wrap=True)
    table.add_column("Plan", no_wrap=True)
    table.add_column("Status", overflow="fold")
    table.add_column("5h reset", no_wrap=True)
    table.add_column("Week reset", no_wrap=True)

    for item in statuses:
        limits = item.rate_limits
        primary = limits.primary if limits else None
        secondary = limits.secondary if limits else None
        current_status = status_text(limits, item.auth_ok, item.error)
        table.add_row(
            item.profile.name,
            _percent(primary.remaining_percent if primary else None),
            _percent(secondary.remaining_percent if secondary else None),
            limits.plan_type if limits and limits.plan_type else "?",
            Text(current_status, style=_status_style(current_status)),
            fmt_reset(primary.resets_at if primary else None),
            fmt_reset(secondary.resets_at if secondary else None),
        )
    return table


def render_status_view(
    statuses: list[ProfileStatus],
    *,
    command_hint: bool = True,
    refreshed_at: datetime | None = None,
) -> Group:
    parts: list[RenderableType] = []
    if refreshed_at is not None:
        parts.append(Align.right(Text(fmt_refreshed_at(refreshed_at), style="dim")))
    parts.append(render_status_table(statuses))
    if command_hint:
        parts.append(
            Text(
                "Commands: refresh | login <profile> | exec <profile> <prompt> | quit",
                style="dim",
            )
        )
    return Group(*parts)


def render_message(message: str, *, title: str = "Message") -> Panel:
    return Panel(Text(message.rstrip() or "<empty>", overflow="fold"), title=title)
