"""Act picker with inline explanations of each Act.

A Select of the four Acts (their runnable status from the shared catalogue) plus a live one-line
explanation. Emits :class:`ActPicker.ActChanged` so the Studio can re-key the available actions and
re-validate when the Act changes.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, Select, Static

from ....builder.catalog import act_infos, get_act_info
from ...theme import ACT_LABELS


def _option_label(act: str, implemented: bool) -> str:
    return ACT_LABELS[act] + ("" if implemented else " (not runnable yet)")


class ActPicker(Vertical):
    """Choose the Blueprint's Act and show what it does."""

    DEFAULT_CSS = """
    ActPicker {
        height: auto;
        padding: 1 1 0 1;
    }
    ActPicker #act-explanation {
        color: $text-muted;
        padding: 1 0 0 0;
    }
    """

    class ActChanged(Message):
        """Posted when the selected Act changes."""

        def __init__(self, act: str) -> None:
            self.act = act
            super().__init__()

    def __init__(self, act: str = "vector") -> None:
        super().__init__()
        self._act = act

    def compose(self) -> ComposeResult:
        yield Label("Act")
        yield Select(
            [(_option_label(info.act, info.implemented), info.act) for info in act_infos()],
            value=self._act,
            allow_blank=False,
            id="act-select",
        )
        yield Static(self._explanation(self._act), id="act-explanation")

    @property
    def act(self) -> str:
        return self._act

    def _explanation(self, act: str) -> str:
        info = get_act_info(act)
        note = (
            "" if info.implemented else "  This Act has no driver yet — valid to author, not run."
        )
        return info.summary + note

    def on_select_changed(self, event: Select.Changed) -> None:
        # Handle it here and stop it, so the Studio only reacts to the dedicated ActChanged message.
        event.stop()
        act = str(event.value)
        self._act = act
        self.query_one("#act-explanation", Static).update(self._explanation(act))
        self.post_message(self.ActChanged(act))
