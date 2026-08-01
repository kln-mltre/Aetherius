/**
 * HTML extraction outside a browser, mirror of `core/extraction/html_extractor.py`.
 *
 * Vector extracts from a `fetch` response, so there is no DOM to ask: the engine parses the markup
 * itself. Rather than hand-roll a forgiving HTML parser and a CSS engine, it leans on the
 * `htmlparser2` / `css-select` stack — pure JavaScript, and free of `eval` and `new Function`, which
 * is what makes it usable under Hermes. A test guards that property
 * (`test/no-dynamic-code.test.js`); the day it fails, the fix is ours to write, not to discover on
 * a device.
 *
 * Two behaviours of `parsel` (the Python side) are reproduced here because Blueprints depend on
 * them and neither is standard CSS:
 *
 *   - `::text` selects the **direct child text nodes** of the matched element, each a separate
 *     result — `<h1>Hello <b>x</b> world</h1>::text` yields two strings, not one joined one;
 *   - without a pseudo-element and without `attr`, a match renders as its **serialised outer
 *     HTML**, which is what `Selector.getall()` returns.
 *
 * XPath has no engine here and is refused at validation time (`blueprint/portability.ts`); the
 * check below is the belt to that suspenders, for a caller that skipped the validator.
 */

import { selectAll } from "css-select";
import { isText, type AnyNode, type Element } from "domhandler";
import { getOuterHTML } from "domutils";
import { parseDocument } from "htmlparser2";

import { ExtractionError } from "../errors.js";

export interface HtmlExtractSpec {
  readonly from: "html";
  /** CSS selector, optionally suffixed with parsel's `::text` or `::attr(name)`. */
  readonly selector: string;
  readonly selector_type?: string | undefined;
  /** Attribute to read; omitted means the node's own rendering. */
  readonly attr?: string | undefined;
  /** `true` (default) yields a list, `false` the first match or `null`. */
  readonly multiple?: boolean | undefined;
}

const PSEUDO = /::\s*(text|attr\(\s*([^)\s]+)\s*\))\s*$/;

/** Run every spec against an HTML *body* and collect the results under their output names. */
export function extractHtml(
  body: string,
  specs: Readonly<Record<string, HtmlExtractSpec>>,
): Record<string, unknown> {
  let document: AnyNode;
  try {
    document = parseDocument(body);
  } catch (cause) {
    const reason = cause instanceof Error ? cause.message : String(cause);
    throw new ExtractionError(`Cannot parse HTML response body: ${reason}`);
  }

  const result: Record<string, unknown> = {};
  for (const [name, spec] of Object.entries(specs)) {
    const values = runSpec(spec, document);
    result[name] = spec.multiple === false ? (values.length > 0 ? values[0] : null) : values;
  }
  return result;
}

function runSpec(spec: HtmlExtractSpec, document: AnyNode): string[] {
  if (spec.selector_type === "xpath") {
    throw new ExtractionError(
      `Invalid xpath selector '${spec.selector}': the embedded engine has no XPath engine ` +
        "(there is no DOM outside a browser); use a CSS selector.",
    );
  }

  const pseudo = PSEUDO.exec(spec.selector);
  const query = pseudo === null ? spec.selector.trim() : spec.selector.slice(0, pseudo.index).trim();

  let nodes: Element[];
  try {
    nodes = selectAll(query.length > 0 ? query : "*", document);
  } catch (cause) {
    const reason = cause instanceof Error ? cause.message : String(cause);
    throw new ExtractionError(`Invalid css selector '${spec.selector}': ${reason}`);
  }

  if (pseudo !== null) {
    const attribute = pseudo[2];
    if (attribute !== undefined) return nodes.map((node) => node.attribs[attribute]).filter(isString);
    return nodes.flatMap(directText);
  }

  if (spec.attr !== undefined && spec.attr !== null && spec.attr !== "") {
    const attribute = spec.attr;
    return nodes.map((node) => node.attribs[attribute] ?? "");
  }

  return nodes.map((node) => getOuterHTML(node));
}

/** `::text` is `/text()`: the element's own text children, not the whole subtree's. */
function directText(node: Element): string[] {
  return node.children.filter(isText).map((child) => child.data);
}

function isString(value: string | undefined): value is string {
  return value !== undefined;
}
