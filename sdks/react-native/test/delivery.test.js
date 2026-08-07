/**
 * La livraison des Blueprints : resolution, rafraichissement, hors ligne, interrupteur d'arret.
 *
 * Ce que ces tests figent n'est pas du code, c'est une **promesse produit** : une application
 * fonctionne au premier lancement sans reseau, un Blueprint corrige a distance est pris en compte
 * sans republication, et on peut revenir en arriere. Chaque cas ici correspond a une ligne du plan
 * de test du jalon (docs/phase-3/3-f-delivery.md).
 *
 * Les gardes — integrite, perimetre des secrets, cache corrompu — ont leur propre fichier
 * (`delivery-guards.test.js`), parce qu'elles repondent a une autre question : non pas « la bonne
 * version gagne-t-elle ? » mais « qu'est-ce qui n'entre pas ? ».
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { describeFailure } from "@aetherius/engine";

import { BlueprintRegistry } from "../dist/delivery/registry.js";
import { CACHE_KEY, memoryCache } from "../dist/delivery/cache.js";
import { MANIFEST_URL, cdn, document, manifest, text } from "./delivery-support.mjs";

const NAME = "demo.delivery";
const FIX_URL = "https://cdn.example.test/aetherius/demo.v2.json";
const fix = text(document(NAME, { marker: "remote-v2" }));

/** A registry wired to a double CDN, with the bundled v1 every case starts from. */
function registry(routes, extra = {}) {
  const store = extra.cache ?? memoryCache();
  const network = cdn(routes);
  const subject = new BlueprintRegistry({
    bundled: { [NAME]: { version: "1", document: document(NAME, { marker: "bundled-v1" }) } },
    manifest: MANIFEST_URL,
    cache: store,
    fetch: network.fetch,
    ...extra,
  });
  return { subject, network, store };
}

const marker = async (subject) => (await subject.resolve(NAME)).blueprint.steps[0].value;

test("without a manifest, the bundled Blueprint is what runs", async () => {
  const subject = new BlueprintRegistry({
    bundled: { [NAME]: { version: "1", document: document(NAME) } },
  });

  const resolved = await subject.resolve(NAME);
  assert.equal(resolved.origin, "bundled");
  assert.equal(resolved.version, "1");
  assert.equal(resolved.blueprint.name, NAME);
});

test("a newer remote version wins, and the application repairs itself", async () => {
  const { subject } = registry({
    [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
    [FIX_URL]: fix,
  });

  assert.equal(await marker(subject), "bundled-v1");
  const report = await subject.refresh();
  assert.equal(report.ok, true);
  assert.deepEqual(report.entries, [{ name: NAME, outcome: "updated", version: "2" }]);

  const resolved = await subject.resolve(NAME);
  assert.equal(resolved.origin, "remote");
  assert.equal(resolved.version, "2");
  assert.equal(resolved.blueprint.steps[0].value, "remote-v2");
});

test("an older remote version is ignored: the remote only wins when it is newer", async () => {
  const stale = text(document(NAME, { marker: "remote-v0" }));
  const { subject } = registry({
    [MANIFEST_URL]: manifest({ [NAME]: { version: "0.9", url: FIX_URL, body: stale } }),
    [FIX_URL]: stale,
  });

  const report = await subject.refresh();
  assert.equal(report.entries[0].outcome, "ignored");
  assert.match(report.entries[0].reason, /not newer than the bundled 1/);
  assert.equal(await marker(subject), "bundled-v1");
});

test("a remote Blueprint written for a newer engine is ignored, without a visible error", async () => {
  const { subject } = registry(
    {
      [MANIFEST_URL]: manifest({
        [NAME]: { version: "2", url: FIX_URL, body: fix, min_engine: "9.9.9" },
      }),
      [FIX_URL]: fix,
    },
    { engineVersion: "0.4.0" },
  );

  const report = await subject.refresh();
  assert.equal(report.ok, true);
  assert.equal(report.entries[0].outcome, "ignored");
  assert.match(report.entries[0].reason, /needs engine 9\.9\.9/);
  assert.equal(await marker(subject), "bundled-v1");
});

test("a manifest entry the application does not bundle is ignored", async () => {
  // Regle du jalon : le manifeste ne peut que *mettre a jour* ce que l'application livre deja. Un
  // nom inconnu n'aurait aucun repli hors ligne, et elargirait ce qu'un manifeste compromis peut
  // faire executer.
  const other = text(document("someone.else"));
  const { subject } = registry({
    [MANIFEST_URL]: manifest({ "someone.else": { version: "2", url: FIX_URL, body: other } }),
    [FIX_URL]: other,
  });

  const report = await subject.refresh();
  assert.equal(report.entries[0].outcome, "ignored");
  assert.match(report.entries[0].reason, /not bundled/);
  await assert.rejects(() => subject.resolve("someone.else"), { name: "BlueprintLoadError" });
});

test("resolving never reaches the network", async () => {
  // Un run n'attend pas un CDN pour savoir quoi jouer : c'est la regle qui rend la livraison
  // invisible depuis le chemin critique.
  const { subject, network } = registry({
    [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
    [FIX_URL]: fix,
  });

  await subject.resolve(NAME);
  await subject.list();
  assert.deepEqual(network.calls, []);

  await subject.refresh();
  network.calls.length = 0;
  await subject.resolve(NAME);
  assert.deepEqual(network.calls, []);
});

test("an unknown name fails as a Blueprint problem, not as an engine bug", async () => {
  const { subject } = registry({});
  const error = await subject.resolve("nobody.knows").catch((cause) => cause);

  assert.equal(error.name, "BlueprintLoadError");
  assert.equal(describeFailure(error).kind, "blueprint");
  assert.match(error.message, /nobody\.knows/);
});

test("first launch with no network at all runs on the bundle", async () => {
  const offline = () => Promise.reject(new Error("Network request failed"));
  const subject = new BlueprintRegistry({
    bundled: { [NAME]: { version: "1", document: document(NAME, { marker: "bundled-v1" }) } },
    manifest: MANIFEST_URL,
    cache: memoryCache(),
    fetch: offline,
  });

  const report = await subject.refresh();
  assert.equal(report.ok, false);
  assert.match(report.reason, /Network request failed/);
  assert.equal(await marker(subject), "bundled-v1");
});

test("a network loss during a refresh leaves the version in place untouched", async () => {
  const { subject, network } = registry({
    [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
    [FIX_URL]: fix,
  });
  await subject.refresh();
  assert.equal(await marker(subject), "remote-v2");

  // Le manifeste annonce une v3 que le CDN ne sert pas (deploiement a moitie fait, coupure).
  const three = text(document(NAME, { marker: "remote-v3" }));
  network.put(
    MANIFEST_URL,
    manifest({
      [NAME]: { version: "3", url: "https://cdn.example.test/aetherius/demo.v3.json", body: three },
    }),
  );

  const report = await subject.refresh();
  assert.equal(report.entries[0].outcome, "rejected");
  assert.match(report.entries[0].reason, /HTTP 404/);
  assert.equal(await marker(subject), "remote-v2");
});

test("an unchanged entry is kept without being downloaded again", async () => {
  const { subject, network } = registry({
    [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
    [FIX_URL]: fix,
  });
  await subject.refresh();

  network.calls.length = 0;
  const report = await subject.refresh();
  assert.deepEqual(report.entries, [{ name: NAME, outcome: "kept", version: "2" }]);
  assert.deepEqual(network.calls, [MANIFEST_URL]);
});

test("every delivery request defeats the platform HTTP cache", async () => {
  // Trouve sur un appareil : `fetch` passe par NSURLCache (iOS) et par le cache OkHttp (Android),
  // et un hote statique qui ne renvoie qu'un `Last-Modified` leur laisse inventer une fraicheur.
  // Consequence observee : serveur coupe, et l'application repondait « manifeste lu ». Un manifeste
  // servi depuis un cache, c'est un interrupteur d'arret qui n'arrete rien.
  const { subject, network } = registry({
    [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
    [FIX_URL]: fix,
  });

  // L'horloge est GELEE le temps du test : deux rafraichissements dans la meme milliseconde sont
  // exactement le cas que la CI a rencontre et qu'une machine plus lente masque. L'unicite du jeton
  // ne doit pas dependre de la resolution de `Date.now()`, sinon le contournement cesse de
  // contourner sans que rien ne le dise.
  const clock = Date.now;
  Date.now = () => 1_700_000_000_000;
  try {
    await subject.refresh();
    await subject.refresh();
  } finally {
    Date.now = clock;
  }

  const manifests = network.raw.filter((call) => call.url.startsWith(MANIFEST_URL));
  assert.equal(manifests.length, 2);
  assert.notEqual(manifests[0].url, manifests[1].url, "two refreshes asked for the same URL");
  for (const call of network.raw) {
    assert.match(call.url, /[?&]_aeth=/);
    assert.match(call.init.headers["Cache-Control"], /no-cache/);
  }
});

test("the overlay survives the process: a new registry over the same store finds the fix", async () => {
  const store = memoryCache();
  const routes = {
    [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
    [FIX_URL]: fix,
  };
  const first = registry(routes, { cache: store });
  await first.subject.refresh();

  // Redemarrage de l'application : meme magasin, registre neuf, aucun reseau disponible.
  const second = new BlueprintRegistry({
    bundled: { [NAME]: { version: "1", document: document(NAME, { marker: "bundled-v1" }) } },
    cache: store,
  });
  assert.equal(await marker(second), "remote-v2");
});

test("an entry disabled by the manifest goes back to the bundle at the next run", async () => {
  const { subject, network } = registry({
    [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
    [FIX_URL]: fix,
  });
  await subject.refresh();
  assert.equal(await marker(subject), "remote-v2");

  network.put(
    MANIFEST_URL,
    manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix, disabled: true } }),
  );
  const report = await subject.refresh();
  assert.equal(report.entries[0].outcome, "ignored");
  assert.match(report.entries[0].reason, /disabled by the manifest/);
  assert.equal(await marker(subject), "bundled-v1");
});

test("the global kill switch reverts everything at once", async () => {
  const { subject, network } = registry({
    [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
    [FIX_URL]: fix,
  });
  await subject.refresh();

  network.put(
    MANIFEST_URL,
    manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }, { disabled: true }),
  );
  await subject.refresh();
  assert.equal(await marker(subject), "bundled-v1");
});

test("an entry gone from the manifest reverts too: the manifest is the desired state", async () => {
  const { subject, network } = registry({
    [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
    [FIX_URL]: fix,
  });
  await subject.refresh();

  network.put(MANIFEST_URL, manifest({}));
  const report = await subject.refresh();
  assert.equal(report.entries[0].outcome, "ignored");
  assert.match(report.entries[0].reason, /gone from the manifest/);
  assert.equal(await marker(subject), "bundled-v1");
});

test("revert() is the local kill switch: no network, effective on the next run", async () => {
  const { subject, network } = registry({
    [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
    [FIX_URL]: fix,
  });
  await subject.refresh();
  network.calls.length = 0;

  await subject.revert();
  assert.deepEqual(network.calls, []);
  assert.equal(await marker(subject), "bundled-v1");
  assert.deepEqual(await subject.list(), [{ name: NAME, version: "1", origin: "bundled" }]);
});

test("remote: false ignores an overlay that is already there", async () => {
  const store = memoryCache();
  const routes = {
    [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
    [FIX_URL]: fix,
  };
  await registry(routes, { cache: store }).subject.refresh();

  const { subject } = registry(routes, { cache: store, remote: false });
  assert.equal(await marker(subject), "bundled-v1");
  const report = await subject.refresh();
  assert.equal(report.ok, false);
  assert.match(report.reason, /switched off/);

  // Et l'entree n'est pas detruite : rallumer la livraison la retrouve, sans reseau.
  const back = registry(routes, { cache: store });
  assert.equal(await marker(back.subject), "remote-v2");
  assert.notEqual(await store.getItem(CACHE_KEY), null);
});

test("list() reports what would actually run, Blueprint by Blueprint", async () => {
  const { subject } = registry({
    [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
    [FIX_URL]: fix,
  });
  assert.deepEqual(await subject.list(), [{ name: NAME, version: "1", origin: "bundled" }]);

  await subject.refresh();
  assert.deepEqual(await subject.list(), [{ name: NAME, version: "2", origin: "remote" }]);
});
