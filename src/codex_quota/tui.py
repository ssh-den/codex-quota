from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass, field
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Input, Static

from .codex import login as codex_login
from .codex import simple_exec
from .errors import CodexUsageError
from .models import AppConfig, Profile, ProfileStatus
from .profiles import get_profile
from .render import render_message, render_status_view
from .service import collect_statuses


class TuiCommandError(CodexUsageError):
    """Raised when an interactive TUI command is malformed or cannot run."""


@dataclass(slots=True)
class TuiState:
    statuses: list[ProfileStatus] = field(default_factory=list)
    message: str | None = None
    message_title: str = "Message"
    refreshed_at: datetime | None = None
    refresh_pending: bool = False


def _profile_for_tui(config: AppConfig, name: str) -> Profile:
    return get_profile(config, name)


class CodexUsageTui(App[None]):
    """Textual-based TUI for Codex usage monitoring."""

    CSS = """
    Screen { layout: vertical; }
    #body { height: 1fr; padding: 1 2; }
    #status { height: auto; }
    #message { height: auto; margin-top: 1; }
    #command { dock: bottom; margin: 0 2 1 2; }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+d", "quit", "Quit"),
        ("ctrl+r", "refresh", "Refresh"),
        ("f5", "refresh", "Refresh"),
    ]

    def __init__(self, config: AppConfig, refresh_seconds: float) -> None:
        super().__init__()
        self.config = config
        self.refresh_seconds = refresh_seconds
        self.state = TuiState()
        self._refresh_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="body"):
            yield Static(id="status")
            yield Static(id="message")
        yield Input(
            placeholder="refresh | login <profile> | exec <profile> <prompt> | quit",
            id="command",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#command", Input).focus()
        self._set_message("Loading Codex usage...", title="Status")
        self._schedule_refresh(clear_message=True)
        self.set_interval(self.refresh_seconds, self._schedule_auto_refresh)

    def on_mouse_scroll_up(self, event: object) -> None:
        self._stop_event(event)

    def on_mouse_scroll_down(self, event: object) -> None:
        self._stop_event(event)

    def action_refresh(self) -> None:
        self._schedule_refresh(clear_message=True)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value.strip() or "refresh"
        event.input.value = ""
        await self._run_command(command)

    async def _run_command(self, command: str) -> None:
        try:
            parts = shlex.split(command)
            if not parts or parts[0] in {"refresh", "r"}:
                self._schedule_refresh(clear_message=True)
                return
            name = parts[0]
            if name in {"q", "quit", "exit"}:
                self.exit()
                return
            if name in {"help", "?"}:
                self._set_message(
                    "refresh | r\n"
                    "login <profile> [--device-auth]\n"
                    "exec <profile> <prompt>\n"
                    "quit | q | exit",
                    title="Commands",
                )
                return
            if name == "login":
                await self._run_login(parts)
                return
            if name == "exec":
                await self._run_exec(parts)
                return
            raise TuiCommandError(
                "Commands: refresh, login <profile>, exec <profile> <prompt>, quit"
            )
        except (TuiCommandError, CodexUsageError) as exc:
            self._set_message(str(exc), title="Error")
        except ValueError as exc:
            self._set_message(f"Invalid command syntax: {exc}", title="Error")

    async def _run_login(self, parts: list[str]) -> None:
        if len(parts) not in {2, 3}:
            raise TuiCommandError("Usage: login <profile> [--device-auth]")
        if len(parts) == 3 and parts[2] != "--device-auth":
            raise TuiCommandError("Usage: login <profile> [--device-auth]")
        profile = _profile_for_tui(self.config, parts[1])
        device_auth = len(parts) == 3
        self._set_message(
            "Running official Codex login...", title=f"login {profile.name}"
        )
        rc = await asyncio.to_thread(
            codex_login,
            profile,
            self.config.codex_bin,
            device_auth=device_auth,
        )
        self._set_message(
            f"codex login exited with code {rc}.", title=f"login {profile.name}"
        )
        self._schedule_refresh(clear_message=False)

    async def _run_exec(self, parts: list[str]) -> None:
        if len(parts) < 3:
            raise TuiCommandError("Usage: exec <profile> <prompt>")
        profile = _profile_for_tui(self.config, parts[1])
        prompt = " ".join(parts[2:])
        self._set_message("Running codex exec...", title=f"exec {profile.name}")
        proc = await asyncio.to_thread(simple_exec, profile, prompt, self.config)
        output = (
            proc.stdout or proc.stderr or f"Process exited with code {proc.returncode}."
        )
        self._set_message(output, title=f"exec {profile.name}")

    def _schedule_auto_refresh(self) -> None:
        if self.query_one("#command", Input).value.strip():
            return
        self._schedule_refresh(clear_message=False)

    def _schedule_refresh(self, *, clear_message: bool) -> None:
        if self._refresh_task and not self._refresh_task.done():
            return
        if clear_message:
            self.state.message = None
            self.state.message_title = "Message"
        self.state.refresh_pending = True
        self._render()
        self._refresh_task = asyncio.create_task(self._refresh())

    async def _refresh(self) -> None:
        try:
            statuses = await asyncio.to_thread(collect_statuses, self.config)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.state.refresh_pending = False
            self._set_message(str(exc), title="Refresh error")
            return
        self.state.statuses = statuses
        self.state.refreshed_at = datetime.now()
        self.state.refresh_pending = False
        self._render()

    def _set_message(self, message: str, *, title: str) -> None:
        self.state.message = message
        self.state.message_title = title
        self._render()

    def _render(self) -> None:
        status = self.query_one("#status", Static)
        message = self.query_one("#message", Static)
        status.update(
            render_status_view(
                self.state.statuses, refreshed_at=self.state.refreshed_at
            )
        )
        if self.state.message:
            message.update(
                render_message(self.state.message, title=self.state.message_title)
            )
        elif self.state.refresh_pending:
            message.update("refreshing...")
        else:
            message.update("")

    @staticmethod
    def _stop_event(event: object) -> None:
        stop = getattr(event, "stop", None)
        if callable(stop):
            stop()


def run_fullscreen_tui(config: AppConfig, refresh_seconds: float) -> None:
    CodexUsageTui(config, refresh_seconds).run()
