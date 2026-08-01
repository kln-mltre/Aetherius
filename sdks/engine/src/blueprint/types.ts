/**
 * Modele de Blueprint, miroir TypeScript de `src/aetherius/core/blueprint/models.py`.
 *
 * La validation en deux temps qui produit ces types vit a cote : structurelle dans
 * [`loader.ts`](./loader.ts) (schema precompile), semantique dans [`validator.ts`](./validator.ts).
 */

/**
 * Les quatre Acts declares par le contrat. Le moteur embarque n'en execute que deux : la liste de
 * ceux-la (`EMBEDDED_ACTS`) et la table des capacites correspondante vivent dans
 * [`capabilities.ts`](./capabilities.ts), avec les raisons de chaque exclusion.
 */
export type ActName = "vector" | "continuum" | "oracle" | "phantom";

export type InputKind = "string" | "number" | "integer" | "boolean" | "object" | "array" | "path";

export interface InputSpec {
  readonly type: InputKind;
  readonly required?: boolean;
  readonly default?: unknown;
  readonly format?: string;
  readonly description?: string;
}

export type BackoffKind = "none" | "linear" | "exponential";

export interface RetriesOptions {
  readonly max: number;
  readonly backoff: BackoffKind;
}

export interface SessionOptions {
  readonly profile?: string;
  readonly persist: boolean;
}

/**
 * Sous-ensemble d'`options` que le moteur embarque honore. Les options des couches hors perimetre
 * (proxy, stealth avance, agent) restent valides au schema mais sont ignorees : cf. la table des
 * capacites du jalon 3-A.
 */
export interface Options {
  readonly debug?: boolean;
  readonly timeout_ms?: number;
  readonly retries?: RetriesOptions;
  readonly session?: SessionOptions;
  /** Seule bribe de stealth retenue sur appareil : l'identite d'en-tetes / le user-agent. */
  readonly stealth?: unknown;
}

/**
 * Un step. `action` et les champs de controle sont typés ; les parametres propres a l'action sont
 * libres (`extra="allow"` cote pydantic), d'ou l'index signature.
 */
export interface StepModel {
  readonly id?: string;
  readonly action: string;
  readonly when?: string;
  readonly act?: ActName;
  readonly describe?: string;
  readonly [param: string]: unknown;
}

export interface Blueprint {
  readonly aetherius: string;
  readonly name: string;
  readonly description?: string;
  readonly act: ActName;
  readonly inputs?: Readonly<Record<string, InputSpec>>;
  readonly secrets?: readonly string[];
  readonly vars?: Readonly<Record<string, unknown>>;
  readonly options?: Options;
  readonly steps?: readonly StepModel[];
  readonly outputs?: Readonly<Record<string, unknown>>;
}
