/**
 * Un resolver adosse a une table en memoire.
 *
 * Pour les tests et le developpement : c'est ce qui prouve que le moteur ne depend pas du trousseau,
 * et ce qui permet d'ecrire une suite sans simuler `expo-secure-store`.
 *
 * A ne pas confondre avec « coder les secrets en dur » : la table vient de l'appelant, elle n'est
 * jamais lue d'un fichier ni d'un Blueprint. Un secret ecrit dans du code applicatif part dans le
 * binaire publie sur les stores, ou n'importe qui peut le lire.
 */

import type { SecretResolver } from "./resolver.js";

export function staticSecrets(values: Readonly<Record<string, string>>): SecretResolver {
  const table = { ...values };
  return {
    async resolve(name: string): Promise<string | undefined> {
      return Object.prototype.hasOwnProperty.call(table, name) ? table[name] : undefined;
    },
  };
}
