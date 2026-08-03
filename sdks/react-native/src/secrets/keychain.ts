/**
 * L'adaptateur trousseau : le `SecretResolver` par defaut sur un appareil.
 *
 * Le magasin est **injecte**, jamais importe. `expo-secure-store` est le choix habituel, mais le
 * paquet ne le connait pas : il decrit **structurellement** ce dont il a besoin — une methode qui
 * rend une valeur ou `null`. C'est la meme posture que `fetch` (`engine/src/http.ts`) et que
 * `react-native-webview` (`webview/react-native-webview.d.ts`), et elle achete trois choses :
 * aucune dependance ajoutee au binaire, aucune adherence a Expo pour une application React Native
 * nue, et un resolver testable sans trousseau.
 *
 * ```ts
 * import * as SecureStore from "expo-secure-store";
 * const secrets = keychainSecrets(SecureStore);
 * ```
 *
 * `react-native-keychain` ou un magasin maison s'y branchent par un adaptateur d'une ligne, ce qui
 * est precisement l'interet de ne pas avoir choisi a la place de l'application.
 */

import type { SecretResolver } from "./resolver.js";

/** Ce qu'un magasin doit offrir. `expo-secure-store` le satisfait tel quel. */
export interface SecretStore {
  getItemAsync(key: string): Promise<string | null>;
}

export interface KeychainOptions {
  /**
   * Traduit un nom de secret de Blueprint en cle du magasin. Identite par defaut.
   *
   * Il existe parce qu'une application a deja ses cles : UKit garde ses identifiants CAS sous les
   * siennes, et les renommer pour plaire a Aetherius serait le genre de migration qu'une
   * bibliotheque n'a pas a imposer. C'est aussi la ou l'on met un prefixe, si l'on en veut un.
   */
  readonly key?: (name: string) => string;
}

/**
 * Un resolver adosse a *store*.
 *
 * Un secret absent rend `undefined` — il est alors *omis* du contexte, et c'est le rendu qui signale
 * l'erreur, au step qui le lit reellement. Le trousseau qui echoue (verrouille, entree corrompue)
 * est traite comme une absence : la difference n'a pas de sens pour l'appelant, et laisser echapper
 * une erreur de plateforme ferait mourir un run qui n'avait peut-etre pas besoin de ce secret.
 */
export function keychainSecrets(store: SecretStore, options: KeychainOptions = {}): SecretResolver {
  const toKey = options.key ?? ((name: string) => name);
  return {
    async resolve(name: string): Promise<string | undefined> {
      try {
        const value = await store.getItemAsync(toKey(name));
        return value === null ? undefined : value;
      } catch {
        // Volontairement muet : journaliser ici journaliserait le nom du secret a chaque lecture
        // ratee, et un journal d'application finit souvent ailleurs que sur l'appareil.
        return undefined;
      }
    },
  };
}
