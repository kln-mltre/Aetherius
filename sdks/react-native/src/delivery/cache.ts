/**
 * Le cache de la surcouche distante.
 *
 * Le magasin est **injecte**, jamais importe — meme posture que le trousseau (`secrets/keychain.ts`)
 * et que `fetch`. La surface decrite (`getItem`/`setItem`/`removeItem`) est celle d'AsyncStorage,
 * qu'une application branche donc **sans adaptateur** ; un magasin de fichiers s'y branche en dix
 * lignes.
 *
 * Un **document unique** sous une seule cle, plutot qu'une entree par Blueprint. Le cout est connu
 * et assume : un document illisible fait perdre la surcouche **entiere**, et l'application retombe
 * sur son socle embarque. C'est le sens du repli, et c'est preferable a un index et des entrees qui
 * peuvent se contredire — un cache a moitie coherent serait un etat qu'aucun test ne couvre
 * vraiment.
 */

import type { BlueprintCacheStore, CachedBlueprint } from "./types.js";

/** La cle du document. Le suffixe est la version du **format de cache**, pas celle du moteur. */
export const CACHE_KEY = "aetherius/blueprints@1";

const CACHE_FORMAT = "1";

/** Un magasin en memoire : pour les tests, et pour une application qui ne veut rien persister. */
export function memoryCache(): BlueprintCacheStore {
  const items = new Map<string, string>();
  return {
    getItem: (key) => Promise.resolve(items.get(key) ?? null),
    setItem: (key, value) => {
      items.set(key, value);
      return Promise.resolve();
    },
    removeItem: (key) => {
      items.delete(key);
      return Promise.resolve();
    },
  };
}

function usable(value: unknown): value is CachedBlueprint {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Partial<CachedBlueprint>;
  return (
    typeof entry.name === "string" &&
    typeof entry.version === "string" &&
    typeof entry.sha256 === "string" &&
    typeof entry.text === "string"
  );
}

/**
 * Les entrees retenues, ou rien.
 *
 * Toute anomalie — magasin en panne, JSON casse, format inconnu, entree tronquee — rend un cache
 * **vide** plutot qu'une erreur. Un cache est une optimisation : quand il ment, on ne l'ecoute pas,
 * on ne meurt pas avec lui. L'integrite de ce qu'on en tire est verifiee ailleurs (`verify.ts`), et
 * une entree qui passerait ces gardes est bonne quelle que soit la façon dont elle est arrivee la.
 */
export async function readCache(
  store: BlueprintCacheStore | undefined,
): Promise<Record<string, CachedBlueprint>> {
  if (store === undefined) return {};
  try {
    const text = await store.getItem(CACHE_KEY);
    if (text === null) return {};
    const data = JSON.parse(text) as { cache?: unknown; entries?: unknown };
    if (data.cache !== CACHE_FORMAT) return {};
    if (typeof data.entries !== "object" || data.entries === null) return {};

    const entries: Record<string, CachedBlueprint> = {};
    for (const [name, value] of Object.entries(data.entries as Record<string, unknown>)) {
      if (usable(value) && value.name === name) entries[name] = value;
    }
    return entries;
  } catch {
    return {};
  }
}

/**
 * Ecarte les entrees qu'on n'a plus le droit de servir.
 *
 * C'est l'interrupteur d'arret du jalon 3-H : une entree arrivee par le prefixe reserve et qui n'est
 * plus couverte — parce que l'application a change son prefixe ou retire `allowNew` — doit
 * **disparaitre**, pas dormir dans le cache en attendant qu'on rouvre la porte. Un interrupteur qui
 * laisse en place ce qu'il a laisse entrer n'en est pas un.
 *
 * Pure, et rendant `dropped` : c'est l'appelant qui decide de reecrire, un seul endroit ou l'etat
 * change. Reecrire a chaque lecture pour rien couterait une ecriture par run.
 */
export function prune(
  entries: Readonly<Record<string, CachedBlueprint>>,
  keep: (name: string) => boolean,
): { entries: Record<string, CachedBlueprint>; dropped: readonly string[] } {
  const kept: Record<string, CachedBlueprint> = {};
  const dropped: string[] = [];
  for (const [name, entry] of Object.entries(entries)) {
    if (keep(name)) kept[name] = entry;
    else dropped.push(name);
  }
  return { entries: kept, dropped };
}

/**
 * Ecrit les entrees retenues.
 *
 * Une ecriture qui echoue est **muette** : l'application tourne alors sur ce qu'elle a en memoire,
 * et le rafraichissement suivant retentera. Faire echouer un rafraichissement parce qu'un disque
 * est plein reviendrait a transformer une optimisation absente en panne visible.
 */
export async function writeCache(
  store: BlueprintCacheStore | undefined,
  entries: Readonly<Record<string, CachedBlueprint>>,
): Promise<void> {
  if (store === undefined) return;
  try {
    if (Object.keys(entries).length === 0) {
      await store.removeItem(CACHE_KEY);
      return;
    }
    await store.setItem(CACHE_KEY, JSON.stringify({ cache: CACHE_FORMAT, entries }));
  } catch {
    // Volontairement muet : voir ci-dessus.
  }
}
