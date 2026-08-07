/**
 * Regenere `manifest.json` a partir des fichiers de ce repertoire.
 *
 * Publier, c'est deux gestes : deposer un Blueprint corrige, et republier le manifeste qui le
 * designe **avec son empreinte**. Le second se fait ici plutot qu'a la main : une empreinte calculee
 * de tete est perimee des la premiere correction, et un manifeste dont l'empreinte ment est
 * exactement ce que l'appareil rejette — on passerait la soiree a debugger une garde qui fonctionne.
 *
 *   node examples/mobile/registry/build-manifest.mjs
 *
 * Le format est specifie dans docs/embedded.md. C'est un contrat *applicatif* : rien ici n'est
 * genere depuis `contracts/`, et rien ici n'a d'influence sur le moteur.
 */

import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

/**
 * Ce que le manifeste publie.
 *
 * `version` est la version **du Blueprint**, ordonnee, et elle doit battre celle que l'application
 * embarque (declaree dans `examples/mobile/demo/delivery.js`) : le distant ne gagne que s'il est
 * plus recent. Un nom que l'application n'embarque pas n'a rien a battre — il n'a pas de socle —,
 * et sa version sert alors seulement a dire ce qui a change. `min_engine` dit a partir de quelle
 * version du moteur le fichier est jouable ; il parle des **capacites** que le Blueprint utilise,
 * pas du mecanisme de livraison.
 *
 * Les trois entrees sont volontairement de trois natures differentes, et c'est le contraste qui
 * documente la livraison :
 *
 *   - une **correction** d'un nom embarque (jalon 3-F) ;
 *   - un **ajout** sous le prefixe reserve (jalon 3-H) ;
 *   - un ajout **hors prefixe**, que l'appareil doit ignorer — le cas qui echoue.
 */
const PUBLISHED = [
  {
    name: "mobile.delivery.quotes",
    file: "delivery-quotes.v2.blueprint.json",
    version: "2",
    min_engine: "0.4.0",
  },
  {
    name: "mobile.portail.demo",
    file: "portail-demo.blueprint.json",
    version: "1",
    min_engine: "0.4.0",
  },
  {
    name: "mobile.autre.demo",
    file: "hors-perimetre.blueprint.json",
    version: "1",
    min_engine: "0.4.0",
  },
];

const blueprints = {};
for (const entry of PUBLISHED) {
  const text = readFileSync(join(HERE, entry.file), "utf8");
  const declared = JSON.parse(text).name;
  if (declared !== entry.name) {
    // Un fichier livre sous un nom qui n'est pas le sien remplacerait un Blueprint par un autre.
    // L'appareil le refuse ; autant le dire ici, ou la correction est encore facile.
    throw new Error(`${entry.file} is named '${declared}', published as '${entry.name}'`);
  }
  blueprints[entry.name] = {
    version: entry.version,
    url: entry.file,
    sha256: createHash("sha256").update(text, "utf8").digest("hex"),
    min_engine: entry.min_engine,
    disabled: false,
  };
}

const manifest = {
  manifest: "1",
  generated_at: new Date().toISOString(),
  disabled: false,
  blueprints,
};

const path = join(HERE, "manifest.json");
writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
console.log(`manifest written: ${path}`);
for (const [name, entry] of Object.entries(blueprints)) {
  console.log(`  ${name} v${entry.version} -> ${entry.url} (${entry.sha256.slice(0, 12)}…)`);
}
