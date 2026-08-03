/**
 * The operation table: one Blueprint action, one effect on the page.
 *
 * Mirror of `acts/continuum/actions.py`, but where that file delegates to Playwright — which
 * dispatches *trusted* events from outside the page — this one has only the DOM. Three consequences
 * are written into the code below rather than discovered later:
 *
 *   - **a click is both a sequence and a `click()` call.** Synthetic `mousedown`/`mouseup` reach
 *     JavaScript handlers but do not trigger the default action of an `<a>` or a submit button;
 *     `element.click()` triggers the default action but skips the pointer sequence some UI
 *     frameworks listen for. Doing both is the only honest way to cover real pages.
 *   - **setting `value` is not enough for a controlled field.** React installs its own value
 *     tracker; writing the property directly leaves it thinking nothing changed, and the framework
 *     restores the old value on the next render. Going through the native setter is what makes
 *     `fill` work on the portals this milestone exists for.
 *   - **a synthetic key does not submit a form.** `Enter` therefore also calls `requestSubmit()`,
 *     which is what a browser would have done. Documented as a limit, not left as a surprise.
 */

import { OpError } from "./errors.js";
import { describe, matchFirst, matchStrict, targetOf } from "./locator.js";
import { extract } from "./read.js";
import { parseState, satisfies, sleep, waitActionable, waitFor } from "./waiting.js";

type Params = Record<string, unknown>;

export type Operation = (params: Params, timeoutMs: number) => Promise<Record<string, unknown>>;

/** Resolve the one element an action targets, auto-waiting until it is worth acting on. */
async function actionable(params: Params, timeoutMs: number): Promise<Element> {
  const target = targetOf(params);
  return waitActionable(() => matchStrict(target), timeoutMs, () => describe(target));
}

function asString(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "string" ? value : String(value);
}

function scrollIntoView(element: Element): void {
  if (typeof element.scrollIntoView === "function") {
    element.scrollIntoView({ block: "center", inline: "center" });
  }
}

function pointerEvent(element: Element, type: string): void {
  const rect = element.getBoundingClientRect();
  const init: MouseEventInit = {
    bubbles: true,
    cancelable: true,
    composed: true,
    clientX: rect.left + rect.width / 2,
    clientY: rect.top + rect.height / 2,
  };
  // `PointerEvent` is not universal in older WebViews; a MouseEvent carries the same coordinates
  // and every handler that matters listens for one of the two.
  const Ctor = (globalThis as { PointerEvent?: typeof MouseEvent }).PointerEvent ?? MouseEvent;
  element.dispatchEvent(new Ctor(type, init));
}

function focusIfPossible(element: Element): void {
  const focusable = element as HTMLElement;
  if (typeof focusable.focus === "function") focusable.focus();
}

/**
 * Write *value* through the property setter the framework installed, then announce it.
 *
 * Without the prototype setter a controlled React input silently reverts. This is the single most
 * valuable line of the file for the portals Aetherius targets.
 */
function setFieldValue(element: Element, value: string): void {
  const field = element as HTMLInputElement;
  const prototype = Object.getPrototypeOf(field) as object;
  const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
  if (descriptor?.set !== undefined) descriptor.set.call(field, value);
  else field.value = value;
  field.dispatchEvent(new Event("input", { bubbles: true }));
  field.dispatchEvent(new Event("change", { bubbles: true }));
}

/** Best-effort key metadata: enough for handlers that read `key`, `code` or `keyCode`. */
function keyInit(key: string): KeyboardEventInit {
  const single = key.length === 1;
  const code = single ? (/[a-zA-Z]/.test(key) ? `Key${key.toUpperCase()}` : "") : key;
  const which = single ? key.charCodeAt(0) : KEY_CODES[key];
  return {
    bubbles: true,
    cancelable: true,
    composed: true,
    key,
    code,
    ...(which !== undefined ? { keyCode: which, charCode: single ? which : 0, which } : {}),
  } as KeyboardEventInit;
}

const KEY_CODES: Record<string, number> = {
  Backspace: 8,
  Tab: 9,
  Enter: 13,
  Escape: 27,
  Space: 32,
  PageUp: 33,
  PageDown: 34,
  End: 35,
  Home: 36,
  ArrowLeft: 37,
  ArrowUp: 38,
  ArrowRight: 39,
  ArrowDown: 40,
  Delete: 46,
};

function sendKey(element: Element, key: string): void {
  element.dispatchEvent(new KeyboardEvent("keydown", keyInit(key)));
  if (key.length === 1) element.dispatchEvent(new KeyboardEvent("keypress", keyInit(key)));
  element.dispatchEvent(new KeyboardEvent("keyup", keyInit(key)));
}

/** `Enter` in a form field submits, because that is what a browser does with a real key press. */
function submitOnEnter(element: Element, key: string): void {
  if (key !== "Enter") return;
  const form = (element as HTMLInputElement).form ?? element.closest("form");
  if (form === null) return;
  if (typeof form.requestSubmit === "function") form.requestSubmit();
  else form.submit();
}

async function opClick(params: Params, timeoutMs: number): Promise<Record<string, unknown>> {
  const element = await actionable(params, timeoutMs);
  scrollIntoView(element);
  pointerEvent(element, "pointerdown");
  pointerEvent(element, "mousedown");
  focusIfPossible(element);
  pointerEvent(element, "pointerup");
  pointerEvent(element, "mouseup");
  (element as HTMLElement).click();
  return {};
}

async function opFill(params: Params, timeoutMs: number): Promise<Record<string, unknown>> {
  const element = await actionable(params, timeoutMs);
  focusIfPossible(element);
  setFieldValue(element, asString(params["value"]));
  return {};
}

async function opType(params: Params, timeoutMs: number): Promise<Record<string, unknown>> {
  const element = await actionable(params, timeoutMs);
  const raw = params["text"] !== undefined ? params["text"] : params["value"];
  const wanted = asString(raw);
  const delayRaw = params["delay_ms"];
  const delay = typeof delayRaw === "number" && Number.isFinite(delayRaw) ? delayRaw : 0;

  focusIfPossible(element);
  const field = element as HTMLInputElement;
  // Character by character, because the whole point of `type` over `fill` is fields that react to
  // each keystroke (autocompletes, masked inputs, live validation).
  for (const character of wanted) {
    element.dispatchEvent(new KeyboardEvent("keydown", keyInit(character)));
    element.dispatchEvent(new KeyboardEvent("keypress", keyInit(character)));
    setFieldValue(field, (field.value ?? "") + character);
    element.dispatchEvent(new KeyboardEvent("keyup", keyInit(character)));
    if (delay > 0) await sleep(delay);
  }
  return {};
}

async function opPress(params: Params, timeoutMs: number): Promise<Record<string, unknown>> {
  const key = asString(params["key"]);
  if (key === "") throw new OpError("press requires a 'key'.");

  let element: Element;
  if (typeof params["selector"] === "string" && params["selector"] !== "") {
    element = await actionable(params, timeoutMs);
    focusIfPossible(element);
  } else {
    element = document.activeElement ?? document.body;
  }
  sendKey(element, key);
  submitOnEnter(element, key);
  return {};
}

async function opSelect(params: Params, timeoutMs: number): Promise<Record<string, unknown>> {
  const raw = params["values"] !== undefined ? params["values"] : params["value"];
  if (raw === undefined || raw === null) throw new OpError("select requires a 'value' or 'values'.");
  const wanted = (Array.isArray(raw) ? raw : [raw]).map(asString);

  const element = (await actionable(params, timeoutMs)) as HTMLSelectElement;
  const options = Array.prototype.slice.call(element.options ?? []) as HTMLOptionElement[];
  if (options.length === 0) throw new OpError("select requires a <select> element with options.");

  const chosen: string[] = [];
  for (const option of options) {
    // Value first, label as a fallback: that is the order Playwright's `select_option` uses when
    // handed plain strings.
    const selected = wanted.indexOf(option.value) !== -1 || wanted.indexOf(option.label) !== -1;
    option.selected = selected;
    if (selected) chosen.push(option.value);
  }
  if (chosen.length === 0) {
    throw new OpError(`select: no option matches ${JSON.stringify(wanted)}`);
  }
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
  return {};
}

async function opHover(params: Params, timeoutMs: number): Promise<Record<string, unknown>> {
  const element = await actionable(params, timeoutMs);
  scrollIntoView(element);
  pointerEvent(element, "pointerover");
  pointerEvent(element, "mouseover");
  pointerEvent(element, "pointermove");
  pointerEvent(element, "mousemove");
  return {};
}

async function opScroll(params: Params, timeoutMs: number): Promise<Record<string, unknown>> {
  if (typeof params["selector"] === "string" && params["selector"] !== "") {
    const target = targetOf(params);
    const element = await waitFor(
      () => matchFirst(target),
      timeoutMs,
      () => `scroll: ${describe(target)} never appeared`,
    );
    scrollIntoView(element);
    return {};
  }
  const dx = Number(params["dx"] ?? 0) || 0;
  const dy = Number(params["dy"] ?? 0) || 0;
  window.scrollBy(dx, dy);
  return {};
}

async function opWaitFor(params: Params, timeoutMs: number): Promise<Record<string, unknown>> {
  const target = targetOf(params);
  const state = parseState(params["state"]);
  const code = typeof params["fail_code"] === "string" ? params["fail_code"] : undefined;

  await waitFor(
    () => {
      // Waiting is about presence, so several matches are normal and must not trip strict mode.
      const element = matchFirst(target);
      return satisfies(element, state) ? true : null;
    },
    timeoutMs,
    () => `wait_for timed out for selector ${JSON.stringify(target.selector)}`,
    code,
  );
  return {};
}

async function opExtract(params: Params, timeoutMs: number): Promise<Record<string, unknown>> {
  const outputs = params["outputs"];
  if (outputs === null || typeof outputs !== "object" || Array.isArray(outputs)) return {};
  return extract(outputs as Record<string, unknown>, timeoutMs);
}

/** The closed table. `protocol.ts` names the same operations; the two must not drift. */
export const OPERATIONS: Record<string, Operation> = {
  click: opClick,
  fill: opFill,
  type: opType,
  press: opPress,
  select: opSelect,
  hover: opHover,
  scroll: opScroll,
  wait_for: opWaitFor,
  extract: opExtract,
};
