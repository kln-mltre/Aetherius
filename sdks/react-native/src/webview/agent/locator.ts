/**
 * Resolving a Blueprint target into elements, in decreasing order of usefulness: CSS, XPath, text.
 *
 * The part that matters is not the lookup, it is the **strict mode**. Playwright treats several
 * matches as an error rather than an implicit "take the first", and reproducing that is what turns
 * a Blueprint gone ambiguous into a readable failure instead of a click on the wrong button. It is
 * not uniform, and the asymmetry is deliberate on both engines:
 *
 *   - acting (`click`, `fill`, …) is **strict** — acting on an ambiguous target is a mistake;
 *   - waiting and reading take the **first** match — presence and reading are not ambiguous, and a
 *     selector matching several elements is normal there (`bridge.py` uses `.first`).
 */

import { OpError, selectorError } from "./errors.js";

export type SelectorType = "css" | "xpath" | "text";

export interface Target {
  readonly selector: string;
  readonly selectorType: SelectorType;
}

/**
 * The rendered text of an element.
 *
 * `innerText` rather than `textContent`, because Playwright's `inner_text()` is what the Python
 * engine reads: it respects rendering, so a hidden element contributes nothing. The fallback exists
 * for DOM implementations without layout — the test double supplies it, a real WebView never needs
 * it — and keeps the agent single-path.
 */
export function innerTextOf(element: Element): string {
  const inner = (element as HTMLElement).innerText;
  return typeof inner === "string" ? inner : (element.textContent ?? "");
}

/** Text with whitespace collapsed: what *matching* compares, as opposed to what reading returns. */
export function elementText(element: Element): string {
  return innerTextOf(element).replace(/\s+/g, " ").trim();
}

function cssMatches(root: ParentNode, selector: string): Element[] {
  try {
    return Array.prototype.slice.call(root.querySelectorAll(selector)) as Element[];
  } catch {
    throw new OpError(`invalid CSS selector ${JSON.stringify(selector)}`);
  }
}

function xpathMatches(root: Node, expression: string): Element[] {
  // A Blueprint may carry Playwright's `xpath=` prefix; the Python engine adds it when missing, so
  // both spellings reach this engine and both must work.
  const expr = expression.indexOf("xpath=") === 0 ? expression.slice("xpath=".length) : expression;
  let snapshot: XPathResult;
  try {
    snapshot = document.evaluate(
      expr,
      root,
      null,
      7 /* XPathResult.ORDERED_NODE_SNAPSHOT_TYPE */,
      null,
    );
  } catch {
    throw new OpError(`invalid XPath expression ${JSON.stringify(expr)}`);
  }
  const found: Element[] = [];
  for (let index = 0; index < snapshot.snapshotLength; index += 1) {
    const node = snapshot.snapshotItem(index);
    if (node !== null && node.nodeType === 1) found.push(node as Element);
  }
  return found;
}

/**
 * Match by visible text, an approximation of Playwright's `get_by_text`.
 *
 * Reproduced: whitespace normalisation, case-insensitive substring matching, and buttons matched by
 * their `value` rather than their text. Not reproduced: the shadow-DOM traversal and the exact
 * layout-aware notion of "visible text". The limit is written up in docs/embedded.md — this locator
 * is the least precise of the three, which is also why it comes last.
 */
function textMatches(root: ParentNode, needle: string): Element[] {
  const wanted = needle.replace(/\s+/g, " ").trim().toLowerCase();
  const candidates = Array.prototype.slice.call(root.querySelectorAll("*")) as Element[];
  const matched = candidates.filter((element) => {
    const tag = element.tagName.toLowerCase();
    if (tag === "input") {
      const type = (element.getAttribute("type") ?? "").toLowerCase();
      if (type !== "button" && type !== "submit" && type !== "reset") return false;
      return (element.getAttribute("value") ?? "").trim().toLowerCase().indexOf(wanted) !== -1;
    }
    return elementText(element).toLowerCase().indexOf(wanted) !== -1;
  });
  // Keep only the innermost matches: an ancestor "contains" its child's text, and reporting both
  // would make every text lookup ambiguous by construction.
  return matched.filter((element) => !matched.some((other) => other !== element && element.contains(other)));
}

/** Every element *target* resolves to, in document order. */
export function matchAll(target: Target, root: ParentNode = document): Element[] {
  switch (target.selectorType) {
    case "xpath":
      return xpathMatches(root as Node, target.selector);
    case "text":
      return textMatches(root, target.selector);
    default:
      return cssMatches(root, target.selector);
  }
}

/** The first match, or `null`. What waiting and reading use. */
export function matchFirst(target: Target, root: ParentNode = document): Element | null {
  const found = matchAll(target, root);
  return found.length > 0 ? (found[0] as Element) : null;
}

/**
 * The one element *target* names, `null` when the page has none yet.
 *
 * What acting uses, and the asymmetry is deliberate: "zero" and "several" are different problems.
 * **Zero is a *not yet*** — the element may still be rendering, so the caller keeps waiting, which
 * is what Playwright does and therefore what the Python engine does. **Several is a mistake** that
 * waiting will not fix: strict mode refuses it at once rather than clicking the wrong button.
 */
export function matchStrict(target: Target, root: ParentNode = document): Element | null {
  const found = matchAll(target, root);
  if (found.length === 1) return found[0] as Element;
  if (found.length === 0) return null;
  throw selectorError(
    `${describe(target)} matched ${found.length} elements; ` +
      "acting on an ambiguous target is refused — make the selector more specific",
  );
}

export function describe(target: Target): string {
  return `${target.selectorType} selector ${JSON.stringify(target.selector)}`;
}

/** Read a target out of an operation's JSON parameters, defaulting to CSS as the Blueprint does. */
export function targetOf(params: Record<string, unknown>): Target {
  const selector = params["selector"];
  if (typeof selector !== "string" || selector === "") {
    throw new OpError("this action requires a 'selector'.");
  }
  const raw = params["selector_type"];
  const type = typeof raw === "string" && raw !== "" ? raw.toLowerCase() : "css";
  if (type !== "css" && type !== "xpath" && type !== "text") {
    throw new OpError(`Unknown selector_type ${JSON.stringify(type)} (expected css, xpath or text).`);
  }
  return { selector, selectorType: type };
}
