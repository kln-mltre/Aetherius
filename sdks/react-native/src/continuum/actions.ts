/**
 * Blueprint step to WebView operation, mirror of `acts/continuum/actions.py`.
 *
 * Each function renders exactly what the Python engine renders — no more, no less. Rendering a
 * field the other engine leaves alone would make the same Blueprint behave differently on the two,
 * which is the failure this phase exists to prevent; the extraction spec below is the place where
 * that is easiest to get wrong, and the reason it is walked field by field instead of rendered
 * whole.
 *
 * These functions produce *data* — an operation name and JSON parameters. Nothing here builds
 * source. `navigate`, `back`, `forward` and `reload` are absent because they belong to the host,
 * which owns the view (see `webview/protocol.ts`).
 */

import { ActionError, type Renderer } from "@aetherius/engine";

import type { OpName } from "../webview/protocol.js";

export interface AgentOp {
  readonly op: OpName;
  readonly params: Record<string, unknown>;
}

type Params = Record<string, unknown>;
type Builder = (params: Params, render: Renderer) => AgentOp;

function asText(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "string" ? value : String(value);
}

/** `_locator`: `selector` is CSS unless `selector_type` says otherwise. */
function target(params: Params, render: Renderer): Params {
  const selector = asText(render(params["selector"] ?? ""));
  if (selector === "") throw new ActionError("This action requires a 'selector'.");
  const kind = (asText(render(params["selector_type"] ?? "css")) || "css").toLowerCase();
  if (kind !== "css" && kind !== "xpath" && kind !== "text") {
    throw new ActionError(`Unknown selector_type '${kind}' (expected css, xpath or text).`);
  }
  return { selector, selector_type: kind };
}

const click: Builder = (params, render) => ({ op: "click", params: target(params, render) });

const fill: Builder = (params, render) => ({
  op: "fill",
  params: { ...target(params, render), value: render(params["value"] ?? "") },
});

const type: Builder = (params, render) => {
  const raw = params["text"] !== undefined ? params["text"] : params["value"];
  const built: Params = { ...target(params, render), text: render(raw ?? "") };
  if (params["delay_ms"] !== undefined && params["delay_ms"] !== null) {
    built["delay_ms"] = Number(render(params["delay_ms"]));
  }
  return { op: "type", params: built };
};

const press: Builder = (params, render) => {
  const key = asText(render(params["key"] ?? ""));
  if (key === "") throw new ActionError("press requires a 'key'.");
  // The selector is optional here, exactly as in Python: without one the key goes to whatever has
  // focus, which is how a Blueprint submits a form it has just filled.
  const built: Params = params["selector"] ? target(params, render) : {};
  built["key"] = key;
  return { op: "press", params: built };
};

const select: Builder = (params, render) => {
  const raw = params["values"] !== undefined ? params["values"] : params["value"];
  const values = render(raw ?? null);
  if (values === null || values === undefined) {
    throw new ActionError("select requires a 'value' or 'values'.");
  }
  return { op: "select", params: { ...target(params, render), values } };
};

const hover: Builder = (params, render) => ({ op: "hover", params: target(params, render) });

const scroll: Builder = (params, render) => {
  if (params["selector"]) return { op: "scroll", params: target(params, render) };
  return {
    op: "scroll",
    params: {
      dx: Number(render(params["dx"] ?? 0)) || 0,
      dy: Number(render(params["dy"] ?? 0)) || 0,
    },
  };
};

/** `"fail:CODE"` becomes `CODE`; anything else names no code (`bridge.failure_code`). */
export function failureCode(onTimeout: unknown): string | undefined {
  if (typeof onTimeout !== "string" || !onTimeout.startsWith("fail:")) return undefined;
  const code = onTimeout.slice("fail:".length);
  return code === "" ? undefined : code;
}

const waitFor: Builder = (params, render) => {
  const selector = asText(render(params["selector"] ?? ""));
  if (selector === "") throw new ActionError("wait_for requires a 'selector'.");
  const built: Params = {
    selector,
    selector_type: (asText(render(params["selector_type"] ?? "css")) || "css").toLowerCase(),
    state: asText(render(params["state"] ?? "visible")) || "visible",
  };
  const code = failureCode(render(params["on_timeout"] ?? null));
  if (code !== undefined) built["fail_code"] = code;
  return { op: "wait_for", params: built };
};

/**
 * Render an `extract` spec the way `bridge.py` renders it: the selectors and the `as` of each
 * output and of each record field, and nothing else.
 *
 * Rendering the whole map instead would also render `attr`, `item` and `selector_type`, which the
 * Python engine takes verbatim — a divergence nobody would notice until a Blueprint used a template
 * in one of them.
 */
function renderExtractSpec(outputs: Params, render: Renderer): Params {
  const rendered: Params = {};
  for (const [name, raw] of Object.entries(outputs)) {
    const spec = { ...((raw ?? {}) as Params) };
    if (spec["selector"] !== undefined) spec["selector"] = render(spec["selector"]);
    if (spec["as"] !== undefined) spec["as"] = render(spec["as"]);
    if (spec["each"] !== undefined) spec["each"] = render(spec["each"]);

    const fields = spec["fields"];
    if (fields !== null && typeof fields === "object" && !Array.isArray(fields)) {
      const renderedFields: Params = {};
      for (const [field, rawField] of Object.entries(fields as Params)) {
        const fieldSpec = { ...((rawField ?? {}) as Params) };
        if (fieldSpec["selector"] !== undefined) fieldSpec["selector"] = render(fieldSpec["selector"]);
        if (fieldSpec["as"] !== undefined) fieldSpec["as"] = render(fieldSpec["as"]);
        renderedFields[field] = fieldSpec;
      }
      spec["fields"] = renderedFields;
    }
    rendered[name] = spec;
  }
  return rendered;
}

const extract: Builder = (params, render) => {
  const outputs = params["outputs"];
  const map = outputs !== null && typeof outputs === "object" && !Array.isArray(outputs)
    ? (outputs as Params)
    : {};
  return { op: "extract", params: { outputs: renderExtractSpec(map, render) } };
};

/** Actions the injected agent performs. Navigation is the host's, and is dispatched by the driver. */
export const AGENT_ACTIONS: Readonly<Record<string, Builder>> = {
  click,
  fill,
  type,
  press,
  select,
  hover,
  scroll,
  wait_for: waitFor,
  extract,
};
