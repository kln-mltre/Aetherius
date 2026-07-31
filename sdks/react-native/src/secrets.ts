/**
 * Resolution des secrets, cote appareil.
 *
 * Cote Python les secrets viennent de l'environnement ou d'un `.env` ; sur mobile ils vivent dans le
 * trousseau de l'OS. L'interface est branchable pour que le moteur ne dependance jamais d'un
 * fournisseur precis : l'implementation `expo-secure-store` n'est qu'un adaptateur parmi d'autres.
 *
 * Invariant repris tel quel du moteur Python : un secret resolu ne franchit jamais la frontiere des
 * evenements ni des journaux. En particulier, `step_skipped` publie l'expression `when` **brute**,
 * jamais sa valeur rendue.
 *
 * Squelette Phase 3 : les adaptateurs et la facade arrivent au jalon 3-E
 * (docs/phase-3/3-e-integration.md).
 */

export interface SecretResolver {
  /** Rend la valeur du secret, ou `undefined` s'il est absent (le moteur decide alors d'echouer). */
  resolve(name: string): Promise<string | undefined>;
}
