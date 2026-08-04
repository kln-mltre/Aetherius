/**
 * Le format du manifeste, et l'empreinte qui le rend credible.
 *
 * Deux briques que personne ne regarde tant qu'elles marchent, et qui decident pourtant de tout le
 * jalon : un parseur **strict** (une faute de frappe ne doit pas pouvoir desactiver une garde en
 * silence) et un SHA-256 **juste** (une empreinte fausse rejetterait les bonnes livraisons, une
 * empreinte trop indulgente accepterait les mauvaises).
 *
 * L'empreinte est comparee a `node:crypto` : ecrire son propre SHA-256 n'est defendable que si on le
 * confronte a une implementation de reference, y compris sur les coins ou les deux pourraient
 * diverger (multi-octets, demi-couples de substitution).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { compareVersions, parseManifest, resolveUrl } from "../dist/delivery/manifest.js";
import { sha256Hex } from "../dist/delivery/sha256.js";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const REGISTRY = join(REPO, "examples", "mobile", "registry");

const reference = (text) => createHash("sha256").update(text, "utf8").digest("hex");

const wrap = (blueprints, extra = {}) =>
  JSON.stringify({ manifest: "1", disabled: false, blueprints, ...extra });

const ENTRY = {
  version: "2",
  url: "fix.json",
  sha256: "a".repeat(64),
};

test("a well-formed manifest reads back as declared", () => {
  const parsed = parseManifest(
    wrap(
      { "demo.thing": { ...ENTRY, min_engine: "0.4.0", disabled: true } },
      { generated_at: "2026-08-04T00:00:00Z" },
    ),
  );

  assert.equal(parsed.format, "1");
  assert.equal(parsed.generatedAt, "2026-08-04T00:00:00Z");
  assert.equal(parsed.disabled, false);
  assert.deepEqual(parsed.blueprints["demo.thing"], {
    version: "2",
    url: "fix.json",
    sha256: "a".repeat(64),
    minEngine: "0.4.0",
    disabled: true,
  });
});

test("`disabled` defaults to false, and `blueprints` may be absent", () => {
  const parsed = parseManifest(JSON.stringify({ manifest: "1" }));
  assert.equal(parsed.disabled, false);
  assert.deepEqual(parsed.blueprints, {});
});

test("the parser is strict, because a typo must not disable a guard in silence", () => {
  const refused = {
    "not JSON at all": "{ nope",
    "an array": "[]",
    "an unknown root key": wrap({}, { blueprintz: {} }),
    "an unknown entry key": wrap({ "demo.thing": { ...ENTRY, sha_256: "x" } }),
    "a missing version": wrap({ "demo.thing": { url: "fix.json", sha256: "a".repeat(64) } }),
    "a non-numeric version": wrap({ "demo.thing": { ...ENTRY, version: "2.0-beta" } }),
    "a short digest": wrap({ "demo.thing": { ...ENTRY, sha256: "abc" } }),
    "an uppercase digest": wrap({ "demo.thing": { ...ENTRY, sha256: "A".repeat(64) } }),
    "a non-boolean disabled": wrap({ "demo.thing": { ...ENTRY, disabled: "true" } }),
    "an empty url": wrap({ "demo.thing": { ...ENTRY, url: "" } }),
    // Ecrit en toutes lettres : dans un litteral JavaScript, `__proto__` fixe le prototype au lieu
    // de creer une propriete, donc `JSON.stringify` n'en produirait rien. `JSON.parse`, lui, en fait
    // une propriete ordinaire — c'est bien un nom qui peut arriver du reseau.
    "a poisoned name": `{"manifest":"1","blueprints":{"__proto__":${JSON.stringify(ENTRY)}}}`,
    "an unsupported format": JSON.stringify({ manifest: "2", blueprints: {} }),
    "a missing format": JSON.stringify({ blueprints: {} }),
  };

  for (const [what, text] of Object.entries(refused)) {
    assert.throws(() => parseManifest(text), { name: "ManifestError" }, `accepted ${what}`);
  }
});

test("versions are ordered numerically, missing segments counting as zero", () => {
  assert.equal(compareVersions("2", "1"), 1);
  assert.equal(compareVersions("1.9", "1.10"), -1);
  assert.equal(compareVersions("1", "1.0.0"), 0);
  assert.equal(compareVersions("0.4.0", "0.4.1"), -1);
  assert.equal(compareVersions("10", "9"), 1);
});

test("an entry URL resolves against the manifest, absolute or not", () => {
  const base = "https://cdn.example.test/aetherius/manifest.json";
  assert.equal(resolveUrl(base, "https://other.test/x.json"), "https://other.test/x.json");
  assert.equal(resolveUrl(base, "/raw/x.json"), "https://cdn.example.test/raw/x.json");
  assert.equal(resolveUrl(base, "fix.json"), "https://cdn.example.test/aetherius/fix.json");
  assert.equal(resolveUrl("https://cdn.example.test", "fix.json"), "https://cdn.example.test/fix.json");
});

test("the digest matches node:crypto, corners included", () => {
  const cases = [
    "",
    "abc",
    "a".repeat(1000),
    '{\n  "aetherius": "1.0"\n}\n',
    "éàü漢字🙂",
    // Un demi-couple de substitution isole : les deux implementations doivent le remplacer par
    // U+FFFD, sans quoi l'empreinte d'un publieur et celle de l'appareil differeraient.
    "\ud800",
    "x\udc00y",
    // 55, 56 et 64 octets encadrent la frontiere du bourrage : c'est la ou une implementation
    // maison se trompe.
    "z".repeat(55),
    "z".repeat(56),
    "z".repeat(64),
  ];
  for (const value of cases) {
    assert.equal(sha256Hex(value), reference(value), `digest differs for ${JSON.stringify(value)}`);
  }
});

test("the digest matches node:crypto on random input", () => {
  for (let i = 0; i < 200; i += 1) {
    let value = "";
    const length = Math.floor(Math.random() * 400);
    for (let j = 0; j < length; j += 1) {
      value += String.fromCharCode(Math.floor(Math.random() * 0x11000));
    }
    assert.equal(sha256Hex(value), reference(value));
  }
});

test("the example manifest is real: it parses, and its digests match the files on disk", () => {
  // Sans cette garde, l'exemple livre pourrait annoncer des empreintes perimees — et la premiere
  // personne qui suit la procedure de docs/embedded.md verrait la livraison echouer sur une garde
  // qui, elle, fonctionne. `node examples/mobile/registry/build-manifest.mjs` le regenere.
  const manifest = parseManifest(readFileSync(join(REGISTRY, "manifest.json"), "utf8"));
  const entries = Object.entries(manifest.blueprints);
  assert.ok(entries.length > 0, "the example manifest publishes nothing");

  for (const [name, entry] of entries) {
    const text = readFileSync(join(REGISTRY, entry.url), "utf8");
    assert.equal(sha256Hex(text), entry.sha256, `${name}: stale digest — rebuild the manifest`);
    assert.equal(JSON.parse(text).name, name);
  }
});
