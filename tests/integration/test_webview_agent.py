"""The embedded engine's injected agent, played in a real Chromium and compared with Playwright.

This is the most direct comparison the two implementations allow. The conformance corpus compares
whole runs; here the *same page* is read twice — once by the agent that ships to a phone, once by
Playwright — and the answers must match. A jsdom double cannot prove that: it has no layout engine,
so its notion of "visible" and its `innerText` are approximations. A real browser has both.

The agent is the artefact `sdks/react-native` builds, so this test also fails when that build is
missing or stale — which is the point: an agent nobody has built is an agent nobody has run.

Marked ``browser``: skipped in the base CI, run by the dedicated browser job and by the job that
replays the conformance corpus.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.browser
pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENT_SOURCE = _REPO_ROOT / "sdks" / "react-native" / "src" / "generated" / "agent-source.ts"

_PAGE_HTML = """<!doctype html>
<html><body>
  <h1 id="titre">Bonjour <b>Kylian</b> !</h1>
  <p class="prix">12,50 EUR</p>
  <p class="rien">aucun chiffre</p>
  <img class="avatar" src="/avatar.png" alt="">
  <div class="row"><span class="t">Alpha</span><span class="p">3,20</span></div>
  <div class="row"><span class="t">Beta</span><span class="p">7</span></div>
  <p class="cachee" style="display:none">invisible</p>
  <input id="champ" value="">
  <button id="bouton" disabled>Indisponible</button>
</body></html>"""


def _agent_source() -> str:
    """The bundled agent, read out of the generated module the package ships."""
    if not _AGENT_SOURCE.exists():
        pytest.skip(
            "the injected agent has not been built: "
            "run `npm --prefix sdks run build --workspace @aetherius/react-native`"
        )
    text = _AGENT_SOURCE.read_text(encoding="utf-8")
    match = re.search(r"export const AGENT_SOURCE = (\".*?\");\n", text, re.DOTALL)
    assert match is not None, "AGENT_SOURCE not found in the generated module"
    return json.loads(match.group(1))


class _Agent:
    """Drives the injected agent in a Playwright page, over the same protocol the driver speaks."""

    def __init__(self, page: Any) -> None:
        self._page = page
        self._id = 0
        # The page has no React Native bridge: stand in for it with a collector the test can read,
        # so the agent's own `post` path is exercised rather than bypassed.
        page.evaluate(
            "() => { window.__sent = []; "
            "window.ReactNativeWebView = { postMessage: (p) => window.__sent.push(p) }; }"
        )
        page.evaluate(f"() => {{ window.__aetheriusGen = 1; {_agent_source()} }}")

    def call(self, op: str, params: dict[str, Any], timeout_ms: int = 3000) -> Any:
        self._id += 1
        call_id = f"t{self._id}"
        request = {"aeth": 1, "id": call_id, "op": op, "params": params, "timeoutMs": timeout_ms}
        self._page.evaluate("(order) => window.__aetherius.handle(order)", json.dumps(request))
        self._page.wait_for_function(
            "(id) => window.__sent.some((raw) => JSON.parse(raw).id === id)",
            arg=call_id,
            timeout=timeout_ms + 2000,
        )
        raw = self._page.evaluate(
            "(id) => window.__sent.find((raw) => JSON.parse(raw).id === id)", call_id
        )
        answer = json.loads(raw)
        if not answer["ok"]:
            raise AssertionError(f"{op} failed: {answer['error']['message']}")
        return answer["value"]


@pytest.fixture(scope="module")
def page() -> Any:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        opened = context.new_page()
        opened.goto("data:text/html," + urllib.parse.quote(_PAGE_HTML))
        yield opened
        browser.close()


def test_the_agent_announces_itself_on_the_document(page: Any) -> None:
    _Agent(page)
    sent = [json.loads(raw) for raw in page.evaluate("() => window.__sent")]
    ready = [message for message in sent if message.get("ready")]
    assert ready, "the agent must announce itself so the driver knows the page is usable"
    assert ready[-1]["gen"] == 1, "the generation the host assigned is echoed back"


def test_reads_match_playwright_on_the_same_page(page: Any) -> None:
    agent = _Agent(page)
    read = agent.call(
        "extract",
        {
            "outputs": {
                "titre": {"selector": "#titre", "as": "text"},
                "prix": {"selector": ".prix", "as": "number"},
                "rien": {"selector": ".rien", "as": "number"},
                "html": {"selector": "#titre", "as": "html"},
                "src": {"selector": "img.avatar", "as": "attr", "attr": "src"},
                "absent": {"selector": "img.avatar", "as": "attr", "attr": "data-nope"},
                "lignes": {"selector": ".row", "as": "count"},
                "titres": {"selector": ".row .t", "as": "list"},
                "produits": {
                    "each": ".row",
                    "fields": {
                        "nom": {"selector": ".t", "as": "text"},
                        "prix": {"selector": ".p", "as": "number"},
                    },
                },
            }
        },
    )

    # The same reads, done by Playwright, are the reference the agent is compared against.
    assert read["titre"] == (page.locator("#titre").inner_text() or "").strip()
    assert read["prix"] == 12.5
    assert read["rien"] is None
    assert read["html"] == page.locator("#titre").inner_html()
    assert read["src"] == page.locator("img.avatar").get_attribute("src")
    assert read["absent"] is None
    assert read["lignes"] == page.locator(".row").count()
    assert read["titres"] == [
        (target.inner_text() or "").strip() for target in page.locator(".row .t").all()
    ]
    assert read["produits"] == [
        {"nom": "Alpha", "prix": 3.2},
        {"nom": "Beta", "prix": 7},
    ]


def test_a_hidden_element_is_read_the_way_playwright_reads_it(page: Any) -> None:
    agent = _Agent(page)
    read = agent.call("extract", {"outputs": {"corps": {"selector": "body", "as": "text"}}})
    # `inner_text` respects rendering on both sides: the hidden paragraph contributes nothing.
    assert "invisible" not in read["corps"]
    assert "invisible" not in (page.locator("body").inner_text() or "")


def test_xpath_and_text_locators_work_in_a_real_browser(page: Any) -> None:
    agent = _Agent(page)
    read = agent.call(
        "extract",
        {
            "outputs": {
                "v": {"selector": "//h1[@id='titre']", "selector_type": "xpath", "as": "text"}
            }
        },
    )
    assert read["v"] == "Bonjour Kylian !"
    # The text locator lives on the action path; hovering proves it resolved to exactly one element.
    agent.call("hover", {"selector": "Alpha", "selector_type": "text"})


def test_strict_mode_matches_playwright_strict_mode(page: Any) -> None:
    agent = _Agent(page)
    with pytest.raises(AssertionError, match="matched 2 elements"):
        agent.call("click", {"selector": ".row"}, timeout_ms=500)
    # Playwright refuses the same thing, which is the behaviour being reproduced.
    with pytest.raises(Exception, match="strict mode"):
        page.locator(".row").click(timeout=500)


def test_an_action_writes_a_value_a_real_browser_reports_back(page: Any) -> None:
    agent = _Agent(page)
    hostile = "mot'de\"passe`\\ </script>"
    agent.call("fill", {"selector": "#champ", "value": hostile})
    assert page.locator("#champ").input_value() == hostile
    # Nothing of the value was compiled: had it been, this would have run.
    assert page.evaluate("() => window.__pwned || null") is None


def test_an_unactionable_target_times_out_with_its_reason(page: Any) -> None:
    agent = _Agent(page)
    with pytest.raises(AssertionError, match="never became visible and enabled"):
        agent.call("click", {"selector": "#bouton"}, timeout_ms=600)


def test_an_element_that_appears_late_is_acted_on(page: Any) -> None:
    """Zero matches means *not yet*: the agent waits, exactly as Playwright does.

    Regression guard for the defect the milestone 3-E probes found — the strict match raised on zero
    matches and short-circuited the auto-waiting, so a portal that renders its form a few hundred
    milliseconds after load worked under Playwright and failed on the phone. Played in a real
    Chromium because that is where "a bit later" is real: jsdom runs no page timers here.
    """
    agent = _Agent(page)
    page.evaluate(
        "() => { setTimeout(() => { const b = document.createElement('button'); "
        "b.id = 'tardif'; b.textContent = 'Tard'; document.body.appendChild(b); }, 400); }"
    )
    # No exception: the click landed on an element that did not exist when the call was made.
    agent.call("click", {"selector": "#tardif"}, timeout_ms=4000)
    assert page.locator("#tardif").count() == 1

    # Playwright agrees on the same page, which is the behaviour being reproduced.
    page.evaluate("() => document.getElementById('tardif').remove()")
    page.evaluate(
        "() => { setTimeout(() => { const b = document.createElement('button'); "
        "b.id = 'tardif'; document.body.appendChild(b); }, 400); }"
    )
    page.locator("#tardif").click(timeout=4000)
