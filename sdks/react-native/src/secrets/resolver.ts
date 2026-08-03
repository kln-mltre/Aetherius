/**
 * Resolution des secrets, cote appareil.
 *
 * Cote Python les secrets viennent de l'environnement ou d'un `.env` ([docs/secrets.md]) ; sur
 * mobile ils vivent dans le trousseau de l'OS, chiffre par le systeme. C'est la raison d'etre de la
 * Phase 3 prise a la lettre : une application universitaire qui scrape l'ENT de son utilisateur
 * detient ses identifiants CAS, et ils ne doivent aller qu'au CAS de son universite.
 *
 * L'interface est **branchable** pour que le moteur ne dependance jamais d'un fournisseur precis :
 * l'adaptateur trousseau (`keychain.ts`) n'est qu'une implementation parmi d'autres, et c'est aussi
 * ce qui rend la facade testable sans trousseau (`static.ts`).
 *
 * Deux invariants tiennent l'hygiene, et tous deux sont testes :
 *
 *   - seuls les secrets **declares** par le Blueprint sont demandes au resolver — un Blueprint ne
 *     peut pas se servir dans le trousseau de l'application ;
 *   - une valeur resolue ne franchit jamais la frontiere des evenements ni des journaux. Le moteur
 *     y contribue par construction (un `step_skipped` publie l'expression `when` **brute**, jamais
 *     sa valeur rendue), la facade ajoute un filet (`redact.ts`).
 */

export interface SecretResolver {
  /** Rend la valeur du secret, ou `undefined` s'il est absent (le moteur decide alors d'echouer). */
  resolve(name: string): Promise<string | undefined>;
}
