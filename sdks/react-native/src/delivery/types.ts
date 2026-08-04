/**
 * Les formes de la livraison des Blueprints (jalon 3-F).
 *
 * Deux vocabulaires cohabitent ici, et il vaut mieux ne pas les confondre :
 *
 *   - le **manifeste**, contrat *applicatif* servi par un CDN — ce que le publieur ecrit ;
 *   - le **cache**, document local — ce que l'appareil a retenu et pourra rejouer hors ligne.
 *
 * Les deux portent une empreinte et une version, pour la meme raison : un Blueprint est de la
 * donnee **executable**, et rien de ce qui vient du reseau n'est cru sur parole. Le format est
 * specifie dans docs/embedded.md.
 */

import type { Blueprint, FetchLike } from "@aetherius/engine";

/** Un Blueprint embarque dans le binaire : le socle, jamais optionnel. */
export interface BundledBlueprint {
  /** Version ordonnee (chaine numerique pointee). Le distant ne gagne que s'il est superieur. */
  readonly version: string;
  /** Le document JSON tel qu'un `import` le rend. Il est valide a la resolution. */
  readonly document: unknown;
}

/** Une entree du manifeste : quelle version d'un Blueprint, ou, et avec quelle empreinte. */
export interface ManifestEntry {
  readonly version: string;
  /** Absolue, ou relative — resolue contre l'URL du manifeste. */
  readonly url: string;
  /** SHA-256 hexadecimal minuscule du **texte servi**. */
  readonly sha256: string;
  /** Version minimale du moteur. Une entree ecrite pour plus recent est ignoree. */
  readonly minEngine?: string;
  /** Interrupteur d'arret par Blueprint : l'embarque reprend la main. */
  readonly disabled: boolean;
}

export interface Manifest {
  /** Version du **format** du manifeste, pas des Blueprints. */
  readonly format: string;
  readonly generatedAt?: string;
  /** Interrupteur d'arret global. */
  readonly disabled: boolean;
  readonly blueprints: Readonly<Record<string, ManifestEntry>>;
}

/** Ce qu'un magasin persistant doit offrir. `AsyncStorage` le satisfait tel quel. */
export interface BlueprintCacheStore {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

/** Une version distante retenue. Le texte est garde tel quel : c'est lui qu'on rehashe a la lecture. */
export interface CachedBlueprint {
  readonly name: string;
  readonly version: string;
  readonly sha256: string;
  readonly text: string;
  readonly min_engine?: string;
  readonly fetched_at: string;
}

export type BlueprintOrigin = "bundled" | "remote";

export interface ResolvedBlueprint {
  readonly name: string;
  readonly version: string;
  readonly origin: BlueprintOrigin;
  readonly blueprint: Blueprint;
}

/** Ce que `list()` rend : de quoi afficher l'etat de la livraison sans charger les Blueprints. */
export interface BlueprintStatus {
  readonly name: string;
  readonly version: string;
  readonly origin: BlueprintOrigin;
}

/**
 * Le sort d'une entree lors d'un rafraichissement.
 *
 * `ignored` et `rejected` disent deux choses differentes, et la distinction est le premier outil de
 * diagnostic d'un publieur : `ignored` = le manifeste ne demandait rien de nouveau (plus ancien,
 * desactive, moteur trop vieux) ; `rejected` = il demandait quelque chose, et la garde a mordu
 * (empreinte fausse, Blueprint invalide, secret hors perimetre).
 */
export type RefreshOutcome = "updated" | "kept" | "ignored" | "rejected";

export interface RefreshEntry {
  readonly name: string;
  readonly outcome: RefreshOutcome;
  readonly version?: string;
  readonly reason?: string;
}

export interface RefreshReport {
  /** Le manifeste a-t-il ete lu ? Un `false` n'est **jamais** une erreur pour l'application. */
  readonly ok: boolean;
  /** Pourquoi il ne l'a pas ete : reseau, format, interrupteur local. */
  readonly reason?: string;
  readonly entries: readonly RefreshEntry[];
}

export interface RegistryConfig {
  /** Le socle embarque, indexe par le `name` du Blueprint. Sans lui, rien ne tourne hors ligne. */
  readonly bundled: Readonly<Record<string, BundledBlueprint>>;
  /** L'URL du manifeste. Absente, le registre sert uniquement l'embarque. */
  readonly manifest?: string;
  /** Le magasin persistant. Sans lui, la surcouche ne survit pas au processus. */
  readonly cache?: BlueprintCacheStore;
  /**
   * Les secrets qu'un Blueprint **distant** a le droit de reclamer.
   *
   * Par defaut : l'union de ceux que declare le socle embarque — c'est-a-dire ce que l'application
   * a ete construite pour fournir. Sans cette borne, un Blueprint distant compromis pourrait
   * demander le contenu du trousseau et l'exfiltrer par une simple requete.
   */
  readonly allowedSecrets?: readonly string[];
  /** Remplace le `fetch` de l'hote (interception, epinglage de certificat, test). */
  readonly fetch?: FetchLike;
  /** Delai d'une requete de livraison. 10 s par defaut. */
  readonly timeoutMs?: number;
  /** Plafond de taille d'un telechargement. 512 Kio par defaut. */
  readonly maxBytes?: number;
  /** Interrupteur d'arret **local** et durable : `false` ne resout que l'embarque. */
  readonly remote?: boolean;
  /**
   * La version du moteur opposee a `min_engine`. Celle du paquet par defaut.
   *
   * Surchargeable pour qu'un test de la contrainte de compatibilite n'ait pas a etre reecrit a
   * chaque version publiee.
   */
  readonly engineVersion?: string;
}
