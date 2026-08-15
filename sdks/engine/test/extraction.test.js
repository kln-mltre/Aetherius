/**
 * Extraction: the JSONPath subset, the `where` predicate, and HTML without a DOM.
 *
 * Two families of case matter as much as the nominal ones — the **declared limits** (a construct
 * outside the subset must fail loudly, never return a partial result) and the **escape attempts**
 * on `where`, which must be refused before anything is evaluated.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { ExtractionError } from "../dist/errors.js";
import {
  decodeUtf8,
  dispatchExtract,
  extractHtml,
  extractJson,
  jsonPathFind,
  resolveCharset,
} from "../dist/extraction/index.js";

function failure(run) {
  try {
    run();
  } catch (error) {
    assert.ok(error instanceof ExtractionError, `unexpected error: ${error}`);
    return error.message;
  }
  return assert.fail("expected an ExtractionError");
}

const USERS = JSON.stringify([
  { id: 1, name: "Ada", tags: ["a"] },
  { id: 2, name: "Alan", tags: [] },
]);

// ── JSONPath ─────────────────────────────────────────────────────────────────

test("the supported JSONPath constructs match jsonpath-ng", () => {
  const data = { headers: { "Accept-Language": "fr" }, items: [{ id: 1 }, { id: 2 }] };
  assert.deepEqual(jsonPathFind("$", data), [data]);
  assert.deepEqual(jsonPathFind("$.items[*].id", data), [1, 2]);
  assert.deepEqual(jsonPathFind("$.headers.'Accept-Language'", data), ["fr"]);
  assert.deepEqual(jsonPathFind("$['headers']['Accept-Language']", data), ["fr"]);
  assert.deepEqual(jsonPathFind("$..id", data), [1, 2]);
  assert.deepEqual(jsonPathFind("$.items[-1]", data), [{ id: 2 }]);
  assert.deepEqual(jsonPathFind("$.items[0:1]", data), [{ id: 1 }]);
  // Python's slice semantics, defaults included: with a negative step the bounds flip.
  assert.deepEqual(jsonPathFind("$[3:0:-1]", [1, 2, 3, 4, 5]), [4, 3, 2]);
  assert.deepEqual(jsonPathFind("$[::-1]", [1, 2, 3]), [3, 2, 1]);
  assert.deepEqual(jsonPathFind("$[-3:-1]", [1, 2, 3, 4, 5]), [3, 4]);
  assert.deepEqual(jsonPathFind("$[10:20]", [1, 2]), []);
  // A relative path, the form `fields` uses.
  assert.deepEqual(jsonPathFind("id", { id: 7 }), [7]);
});

test("a path that matches nothing yields nothing, it does not raise", () => {
  assert.deepEqual(jsonPathFind("$.missing", { a: 1 }), []);
  assert.deepEqual(jsonPathFind("$.items[5]", { items: [] }), []);
});

test("a list operator applied to a non-list behaves as jsonpath-ng does", () => {
  // Nonsense usage, but the two engines must still agree on it. `[*]` is a full slice, so a
  // non-list passes through as a one-element list; `.*` is a field access, so it yields nothing.
  assert.deepEqual(jsonPathFind("$[*]", { a: 1 }), [{ a: 1 }]);
  assert.deepEqual(jsonPathFind("$[*]", 7), [7]);
  assert.deepEqual(jsonPathFind("$[*]", null), []);
  assert.deepEqual(jsonPathFind("$[0:2]", { a: 1 }), [{ a: 1 }]);
  assert.deepEqual(jsonPathFind("$[1:]", { a: 1 }), []);
  assert.deepEqual(jsonPathFind("$.*", [1, 2]), []);
  assert.deepEqual(jsonPathFind("$.*", { a: 1, b: 2 }), [1, 2]);
});

test("indexing something unindexable follows jsonpath-ng, error included", () => {
  // `if datum.value and len(datum.value) > index` — a falsy container yields nothing, an object
  // with too few keys yields nothing, and anything else gets as far as raising.
  assert.deepEqual(jsonPathFind("$[0]", {}), []);
  assert.deepEqual(jsonPathFind("$[0]", null), []);
  assert.deepEqual(jsonPathFind("$[5]", { a: 1 }), []);
  assert.deepEqual(jsonPathFind("$[0]", "abc"), ["a"]);
  assert.match(failure(() => jsonPathFind("$[0]", { a: 1 })), /cannot take element/);
  assert.match(failure(() => jsonPathFind("$[0]", 7)), /cannot take element/);
  assert.match(failure(() => jsonPathFind("$[-5]", [1, 2])), /index out of range/);
});

test("a construct outside the subset fails loudly", () => {
  assert.match(failure(() => jsonPathFind("$[?(@.id > 1)]", [])), /filter expressions/);
  assert.match(failure(() => jsonPathFind("$['a','b']", {})), /unions/);
  assert.match(failure(() => jsonPathFind("$.items.`len`", {})), /Invalid JSONPath/);
  // `..*` is the one construct where jsonpath-ng's shape is not the obvious one — it does not
  // descend into list elements. Refused by name rather than reproduced from guesswork.
  assert.match(failure(() => jsonPathFind("$..*", {})), /recursive descent onto '\*'/);
});

// ── JSON extraction ──────────────────────────────────────────────────────────

test("an extraction always yields a list, even for a single match", () => {
  const body = JSON.stringify({ title: "hello", completed: false });
  assert.deepEqual(extractJson(body, { title: { from: "json", path: "$.title" } }), {
    title: ["hello"],
  });
});

test("fields map to relative paths, with zero, one and several matches", () => {
  const body = JSON.stringify([{ id: 1, tags: ["a", "b"] }]);
  const extracted = extractJson(body, {
    rows: {
      from: "json",
      path: "$[*]",
      fields: { id: "$.id", missing: "$.nope", tags: "$.tags[*]" },
    },
  });
  assert.deepEqual(extracted, { rows: [{ id: 1, missing: null, tags: ["a", "b"] }] });
});

test("a malformed body is reported as such", () => {
  assert.match(
    failure(() => extractJson("{not json", { x: { from: "json", path: "$" } })),
    /Cannot parse JSON response body/,
  );
});

// ── The where predicate ──────────────────────────────────────────────────────

test("where filters the matched items", () => {
  const extracted = extractJson(USERS, {
    users: { from: "json", path: "$[*]", where: "item.name != 'Alan'", fields: { id: "$.id" } },
  });
  assert.deepEqual(extracted, { users: [{ id: 1 }] });
});

test("where accepts boolean logic and identity", () => {
  const body = JSON.stringify([{ a: 1, b: null }, { a: 2, b: null }]);
  const spec = (where) => ({ rows: { from: "json", path: "$[*]", where } });
  assert.equal(extractJson(body, spec("item.a > 1 and item.b is None")).rows.length, 1);
  assert.equal(extractJson(body, spec("not item.a == 1")).rows.length, 1);
});

test("where on an absent field raises, it does not silently drop the item", () => {
  // Python wraps the item in a SimpleNamespace, so `item.missing` is an AttributeError.
  const message = failure(() =>
    extractJson(USERS, { users: { from: "json", path: "$[*]", where: "item.missing == 1" } }),
  );
  assert.match(message, /Error evaluating where expression/);
});

test("where refuses everything Python's AST allowlist refuses", () => {
  const reject = (where) =>
    failure(() => extractJson(USERS, { u: { from: "json", path: "$[*]", where } }));

  assert.match(reject("item.__class__ == 1"), /Disallowed dunder attribute '__class__'/);
  assert.match(reject("__import__ == 1"), /Disallowed dunder name '__import__'/);
  assert.match(reject("open('/etc/passwd') == 1"), /function calls/);
  assert.match(reject("item['id'] == 1"), /subscripting/);
  assert.match(reject("item.id | length == 1"), /filters/);
  assert.match(reject("item.id in [1, 2]"), /list literals/);
  assert.match(reject("item.id + 1 == 2"), /arithmetic/);
  assert.match(reject("1 if item.id else 2"), /inline conditionals/);
  assert.match(reject("item.id =="), /Invalid where expression/);
});

// ── HTML extraction ──────────────────────────────────────────────────────────

const PAGE = `<html><body>
  <div class="quote"><span class="text">Hello <b>bold</b> world</span><small class="author">Ada</small></div>
  <div class="quote"><span class="text">Second</span><small class="author">Alan</small></div>
  <a class="next" href="/page/2/" data-id="7">Next</a>
</body></html>`;

test("::text selects the element's own text nodes, one result each", () => {
  const extracted = extractHtml(PAGE, {
    quotes: { from: "html", selector: "div.quote span.text::text" },
    authors: { from: "html", selector: "div.quote small.author::text" },
  });
  // "Hello " and " world" are two text nodes around <b>, exactly as parsel reports them.
  assert.deepEqual(extracted.quotes, ["Hello ", " world", "Second"]);
  assert.deepEqual(extracted.authors, ["Ada", "Alan"]);
});

test("without a pseudo-element a match renders as its outer HTML", () => {
  const extracted = extractHtml(PAGE, { links: { from: "html", selector: "a.next" } });
  assert.deepEqual(extracted.links, ['<a class="next" href="/page/2/" data-id="7">Next</a>']);
});

test("attributes are read by the attr field or the ::attr pseudo-element", () => {
  const extracted = extractHtml(PAGE, {
    href: { from: "html", selector: "a.next", attr: "href" },
    id: { from: "html", selector: "a.next::attr(data-id)" },
    absent: { from: "html", selector: "a.next", attr: "nope" },
  });
  assert.deepEqual(extracted.href, ["/page/2/"]);
  assert.deepEqual(extracted.id, ["7"]);
  assert.deepEqual(extracted.absent, [""], "a missing attribute is the empty string, as in parsel");
});

test("multiple: false yields the first match or null", () => {
  const extracted = extractHtml(PAGE, {
    first: { from: "html", selector: "small.author::text", multiple: false },
    none: { from: "html", selector: "h1::text", multiple: false },
  });
  assert.equal(extracted.first, "Ada");
  assert.equal(extracted.none, null);
});

test("xpath is refused with a message that names the limit", () => {
  const message = failure(() =>
    extractHtml(PAGE, { x: { from: "html", selector: "//p", selector_type: "xpath" } }),
  );
  assert.match(message, /no XPath engine/);
});

test("an invalid CSS selector is reported, not swallowed", () => {
  assert.match(
    failure(() => extractHtml(PAGE, { x: { from: "html", selector: "div[" } })),
    /Invalid css selector 'div\['/,
  );
});

// ── Dispatch ─────────────────────────────────────────────────────────────────

test("dispatchExtract splits the two dialects and applies the same defaults as Python", () => {
  const extracted = dispatchExtract(USERS, { ids: { path: "$[*].id" } });
  assert.deepEqual(extracted, { ids: [1, 2] });

  const both = dispatchExtract(PAGE, {
    authors: { from: "html", selector: "small.author::text" },
  });
  assert.deepEqual(both.authors, ["Ada", "Alan"]);
});

test("'multiple' is tested for truthiness, as Python does", () => {
  // `multiple: 0` means "single" on the Python engine; `!== false` here would answer a list.
  const spec = (multiple) => ({ a: { from: "html", selector: "small.author::text", multiple } });
  assert.equal(dispatchExtract(PAGE, spec(0)).a, "Ada");
  assert.equal(dispatchExtract(PAGE, spec("")).a, "Ada");
  assert.deepEqual(dispatchExtract(PAGE, spec(1)).a, ["Ada", "Alan"]);
});

// ── Le corps en texte ────────────────────────────────────────────────────────

/** The dialect through its real entry point: bytes plus the header the client would have read. */
function text(bytes, contentType) {
  const extracted = dispatchExtract("", { raw: { from: "text" } }, { bytes, contentType });
  return extracted.raw;
}

const bytesOf = (value, encoding = "utf8") => new Uint8Array(Buffer.from(value, encoding));

test("a text extraction renders the whole decoded body", () => {
  assert.equal(text(bytesOf("BEGIN:VCALENDAR\r\nSUMMARY:Noël\r\n"), "text/calendar; charset=utf-8"),
    "BEGIN:VCALENDAR\r\nSUMMARY:Noël\r\n");
});

test("a declared charset is honoured, and a mislabelled body mojibakes identically", () => {
  assert.equal(text(bytesOf("Prénom;Zoé", "latin1"), "text/csv; charset=ISO-8859-1"), "Prénom;Zoé");
  // UTF-8 bytes served as latin-1: the mojibake is the correct answer, and the Python engine
  // produces the same one. Guessing the encoding would make the two differ on real sources.
  assert.equal(text(bytesOf("Prénom"), "text/csv; charset=iso-8859-1"), "PrÃ©nom");
});

test("windows-1252 maps its own window, undefined bytes included", () => {
  assert.equal(text(new Uint8Array([0x80, 0x20, 0x99, 0x20, 0x8d]), "text/plain; charset=windows-1252"),
    "€ ™ �");
});

test("no charset, an unknown label, or no header at all mean UTF-8", () => {
  assert.equal(text(bytesOf("café")), "café");
  assert.equal(text(bytesOf("café"), "text/calendar"), "café");
  assert.equal(text(bytesOf("café"), "text/plain; charset=shift_jis"), "café");
});

test("an empty body is an empty string, not null", () => {
  assert.equal(text(new Uint8Array(0), "text/plain"), "");
});

test("a binary body is replaced, never thrown", () => {
  // An image means the Blueprint aimed at the wrong source; the engine is not the one who can say so.
  assert.equal(text(new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0xff, 0xfe]), "image/png"),
    "�PNG\r\n\x1a\n��");
});

test("a BOM is kept, as the Python codec keeps it", () => {
  assert.equal(text(new Uint8Array([0xef, 0xbb, 0xbf, 0x42]), "text/plain"), "﻿B");
});

test("invalid UTF-8 replaces one character per maximal subpart", () => {
  // Values computed with CPython's errors="replace" and copied here: the count is observable, and
  // "close enough" would mean two engines rendering a different string for the same broken body.
  const cases = [
    [[0xff], "�"],
    [[0xff, 0xfe], "��"],
    [[0xc3], "�"],
    [[0xc3, 0x28], "�("],
    [[0xe0, 0xa0], "�"],
    [[0xf0, 0x9f, 0x98], "�"],
    [[0xf0, 0x9f, 0x98, 0x81], "\u{1F601}"],
    [[0xc0, 0xaf], "��"],
    [[0xed, 0xa0, 0x80], "���"],
    [[0xf4, 0x90, 0x80, 0x80], "����"],
    [[0xe0, 0x80, 0xaf], "���"],
  ];
  for (const [raw, expected] of cases) {
    assert.equal(decodeUtf8(new Uint8Array(raw)), expected, `bytes ${raw}`);
  }
});

test("a long body crosses the chunk boundary unharmed", () => {
  // The decoders build the string in chunks; a body of a few hundred kilobytes is the normal size
  // of a year of iCal, and `fromCharCode` over the whole of it would blow the stack.
  const long = "é".repeat(20_000);
  assert.equal(text(bytesOf(long)), long);
  assert.equal(text(bytesOf(long, "latin1"), "text/plain; charset=latin-1"), long);
});

test("the charset parameter is read, not the media type", () => {
  assert.equal(resolveCharset(undefined), "utf-8");
  assert.equal(resolveCharset("text/plain"), "utf-8");
  assert.equal(resolveCharset('text/plain; charset="ISO-8859-1"'), "iso-8859-1");
  assert.equal(resolveCharset("text/plain;charset=latin-1"), "iso-8859-1");
  assert.equal(resolveCharset("text/plain; charset = Windows-1252 "), "cp1252");
  assert.equal(resolveCharset("text/plain; boundary=charset=x"), "utf-8");
});

test("without bytes, the text dialect renders the string it was given", () => {
  // The path the conformance `extraction` cases take: no response, so nothing to re-decode.
  assert.equal(dispatchExtract("BEGIN:VCALENDAR", { raw: { from: "text" } }).raw, "BEGIN:VCALENDAR");
});
