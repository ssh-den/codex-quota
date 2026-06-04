from __future__ import annotations


class CodexUsageError(RuntimeError):
    """Base exception for user-facing failures."""


class ConfigError(CodexUsageError):
    """Raised when app config is missing, malformed, or unsafe."""


class ProfileError(CodexUsageError):
    """Raised when profile discovery or profile mutation fails."""


class ProfileNameError(ProfileError):
    """Raised when a profile name is invalid."""


class ProfileNotFoundError(ProfileError):
    """Raised when a requested profile does not exist."""


class CodexNotFoundError(CodexUsageError):
    """Raised when the codex executable cannot be found."""


class CodexCommandError(CodexUsageError):
    """Raised when an official Codex command fails."""


class AuthError(CodexUsageError):
    """Raised when Codex reports an authentication problem."""


class AppServerError(CodexUsageError):
    """Raised when Codex app-server JSON-RPC fails."""
