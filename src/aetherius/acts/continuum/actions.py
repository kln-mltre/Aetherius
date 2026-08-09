"""Mapping of core actions to concrete Playwright page operations.

Pure functions with a uniform signature ``(page, params, render) -> dict``: they translate a
Blueprint step into one browser operation and return that step's outputs. Kept free of the event
bus and filesystem on purpose, so they are trivially testable against a fake page. Artifact-producing
actions (screenshot) and DOM reads (extract/wait_for/evaluate) live in the driver and bridge, which
own the run context.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ...core.errors import ActionError, NetworkError
from .bridge import is_timeout

Renderer = Callable[[Any], Any]
PageAction = Callable[[Any, Mapping[str, Any], Renderer], dict[str, Any]]

#: Chromium reports a transport failure with a ``net::ERR_*`` code in the message, and it is the
#: only browser this Act launches. Matching the token rather than a phrasing keeps the test narrow:
#: a page that closes mid-navigation, or a frame that detaches, is not a network problem and must
#: keep its own path.
_TRANSPORT_MARKER = "net::ERR_"


def _navigating(action: str, run: Callable[[], Any], url: Any = None) -> Any:
    """Run a navigation, typing a transport failure as a ``NetworkError``.

    Without this, an unreachable source escapes as a raw Playwright ``Error`` and the runtime wraps
    it in a ``RunError`` — an engine bug, as far as a caller can tell. It is the same source of
    truth the embedded engine reads from its WebView (``docs/embedded.md``): the two engines must
    agree that a refused connection is a source in trouble, not a Blueprint or a defect.

    Playwright's own ``TimeoutError`` is deliberately **not** caught here: a page too slow to finish
    loading keeps the path it already had (``bridge.as_step_timeout``).
    """
    try:
        return run()
    except Exception as exc:  # noqa: BLE001 - re-raised untouched unless it is a transport failure
        if is_timeout(exc) or _TRANSPORT_MARKER not in str(exc):
            raise
        target = f" ({url})" if url else ""
        raise NetworkError(f"{action}: the source is unreachable{target} — {exc}") from exc


def _locator(page: Any, params: Mapping[str, Any], render: Renderer) -> Any:
    """Resolve a step's target into a Playwright locator.

    ``selector`` is CSS by default; ``selector_type`` switches to ``xpath`` or ``text``.
    """
    selector = render(params.get("selector", ""))
    if not selector:
        raise ActionError("This action requires a 'selector'.")
    selector_type = str(render(params.get("selector_type", "css")) or "css").lower()
    if selector_type == "css":
        return page.locator(selector)
    if selector_type == "xpath":
        return page.locator(selector if selector.startswith("xpath=") else f"xpath={selector}")
    if selector_type == "text":
        return page.get_by_text(selector)
    raise ActionError(f"Unknown selector_type {selector_type!r} (expected css, xpath or text).")


def navigate(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    url = render(params.get("url", ""))
    if not url:
        raise ActionError("navigate requires a 'url'.")
    wait_until = render(params.get("wait_until", "load"))
    response = _navigating("navigate", lambda: page.goto(url, wait_until=wait_until), url)
    return {"url": page.url, "status": response.status if response is not None else None}


def back(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    _navigating("back", page.go_back)
    return {"url": page.url}


def forward(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    _navigating("forward", page.go_forward)
    return {"url": page.url}


def reload(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    _navigating("reload", page.reload, page.url)
    return {"url": page.url}


def click(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    _locator(page, params, render).click()
    return {}


def fill(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    _locator(page, params, render).fill(render(params.get("value", "")))
    return {}


def type_text(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    text = render(params.get("text", params.get("value", "")))
    delay = params.get("delay_ms")
    locator = _locator(page, params, render)
    if delay is not None:
        locator.press_sequentially(text, delay=float(render(delay)))
    else:
        locator.press_sequentially(text)
    return {}


def press(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    key = render(params.get("key", ""))
    if not key:
        raise ActionError("press requires a 'key'.")
    if params.get("selector"):
        _locator(page, params, render).press(key)
    else:
        page.keyboard.press(key)
    return {}


def select(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    values = render(params.get("values", params.get("value")))
    if values is None:
        raise ActionError("select requires a 'value' or 'values'.")
    _locator(page, params, render).select_option(values)
    return {}


def hover(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    _locator(page, params, render).hover()
    return {}


def scroll(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    if params.get("selector"):
        _locator(page, params, render).scroll_into_view_if_needed()
    else:
        dx = float(render(params.get("dx", 0)) or 0)
        dy = float(render(params.get("dy", 0)) or 0)
        page.mouse.wheel(dx, dy)
    return {}


def upload(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    file = render(params.get("file", params.get("files")))
    if not file:
        raise ActionError("upload requires a 'file'.")
    _locator(page, params, render).set_input_files(file)
    return {}


def drag(page: Any, params: Mapping[str, Any], render: Renderer) -> dict[str, Any]:
    source = render(params.get("source", params.get("from", "")))
    target = render(params.get("target", params.get("to", "")))
    if not source or not target:
        raise ActionError("drag requires 'source'/'from' and 'target'/'to' selectors.")
    page.drag_and_drop(source, target)
    return {}


# Simple, side-effect-free page operations dispatched directly by the driver.
PAGE_ACTIONS: dict[str, PageAction] = {
    "navigate": navigate,
    "back": back,
    "forward": forward,
    "reload": reload,
    "click": click,
    "fill": fill,
    "type": type_text,
    "press": press,
    "select": select,
    "hover": hover,
    "scroll": scroll,
    "upload": upload,
    "drag": drag,
}
