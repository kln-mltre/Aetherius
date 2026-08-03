/**
 * Le filet : masquer les valeurs de secrets sur le chemin de sortie du moteur.
 *
 * Le moteur tient deja l'invariant principal **par construction** — un evenement `step_skipped`
 * publie l'expression `when` *brute*, jamais sa valeur rendue, precisement parce que cette valeur
 * peut deriver d'un secret. Mais deux chemins restent ouverts, et ils ne sont pas theoriques :
 *
 *   - le message d'un `assert` est **rendu** avant d'etre leve, donc `{{ secrets.x }}` s'y retrouve ;
 *   - une URL, un corps de requete ou un en-tete cite dans un message d'erreur peut porter un secret
 *     interpole.
 *
 * D'ou ce rideau, pose par la facade sur le flux d'evenements **et** sur le message d'echec du
 * `Result`. Il est ajoute par la surface applicative, pas repris du moteur Python : c'est le jalon
 * 3-E qui decide de ce qu'une application voit.
 *
 * **La limite, ecrite plutot que decouverte** : le masquage se fait par valeur. Un « secret » d'un
 * ou deux caracteres masquerait ces caracteres partout dans les messages — ce qui est visible, et
 * bien plus honnete qu'un masquage qui cesserait silencieusement de proteger en dessous d'un seuil.
 * Une valeur vide est ignoree : elle n'a rien a proteger et masquerait tout.
 */

import type { RunEvent, Sink } from "@aetherius/engine";

export const REDACTED = "[secret]";

/**
 * Remplace chaque valeur de *values* par `[secret]` dans *text*.
 *
 * Les valeurs sont traitees de la plus longue a la plus courte : sans cela, un secret qui est le
 * prefixe d'un autre laisserait la queue du second en clair.
 */
export function redactText(text: string, values: readonly string[]): string {
  let out = text;
  for (const value of ordered(values)) out = out.split(value).join(REDACTED);
  return out;
}

/** Masque recursivement dans une valeur quelconque (les `data` d'un evenement en sont). */
export function redactValue(value: unknown, values: readonly string[]): unknown {
  if (typeof value === "string") return redactText(value, values);
  if (Array.isArray(value)) return value.map((item) => redactValue(item, values));
  if (value !== null && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) out[key] = redactValue(item, values);
    return out;
  }
  return value;
}

export function redactEvent(event: RunEvent, values: readonly string[]): RunEvent {
  if (values.length === 0) return event;
  return {
    ...event,
    ...(event.message !== undefined ? { message: redactText(event.message, values) } : {}),
    ...(event.data !== undefined
      ? { data: redactValue(event.data, values) as Readonly<Record<string, unknown>> }
      : {}),
  };
}

/**
 * Enveloppe *sink* pour qu'il ne voie jamais un secret.
 *
 * Le masquage a lieu **avant** le sink, pas dans le bus : l'interieur du moteur continue de
 * travailler sur des valeurs vraies, et seule la frontiere de sortie est nettoyee. Masquer plus tot
 * rendrait un message d'erreur illisible au debogage du moteur lui-meme.
 */
export function redactingSink(sink: Sink, values: readonly string[]): Sink {
  const secrets = usable(values);
  if (secrets.length === 0) return sink;
  return {
    onEvent(event: RunEvent): void {
      sink.onEvent(redactEvent(event, secrets));
    },
  };
}

/** Les valeurs qui valent la peine d'etre masquees (non vides), les plus longues d'abord. */
export function usable(values: readonly string[]): string[] {
  return ordered(values.filter((value) => value !== ""));
}

function ordered(values: readonly string[]): string[] {
  return [...values].sort((left, right) => right.length - left.length);
}
