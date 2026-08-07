/**
 * Les gardes qu'un Blueprint venu du reseau doit franchir.
 *
 * Un fichier a part, parce que ces gardes s'appliquent **deux fois** et qu'il ne doit pas exister
 * deux versions d'elles : a l'ecriture du cache (rafraichissement) et a **chaque lecture**
 * (resolution). Verifier a l'ecriture seulement supposerait qu'un cache local est digne de
 * confiance ; il ne l'est pas plus qu'un CDN — c'est un fichier sur un appareil.
 *
 * Elles sont ordonnees par importance decroissante, comme la specification du jalon :
 *
 *   1. **integrite** — l'empreinte du texte doit etre celle qu'annonce le manifeste ;
 *   2. **compatibilite** — un Blueprint ecrit pour un moteur plus recent est ignore ;
 *   3. **anteriorite** — le distant ne gagne que s'il est plus recent que l'embarque (sans objet
 *      pour un nom **ajoute** sous le prefixe reserve du jalon 3-H : il n'y a pas d'embarque) ;
 *   4. **validite** — schema, modele, et portabilite sur ce moteur (`validateForAct`) ;
 *   5. **perimetre** — les secrets reclames sont bornes par l'application, pas par le fichier.
 *
 * La cinquieme est la moins evidente et la plus importante : sans elle, un Blueprint distant
 * compromis pourrait declarer `secrets: ["cas_pass"]` et poster la valeur ou il veut. La façade ne
 * resout que les secrets **declares** (jalon 3-E) — ce qui borne ce que peut lire un Blueprint,
 * mais pas ce qu'il peut *declarer*. C'est ici que la borne est posee.
 */

import { parseBlueprint, validateForAct, type Blueprint } from "@aetherius/engine";

import { compareVersions } from "./manifest.js";
import { sha256Hex } from "./sha256.js";

/** Le verdict d'une garde. Une valeur plutot qu'une exception : un refus n'est pas un incident. */
export type Verdict = { readonly ok: true; readonly blueprint: Blueprint } | Rejection;

export interface Rejection {
  readonly ok: false;
  /** `ignored` : le manifeste ne demandait rien d'applicable. `rejected` : une garde a mordu. */
  readonly outcome: "ignored" | "rejected";
  readonly reason: string;
}

export interface Candidate {
  readonly name: string;
  readonly version: string;
  readonly sha256: string;
  readonly text: string;
  readonly minEngine?: string | undefined;
}

export interface Bounds {
  /**
   * La version embarquee que le candidat doit battre.
   *
   * Absente pour un nom **ajoute** sous le prefixe reserve (jalon 3-H) : il n'y a rien a battre, et
   * exiger une comparaison contre une version qui n'existe pas reviendrait a inventer un socle.
   */
  readonly bundledVersion?: string | undefined;
  readonly engineVersion: string;
  readonly allowedSecrets: ReadonlySet<string>;
}

export function verify(candidate: Candidate, bounds: Bounds): Verdict {
  const digest = sha256Hex(candidate.text);
  if (digest !== candidate.sha256) {
    return {
      ok: false,
      outcome: "rejected",
      reason: `integrity check failed (expected ${short(candidate.sha256)}, got ${short(digest)})`,
    };
  }

  if (
    candidate.minEngine !== undefined &&
    compareVersions(candidate.minEngine, bounds.engineVersion) > 0
  ) {
    return {
      ok: false,
      outcome: "ignored",
      reason: `needs engine ${candidate.minEngine}, this one is ${bounds.engineVersion}`,
    };
  }

  if (
    bounds.bundledVersion !== undefined &&
    compareVersions(candidate.version, bounds.bundledVersion) <= 0
  ) {
    return {
      ok: false,
      outcome: "ignored",
      reason: `version ${candidate.version} is not newer than the bundled ${bounds.bundledVersion}`,
    };
  }

  let blueprint: Blueprint;
  try {
    blueprint = parseBlueprint(candidate.text, `${candidate.name}@${candidate.version}`);
    validateForAct(blueprint);
  } catch (error) {
    return {
      ok: false,
      outcome: "rejected",
      reason: error instanceof Error ? error.message : String(error),
    };
  }

  if (blueprint.name !== candidate.name) {
    // Un fichier qui ne porte pas le nom sous lequel il est livre remplacerait un Blueprint par un
    // autre — le manifeste dirait une chose, l'appareil en jouerait une autre.
    return {
      ok: false,
      outcome: "rejected",
      reason: `the document is named '${blueprint.name}', not '${candidate.name}'`,
    };
  }

  const outside = (blueprint.secrets ?? []).filter((name) => !bounds.allowedSecrets.has(name));
  if (outside.length > 0) {
    return {
      ok: false,
      outcome: "rejected",
      reason:
        `declares secrets the application does not allow: ${outside.join(", ")} ` +
        `(allowed: ${[...bounds.allowedSecrets].join(", ") || "none"})`,
    };
  }

  return { ok: true, blueprint };
}

function short(digest: string): string {
  return digest.slice(0, 12);
}
