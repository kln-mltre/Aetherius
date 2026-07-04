"""Syntax-highlighted, validated JSON preview widget."""

from __future__ import annotations

import json
from typing import Any

from rich.syntax import Syntax

from textual.widgets import Static


class JsonPreview(Static):
    """Read-only, syntax-highlighted rendering of arbitrary JSON-serializable data."""

    def show(self, data: Any) -> None:
        text = json.dumps(data, indent=2, default=str, ensure_ascii=False)
        self.update(Syntax(text, "json", theme="ansi_dark", word_wrap=True))
