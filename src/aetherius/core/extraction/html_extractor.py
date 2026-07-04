"""HTML extraction via CSS and XPath selectors using parsel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parsel import Selector

from ..errors import ExtractionError


@dataclass
class HtmlExtractSpec:
    from_: str  # "html"
    selector: str  # CSS or XPath expression
    selector_type: str = "css"  # "css" | "xpath"
    attr: str | None = None  # attribute to extract; None → text content
    multiple: bool = True  # True → list, False → first match only


def extract_html(body: bytes, spec: dict[str, "HtmlExtractSpec"]) -> dict[str, Any]:
    """Run all extraction specs in *spec* against an HTML *body*.

    Returns a dict mapping each output name to a string (single) or list of strings (multiple).
    """
    try:
        sel = Selector(text=body.decode("utf-8", errors="replace"))
    except Exception as exc:
        raise ExtractionError(f"Cannot parse HTML response body: {exc}") from exc

    result: dict[str, Any] = {}

    for output_name, s in spec.items():
        try:
            if s.selector_type == "xpath":
                nodes = sel.xpath(s.selector)
            else:
                nodes = sel.css(s.selector)
        except Exception as exc:
            raise ExtractionError(
                f"Invalid {s.selector_type} selector {s.selector!r}: {exc}"
            ) from exc

        if s.attr:
            values = [node.attrib.get(s.attr, "") for node in nodes]
        else:
            values = nodes.getall()

        result[output_name] = values if s.multiple else (values[0] if values else None)

    return result
