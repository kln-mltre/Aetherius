"""Headless Blueprint construction, reusable by the Console, the daemon and the SDKs.

The Console is only its presentation layer: everything here is Textual-free. A ``BlueprintDraft`` is
the editing state; ``validate_draft`` reports issues live; ``build_blueprint``/``save_blueprint``
finalise it; ``act_infos``/``actions_for_act`` project the action registry into UI-ready records;
``list_templates``/``template_draft`` seed a draft from a starter.
"""

from __future__ import annotations

from .catalog import ActInfo, ActionInfo, act_infos, actions_for_act, get_act_info
from .factory import (
    BlueprintDraft,
    StepDraft,
    assemble_blueprint,
    build_blueprint,
    save_blueprint,
    slugify_name,
)
from .templates import TemplateInfo, list_templates, template_draft
from .validation import ValidationIssue, validate_draft

__all__ = [
    "ActInfo",
    "ActionInfo",
    "act_infos",
    "actions_for_act",
    "get_act_info",
    "BlueprintDraft",
    "StepDraft",
    "assemble_blueprint",
    "build_blueprint",
    "save_blueprint",
    "slugify_name",
    "TemplateInfo",
    "list_templates",
    "template_draft",
    "ValidationIssue",
    "validate_draft",
]
