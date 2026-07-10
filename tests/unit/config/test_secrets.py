"""Tests for config/secrets.py — environment-backed secret resolution."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from aetherius.config import secrets as secrets_mod

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_real_dotenv(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Keep tests hermetic: never load the repo's real .env, rely only on explicit env vars.
    monkeypatch.setattr(secrets_mod, "load_dotenv_once", lambda: None)
    yield


def test_caller_value_wins_over_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHERIUS_SECRET_TOK", "from-env")
    assert secrets_mod.resolve_secrets(["tok"], {"tok": "from-caller"})["tok"] == "from-caller"


def test_resolves_from_prefixed_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHERIUS_SECRET_CAS_PASS", "pw")
    assert secrets_mod.resolve_secrets(["cas_pass"], None) == {"cas_pass": "pw"}


def test_unresolved_secret_is_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AETHERIUS_SECRET_NOPE", raising=False)
    assert "nope" not in secrets_mod.resolve_secrets(["nope"], None)


def test_available_from_env_reports_present_subset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHERIUS_SECRET_A", "x")
    monkeypatch.delenv("AETHERIUS_SECRET_B", raising=False)
    assert secrets_mod.available_from_env(["a", "b"]) == {"a"}
