/**
 * The `as:` vocabulary — a data contract, mirror of `acts/continuum/bridge.py`.
 *
 * A gap here does not break a run: it produces **wrong data**, which is the worst kind of failure.
 * So the details are reproduced deliberately, and each one is a decision the Python engine already
 * made:
 *
 *   - a number is pulled out by regular expression, decimal comma converted to a dot, and returned
 *     as an integer when it is integral;
 *   - text is trimmed;
 *   - `count` counts every match — it does not read the first one;
 *   - `list` reads every match, `item` deciding the type of each (`text` by default);
 *   - records (`each` + `fields`) read each field with a selector resolved **inside** its container.
 *
 * One reproduction is easy to mistake for a bug: inside an `extract` spec, `selector_type` only
 * ever switches to XPath. Anything else is read as CSS, because that is what `_resolve` does on the
 * Python side — including for `selector_type: "text"`. The container and field selectors of a
 * record are always CSS there too, and are here.
 */

import { OpError, selectorError } from "./errors.js";
import { innerTextOf, matchAll, matchFirst, type Target } from "./locator.js";
import { waitFor } from "./waiting.js";

const NUMBER_RE = /-?\d+(?:[.,]\d+)?/;

type Spec = Record<string, unknown>;

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** `_resolve`: within an extraction, only XPath is special; everything else is CSS. */
function specTarget(selector: string, spec: Spec): Target {
  const raw = spec["selector_type"];
  const kind = typeof raw === "string" ? raw.toLowerCase() : "css";
  return { selector, selectorType: kind === "xpath" ? "xpath" : "css" };
}

/** First number in *source*, integer when integral, `null` when there is none. */
export function coerceNumber(source: string | null | undefined): number | null {
  if (source === null || source === undefined || source === "") return null;
  const match = NUMBER_RE.exec(source);
  if (match === null) return null;
  const value = Number(match[0].replace(",", "."));
  return Number.isNaN(value) ? null : value;
}

/** `text` is `inner_text().strip()` on the Python side: trimmed, never collapsed. */
function elementText(element: Element): string {
  return innerTextOf(element).trim();
}

/** Read one already-resolved element as *as_*. */
function readValue(element: Element, as: string, spec: Spec): unknown {
  switch (as) {
    case "text":
      return elementText(element);
    case "number":
      return coerceNumber(elementText(element));
    case "html":
      return element.innerHTML;
    case "attr": {
      const attribute = spec["attr"];
      if (typeof attribute !== "string" || attribute === "") {
        throw new OpError("extract 'as: attr' requires an 'attr' name.");
      }
      return element.getAttribute(attribute);
    }
    default:
      throw new OpError(
        `Unknown extract type ${JSON.stringify(as)} (text, number, html, attr, list or count).`,
      );
  }
}

/**
 * Wait for a single-value read's element to show up.
 *
 * Playwright's `.first.inner_text()` waits for the element to be attached before reading, so a
 * value that arrives with the page still rendering is read rather than missed. Reproduced here
 * because it is real behaviour a Blueprint depends on — not merely an implementation detail of the
 * other engine.
 */
async function resolveOne(target: Target, timeoutMs: number): Promise<Element> {
  return waitFor(
    () => matchFirst(target),
    timeoutMs,
    () => `extract: no element matched ${JSON.stringify(target.selector)}`,
  );
}

function readRecords(spec: Spec): Record<string, unknown>[] {
  const each = text(spec["each"]);
  if (each === "") throw new OpError("extract records require an 'each' container selector.");
  const fields = spec["fields"];
  if (fields === null || typeof fields !== "object" || Object.keys(fields).length === 0) {
    throw new OpError("extract records require a non-empty 'fields' map.");
  }

  // No waiting: `page.locator(each).all()` returns at once on the Python side, so a page with no
  // container yields an empty list rather than an error — on both engines.
  const containers = matchAll({ selector: each, selectorType: "css" });

  const records: Record<string, unknown>[] = [];
  for (const container of containers) {
    const record: Record<string, unknown> = {};
    for (const [name, raw] of Object.entries(fields as Record<string, unknown>)) {
      const fieldSpec = (raw ?? {}) as Spec;
      const selector = text(fieldSpec["selector"]);
      if (selector === "") {
        throw new OpError(`extract record field ${JSON.stringify(name)} requires a 'selector'.`);
      }
      // No waiting inside a container: the container is already in the document, so a field that
      // is not there will not appear later. Playwright waits here only because it always does;
      // the outcome is the same failure, reported at once and with a message that names the field.
      const element = matchFirst({ selector, selectorType: "css" }, container);
      if (element === null) {
        throw selectorError(
          `extract record field ${JSON.stringify(name)}: no element matched ` +
            `${JSON.stringify(selector)} inside ${JSON.stringify(each)}`,
        );
      }
      const as = (text(fieldSpec["as"]) || "text").toLowerCase();
      record[name] = readValue(element, as, fieldSpec);
    }
    records.push(record);
  }
  return records;
}

/** Run an `extract` step's `outputs` map against the live DOM. */
export async function extract(
  outputs: Record<string, unknown>,
  timeoutMs: number,
): Promise<Record<string, unknown>> {
  const result: Record<string, unknown> = {};

  for (const [name, raw] of Object.entries(outputs)) {
    const spec = (raw ?? {}) as Spec;

    if (Object.prototype.hasOwnProperty.call(spec, "each")) {
      result[name] = readRecords(spec);
      continue;
    }

    const selector = text(spec["selector"]);
    if (selector === "") {
      throw new OpError(`extract output ${JSON.stringify(name)} requires a 'selector'.`);
    }
    const as = (text(spec["as"]) || "text").toLowerCase();
    const target = specTarget(selector, spec);

    if (as === "count") {
      // Counting never waits and never fails: zero is an answer, and a Blueprint uses it to decide.
      result[name] = matchAll(target).length;
      continue;
    }
    if (as === "list") {
      const item = (text(spec["item"]) || "text").toLowerCase();
      result[name] = matchAll(target).map((element) => readValue(element, item, spec));
      continue;
    }
    result[name] = readValue(await resolveOne(target, timeoutMs), as, spec);
  }

  return result;
}
