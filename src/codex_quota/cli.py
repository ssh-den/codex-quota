from __future__ import annotations

import json
import sys
from typing import Annotated, Any

import typer
from rich.console import Console

from .codex import codex_version, simple_exec
from .codex import login as codex_login
from .config import ensure_config, load_config
from .errors import CodexUsageError, ProfileNotFoundError
from .models import AppConfig, ProfileStatus
from .paths import default_paths
from .profiles import (
    add_profile,
    discover_profiles,
    ensure_profiles_dir,
    get_profile,
    profile_path,
)
from .profiles import remove_profile as remove_profile_dir
from .render import render_profile_table, render_status_table
from .service import check_failed, collect_statuses
from .tui import run_fullscreen_tui

app = typer.Typer(
    no_args_is_help=True, help="Manage Codex CLI profiles and quota usage."
)
profile_app = typer.Typer(no_args_is_help=True, help="Manage isolated Codex profiles.")
app.add_typer(profile_app, name="profile")
console = Console()


def _config() -> AppConfig:
    return load_config()


def _print_error(exc: Exception) -> None:
    console.print(f"[red]{exc}[/red]")


def _window_payload(window: Any) -> dict[str, Any] | None:
    if window is None:
        return None
    return {
        "used_percent": window.used_percent,
        "remaining_percent": window.remaining_percent,
        "window_duration_mins": window.window_duration_mins,
        "resets_at": window.resets_at,
    }


def _rate_limits_payload(
    item: ProfileStatus,
    *,
    include_raw: bool = False,
) -> dict[str, Any] | None:
    limits = item.rate_limits
    if limits is None:
        return None

    payload: dict[str, Any] = {
        "blocked": limits.is_blocked,
        "rate_limit_reached_type": limits.rate_limit_reached_type,
        "primary": _window_payload(limits.primary),
        "secondary": _window_payload(limits.secondary),
    }
    if include_raw:
        payload["plan_type"] = limits.plan_type
        payload["credits"] = limits.credits
        payload["raw"] = limits.raw
    return payload


def _status_payload(
    statuses: list[ProfileStatus],
    *,
    include_path: bool = False,
    include_raw: bool = False,
) -> list[dict[str, Any]]:
    return [
        {
            "profile": item.profile.name,
            "status": item.status,
            "auth_ok": item.auth_ok,
            "codex_ok": item.codex_ok,
            "ok": item.ok,
            "error": item.error,
            **({"path": str(item.profile.codex_home)} if include_path else {}),
            "rate_limits": _rate_limits_payload(item, include_raw=include_raw),
        }
        for item in statuses
    ]


@app.callback()
def main() -> None:
    """Manage isolated Codex profiles and inspect quota usage."""


@app.command()
def init(
    overwrite_config: Annotated[bool, typer.Option("--overwrite-config")] = False,
    verify: Annotated[bool, typer.Option("--verify", "--check")] = False,
) -> None:
    """Bootstrap directories and validate the local Codex environment."""
    try:
        config = ensure_config(overwrite=overwrite_config)
        ensure_profiles_dir(config)
        profiles = discover_profiles(config)

        paths = default_paths()
        console.print(f"Config file: {paths.config_file}")
        console.print(f"Profiles dir: {config.profiles_dir}")
        console.print(render_profile_table(profiles))

        try:
            console.print(f"Codex: {codex_version(config.codex_bin)}")
        except CodexUsageError as exc:
            console.print(f"[yellow]{exc}[/yellow]")
            if verify:
                raise typer.Exit(2) from exc

        if verify:
            statuses = collect_statuses(config)
            console.print(render_status_table(statuses))
            raise typer.Exit(2 if check_failed(statuses) else 0)
    except CodexUsageError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


@profile_app.command("list")
def profile_list() -> None:
    """List profiles discovered under profiles_dir."""
    try:
        console.print(render_profile_table(discover_profiles(_config())))
    except CodexUsageError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


@profile_app.command("add")
def profile_add(
    name: Annotated[str, typer.Argument(help="Profile name")],
    exist_ok: Annotated[bool, typer.Option("--exist-ok", "--force")] = False,
    run_login: Annotated[bool, typer.Option("--login")] = False,
    device_auth: Annotated[
        bool,
        typer.Option("--device-auth", help="Pass --device-auth to codex login."),
    ] = False,
) -> None:
    """Create a new isolated profile directory."""
    try:
        if device_auth and not run_login:
            raise CodexUsageError("--device-auth requires --login")
        config = _config()
        profile = add_profile(config, name, exist_ok=exist_ok)
        console.print(f"Created profile: {profile.name}")
        console.print(str(profile.codex_home))

        if run_login:
            raise typer.Exit(
                codex_login(profile, config.codex_bin, device_auth=device_auth)
            )
    except CodexUsageError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


@profile_app.command("remove")
def profile_remove(
    name: Annotated[str, typer.Argument(help="Profile name")],
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Remove a profile directory after safety checks."""
    try:
        config = _config()
        profile = get_profile(config, name)

        if profile.has_auth:
            console.print("[yellow]Warning: auth.json exists in this profile.[/yellow]")

        if not yes:
            confirmed = typer.confirm(
                f"Delete profile '{name}' at {profile.codex_home}?"
            )
            if not confirmed:
                raise typer.Exit(1)

        removed = remove_profile_dir(config, name)
        console.print(f"Removed profile: {removed.name}")
    except CodexUsageError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


@profile_app.command("path")
def profile_path_cmd(name: Annotated[str, typer.Argument(help="Profile name")]) -> None:
    """Print the CODEX_HOME path for scripting."""
    try:
        typer.echo(str(profile_path(_config(), name)))
    except CodexUsageError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


@app.command()
def login(
    profile_name: Annotated[str, typer.Argument(help="Profile name")],
    create: Annotated[bool, typer.Option("--create")] = False,
    device_auth: Annotated[
        bool,
        typer.Option("--device-auth", help="Pass --device-auth to codex login."),
    ] = False,
) -> None:
    """Run the official Codex login flow for an existing profile."""
    try:
        config = _config()
        profile = (
            add_profile(config, profile_name, exist_ok=True)
            if create
            else get_profile(config, profile_name)
        )
        raise typer.Exit(
            codex_login(profile, config.codex_bin, device_auth=device_auth)
        )
    except CodexUsageError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


@app.command()
def status(
    profile_name: Annotated[
        str | None, typer.Argument(help="Optional profile name")
    ] = None,
    json_out: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
    json_paths: Annotated[
        bool,
        typer.Option(
            "--json-paths", help="Include absolute profile paths in JSON output."
        ),
    ] = False,
    json_raw: Annotated[
        bool,
        typer.Option(
            "--json-raw", help="Include raw rate-limit payload in JSON output."
        ),
    ] = False,
) -> None:
    """Read quota status for one or all discovered profiles."""
    try:
        statuses = collect_statuses(_config(), profile_name)
        if json_out:
            console.print_json(
                json.dumps(
                    _status_payload(
                        statuses, include_path=json_paths, include_raw=json_raw
                    )
                )
            )
        else:
            console.print(render_status_table(statuses))
    except ProfileNotFoundError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc
    except CodexUsageError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


@app.command()
def check(
    profile_name: Annotated[
        str | None, typer.Argument(help="Optional profile name")
    ] = None,
) -> None:
    """Exit non-zero if any selected profile has auth, quota, or Codex problems."""
    try:
        statuses = collect_statuses(_config(), profile_name)
        console.print(render_status_table(statuses))
        raise typer.Exit(2 if check_failed(statuses) else 0)
    except CodexUsageError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


@app.command("exec")
def exec_prompt(
    profile_name: Annotated[str, typer.Argument(help="Profile name")],
    prompt: Annotated[str, typer.Argument(help="Prompt to send")],
    raw: Annotated[
        bool, typer.Option("--raw", help="Do not force Codex JSON output.")
    ] = False,
) -> None:
    """Run official codex exec under a selected CODEX_HOME."""
    try:
        config = _config()
        proc = simple_exec(
            get_profile(config, profile_name), prompt, config, json_output=not raw
        )

        if proc.stdout:
            console.print(proc.stdout.rstrip())
        if proc.stderr:
            console.print(proc.stderr.rstrip(), style="yellow")

        raise typer.Exit(proc.returncode)
    except CodexUsageError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


@app.command()
def tui(
    refresh: Annotated[float | None, typer.Option("--refresh", "-r")] = None,
) -> None:
    """Open a Textual live quota view."""
    try:
        config = _config()
        refresh_seconds = refresh or config.refresh_seconds

        if refresh_seconds <= 0:
            raise typer.BadParameter("--refresh must be greater than zero")

        if not sys.stdin.isatty() or not console.is_terminal:
            statuses = collect_statuses(config)
            console.print(render_status_table(statuses))
            raise typer.Exit(2 if check_failed(statuses) else 0)

        run_fullscreen_tui(config, refresh_seconds)
    except CodexUsageError as exc:
        _print_error(exc)
        raise typer.Exit(2) from exc


if __name__ == "__main__":
    app()
