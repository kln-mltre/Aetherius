"""Typed exception hierarchy for Aetherius. Errors are never swallowed silently."""

from __future__ import annotations


class AetheriusError(Exception):
    """Base for all Aetherius exceptions."""


# ── Blueprint ──────────────────────────────────────────────────────────────────


class BlueprintError(AetheriusError):
    """Base for Blueprint-related errors."""


class BlueprintLoadError(BlueprintError):
    """File not found, unreadable, or not valid JSON/YAML."""


class BlueprintSchemaError(BlueprintError):
    """Blueprint violates the JSON Schema or Pydantic model constraints."""


class BlueprintValidationError(BlueprintError):
    """Semantic error: action not supported by the declared Act, missing required input, etc."""


# ── Template ───────────────────────────────────────────────────────────────────


class TemplateError(AetheriusError):
    """Jinja2 rendering failure: undefined variable, bad filter, syntax error."""


# ── Network ───────────────────────────────────────────────────────────────────


class NetworkError(AetheriusError):
    """Base for transport-level failures."""


class TimeoutError(NetworkError):
    """Request exceeded the configured timeout."""


class RetryExhaustedError(NetworkError):
    """All retry attempts failed. Wraps the last transport exception."""

    def __init__(self, message: str, last_error: Exception) -> None:
        super().__init__(message)
        self.last_error = last_error


# ── HTTP assertions ────────────────────────────────────────────────────────────


class StatusAssertionError(AetheriusError):
    """HTTP response status does not match `expect.status`."""

    def __init__(
        self,
        expected: int,
        actual: int,
        url: str,
        body_preview: str = "",
    ) -> None:
        super().__init__(
            f"Expected HTTP {expected}, got {actual} — {url}"
            + (f"\n{body_preview[:200]}" if body_preview else "")
        )
        self.expected = expected
        self.actual = actual
        self.url = url
        self.body_preview = body_preview


# ── Extraction ────────────────────────────────────────────────────────────────


class ExtractionError(AetheriusError):
    """JSONPath / CSS / XPath / predicate evaluation failure."""


# ── Actions ───────────────────────────────────────────────────────────────────


class ActionError(AetheriusError):
    """Unknown action name or missing required action parameter."""


class StepTimeoutError(AetheriusError):
    """A step waited past its budget (e.g. wait_for). Carries the Blueprint's failure code."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


# ── Dependencies ──────────────────────────────────────────────────────────────


class DependencyError(AetheriusError):
    """A required optional dependency (an Act extra) is not installed."""

    def __init__(self, message: str, *, extra: str | None = None) -> None:
        super().__init__(message)
        self.extra = extra


# ── Recorder ──────────────────────────────────────────────────────────────────


class RecorderError(AetheriusError):
    """No recorder backend for the requested Act (unknown, or a pending milestone)."""


# ── Builder ───────────────────────────────────────────────────────────────────


class BuilderError(AetheriusError):
    """Headless builder failure: unknown Act or template, or a name collision on save."""


# ── Runtime ───────────────────────────────────────────────────────────────────


class RunError(AetheriusError):
    """Engine-level failure wrapping an underlying AetheriusError."""

    def __init__(self, message: str, cause: Exception) -> None:
        super().__init__(message)
        self.cause = cause
        self.__cause__ = cause
