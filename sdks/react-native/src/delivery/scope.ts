/**
 * Les deux perimetres : ce qu'un Blueprint distant a le droit de **declarer**, et sous quels **noms**
 * un manifeste a le droit d'ajouter (jalon 3-H).
 *
 * Les deux sont ici parce qu'ils repondent a la meme question — *ce que l'application ouvre* — et
 * qu'un lecteur qui cherche l'un cherche l'autre dans la foulee. Ils ne se melangent jamais : un nom
 * **ajoute** ne recoit que `allowNew.secrets`, jamais l'union du socle, sinon le second perimetre ne
 * serait qu'une decoration.
 *
 * Le jalon 3-F posait une regle nette : le manifeste ne peut que *mettre a jour* des noms deja
 * embarques. Elle est bonne pour **corriger** — elle achete le premier lancement hors ligne pour
 * chaque Blueprint, et elle empeche un manifeste compromis d'ajouter du comportement que personne
 * n'a relu. Elle ne tient plus des qu'il s'agit d'**etendre** : un nom **nouveau** n'a aucun repli
 * hors ligne a preserver, puisqu'il n'existe pas encore pour l'utilisateur.
 *
 * La levee porte donc sur cette seule ligne, et la seconde raison reste entiere : c'est ce que ce
 * fichier borne. Il est a part parce que la couverture est consultee a **trois** endroits — la
 * resolution, le rafraichissement, et la purge du cache — et qu'il ne doit pas en exister trois
 * versions. Meme raison que `verify.ts`.
 */

import { BlueprintValidationError } from "@aetherius/engine";

import type { RegistryConfig } from "./types.js";

/**
 * Le separateur qu'un prefixe doit porter en dernier caractere.
 *
 * Un point, parce qu'un `name` de Blueprint est un identifiant pointe au contrat. Commencer strict
 * est relaxable plus tard sans casser une application existante ; l'inverse ne l'est pas.
 */
const SEPARATOR = ".";

export interface Scope {
  readonly prefix: string;
  /** Ce qu'un Blueprint arrive par cette porte a le droit de **declarer**. */
  readonly secrets: ReadonlySet<string>;
  /** Ce nom est-il couvert par le prefixe reserve ? Une comparaison de debut de chaine, rien d'autre. */
  covers(name: string): boolean;
}

/**
 * Lit `allowNew` et le valide, ou rend `undefined` quand la capacite n'est pas demandee.
 *
 * Les refus sont **bruyants et immediats** : une surface ouverte par inadvertance ne se verrait pas
 * autrement, et surement pas au moment ou elle compte.
 *
 * @throws {BlueprintValidationError} `allowNew` est present mais mal forme.
 */
export function resolveScope(config: RegistryConfig): Scope | undefined {
  const declared = config.allowNew;
  if (declared === undefined) return undefined;

  const prefix = (declared as { prefix?: unknown }).prefix;
  if (typeof prefix !== "string" || prefix.length === 0) {
    // Un prefixe vide ouvrirait tout : ce serait exactement la regle qu'on refuse d'ecrire.
    throw new BlueprintValidationError(
      "allowNew.prefix must be a non-empty string ending with a dot (e.g. 'ukit.portail.').",
    );
  }
  if (!prefix.endsWith(SEPARATOR)) {
    // `ukit` couvrirait `ukit.planning.semaine` — c'est-a-dire precisement les Blueprints que
    // l'application embarque, qu'un nom voisin pourrait alors remplacer.
    throw new BlueprintValidationError(
      `allowNew.prefix must end with '${SEPARATOR}' to name a namespace, got '${prefix}'. ` +
        `Without it, '${prefix}' would also cover the Blueprints this application bundles.`,
    );
  }

  const secrets = (declared as { secrets?: unknown }).secrets;
  if (!Array.isArray(secrets) || secrets.some((name) => typeof name !== "string")) {
    // Sans defaut, et surtout pas « l'union des secrets du socle » comme `allowedSecrets` : ce
    // defaut-la est raisonnable pour un fichier qui en remplace un autre, pas pour un fichier que
    // personne n'a relu. L'ecrire, c'est decider ce qu'un inconnu aura le droit de demander.
    throw new BlueprintValidationError(
      "allowNew.secrets is required when allowNew is set: list the secrets a Blueprint nobody " +
        "reviewed may declare (an empty array is a valid, maximally restrictive answer).",
    );
  }

  return {
    prefix,
    secrets: new Set(secrets as string[]),
    covers: (name) => name.startsWith(prefix),
  };
}

/**
 * Les secrets que le socle embarque declare : la borne par defaut du perimetre d'une **mise a
 * jour**.
 *
 * C'est ce que l'application a ete construite pour fournir — un secret de plus demanderait de toute
 * façon qu'elle le range dans le trousseau, donc une livraison. Ce defaut n'existe **pas** pour un
 * nom ajoute : la ou un fichier en remplace un que quelqu'un a relu, deduire est raisonnable ; pour
 * un fichier que personne n'a lu, il faut ecrire.
 *
 * Lu sans valider : le socle est valide ailleurs, et un document casse ne doit pas empecher le
 * registre d'exister.
 */
export function bundledSecrets(config: RegistryConfig): string[] {
  const names = new Set<string>();
  for (const entry of Object.values(config.bundled)) {
    const declared = (entry.document as { secrets?: unknown } | null)?.secrets;
    if (!Array.isArray(declared)) continue;
    for (const name of declared) if (typeof name === "string") names.add(name);
  }
  return [...names];
}

/** Le perimetre d'un nom ajoute quand la capacite n'est pas demandee : rien. */
export const NO_SECRETS: ReadonlySet<string> = new Set();
