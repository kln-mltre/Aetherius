"""Tests for models/registry.py — vision config to cognition provider resolution.

Resolution must stay import-light: none of these tests require the [cognition] or [vision]
extras, because building a provider never touches the heavy SDKs.
"""

from __future__ import annotations

import pytest

from aetherius.acts._cognition.claude import ClaudeProvider
from aetherius.acts._cognition.local import LocalGrounder
from aetherius.core.errors import CognitionError
from aetherius.models.registry import resolve_provider

pytestmark = pytest.mark.unit


def test_defaults_to_claude() -> None:
    provider = resolve_provider(None)
    assert isinstance(provider, ClaudeProvider)
    assert provider.name == "claude"


def test_empty_vision_defaults_to_claude_with_default_model() -> None:
    provider = resolve_provider({})
    assert isinstance(provider, ClaudeProvider)
    assert provider._model == "claude-opus-4-8"


def test_model_is_passed_through() -> None:
    provider = resolve_provider({"model": "claude-sonnet-5"})
    assert isinstance(provider, ClaudeProvider)
    assert provider._model == "claude-sonnet-5"


def test_local_provider_is_resolved() -> None:
    provider = resolve_provider({"provider": "local", "model": "oracle-ui@1"})
    assert isinstance(provider, LocalGrounder)
    assert provider.name == "local"


def test_unknown_provider_raises() -> None:
    with pytest.raises(CognitionError, match="Unknown cognition provider"):
        resolve_provider({"provider": "gpt"})
