"""Cognition substrate shared by Oracle (Act III) and Phantom (Act IV).

The model-backed reasoning both cognitive Acts depend on, behind one segregated interface so a
Blueprint picks a provider (Claude by default, a local model optionally) without any Act knowing
which. See ``provider.py`` for the roles and ``docs/phase-2/2-a-cognition.md`` for the milestone.
"""

from __future__ import annotations

from .provider import CognitionProvider, Extractor, Grounder, GroundResult, Planner

__all__ = ["CognitionProvider", "Extractor", "Grounder", "GroundResult", "Planner"]
