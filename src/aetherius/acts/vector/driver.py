"""Vector driver: executes http.request and utility actions for Act I (no browser)."""

from __future__ import annotations

from typing import Any, Callable

from .._shared import SharedActionsMixin
from ...core.actions.registry import find_handler
from ...core.blueprint.models import StepModel
from ...core.blueprint.template import render_value
from ...core.errors import ActionError
from ...core.events.bus import EventBus
from ...core.extraction.html_extractor import HtmlExtractSpec, extract_html
from ...core.extraction.json_extractor import ExtractSpec, extract_json
from ...core.runtime.context import RunContext
from ...network import httpx_proxy_kwargs, resolve_identity
from .client import VectorClient


class VectorDriver(SharedActionsMixin):
    act = "vector"

    def setup(self, ctx: RunContext) -> None:
        opts = ctx.blueprint.options
        timeout_ms = opts.timeout_ms or 30_000

        # Network identity (Jalon G): options.proxy may carry {{ secrets.x }}, so render it against the
        # run context before decoding. run_key keys sticky rotation to the Blueprint (a schedule-level
        # key arrives with the store).
        proxy_opt = render_value(opts.proxy, ctx.template_ctx()) if opts.proxy is not None else None
        identity = resolve_identity(proxy_opt, run_key=ctx.blueprint.name)

        if identity.impersonate is not None:
            # curl_cffi handles its own proxying (including SOCKS5) — hand it the raw proxy URL.
            proxy = identity.proxy.for_httpx() if identity.proxy is not None else None
            self._client = VectorClient(
                timeout_ms=timeout_ms,
                retries=opts.retries,
                proxy=proxy,
                impersonate=identity.impersonate,
            )
        else:
            # httpx_proxy_kwargs guards SOCKS5 without the [network] extra with a typed error.
            self._client = VectorClient(
                timeout_ms=timeout_ms,
                retries=opts.retries,
                **httpx_proxy_kwargs(identity),
            )

    def teardown(self, ctx: RunContext) -> None:
        self._client.close()

    def run_step(
        self,
        step: StepModel,
        ctx: RunContext,
        bus: EventBus,
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        match step.action:
            case "http.request":
                return self._http_request(step, ctx, bus, renderer)
            case "set":
                return self._set(step, renderer)
            case "assert":
                return self._assert(step, renderer)
            case "emit":
                return self._emit(step, ctx, bus, renderer)
            case "wait":
                return self._wait(step, renderer)
            case "notify":
                return self._notify(step, ctx, bus, renderer)
            case _:
                # Built-ins first, then the plugin registry (docs/plugins.md).
                handler = find_handler(step.action)
                if handler is not None:
                    return handler(step, ctx, bus, renderer)
                raise ActionError(f"VectorDriver: unsupported action {step.action!r}")

    # ── Action handlers ───────────────────────────────────────────────────────

    def _http_request(
        self,
        step: StepModel,
        ctx: RunContext,
        bus: EventBus,
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        p = step.extra_fields
        method: str = renderer(p.get("method", "GET"))
        url: str = renderer(p.get("url", ""))
        headers: dict[str, str] = renderer(p.get("headers") or {})
        form: dict[str, str] | None = renderer(p["form"]) if "form" in p else None
        json_body: Any = renderer(p["json"]) if "json" in p else None
        params: dict[str, str] | None = renderer(p.get("params"))
        expect: dict[str, Any] = renderer(p.get("expect") or {})
        expected_status: int | None = expect.get("status")

        response = self._client.request(
            method,
            url,
            headers=headers,
            json=json_body,
            form=form,
            params=params,
            expected_status=expected_status,
        )

        outputs: dict[str, Any] = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
        }

        extract_specs: dict[str, Any] = p.get("extract") or {}
        if extract_specs:
            content_type = response.headers.get("content-type", "")
            extracted = self._dispatch_extract(
                response.content, extract_specs, content_type, renderer
            )
            outputs.update(extracted)

        return outputs

    def _dispatch_extract(
        self,
        body: bytes,
        raw_specs: dict[str, Any],
        content_type: str,
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        json_specs: dict[str, ExtractSpec] = {}
        html_specs: dict[str, HtmlExtractSpec] = {}

        for name, raw in raw_specs.items():
            from_val: str = raw.get("from", "json")
            if from_val == "json":
                json_specs[name] = ExtractSpec(
                    from_=from_val,
                    path=raw.get("path", "$"),
                    where=raw.get("where"),
                    fields={k: v for k, v in (raw.get("fields") or {}).items()},
                )
            else:
                html_specs[name] = HtmlExtractSpec(
                    from_=from_val,
                    selector=raw.get("selector", ""),
                    selector_type=raw.get("selector_type", "css"),
                    attr=raw.get("attr"),
                    multiple=raw.get("multiple", True),
                )

        result: dict[str, Any] = {}
        if json_specs:
            result.update(extract_json(body, json_specs))
        if html_specs:
            result.update(extract_html(body, html_specs))
        return result
