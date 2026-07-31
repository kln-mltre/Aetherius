/**
 * Hierarchie d'erreurs typees, miroir de `src/aetherius/core/errors.py`.
 *
 * Le contrat est le meme des deux cotes : une `AetheriusError` est un echec de run propre (trace
 * dans le `Result`, pas de pile) ; toute autre exception est enveloppee dans une `RunError` et
 * relancee. Les erreurs des couches hors perimetre embarque (cognition, notifications, scheduler,
 * recorder, builder) n'existent volontairement pas ici.
 */

export class AetheriusError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

export class BlueprintError extends AetheriusError {}
/** Le fichier n'a pas pu etre lu ou parse. */
export class BlueprintLoadError extends BlueprintError {}
/** Le document ne respecte pas `contracts/blueprint.schema.json`. */
export class BlueprintSchemaError extends BlueprintError {}
/** Le document est valide au schema mais incoherent pour son act (capacite absente, par ex.). */
export class BlueprintValidationError extends BlueprintError {}

/** Rendu d'expression : syntaxe invalide, variable indefinie (semantique StrictUndefined). */
export class TemplateError extends AetheriusError {}

export class NetworkError extends AetheriusError {}
/** Nom aligne sur le Python (`core/errors.py`), qui masque lui aussi le builtin homonyme. */
export class TimeoutError extends NetworkError {}
export class RetryExhaustedError extends NetworkError {}

/** `expect.status` non satisfait. */
export class StatusAssertionError extends AetheriusError {}

/** L'extraction (JSONPath, predicat `where`, selecteur DOM) n'a pas abouti. */
export class ExtractionError extends AetheriusError {}

/** Parametre d'action manquant, incoherent, ou action non dispatchable. */
export class ActionError extends AetheriusError {}

/** `wait_for` expire avec un `on_timeout: "fail:CODE"` : le code nomme est porte par l'erreur. */
export class StepTimeoutError extends AetheriusError {
  readonly code: string | undefined;

  constructor(message: string, code?: string) {
    super(message);
    this.code = code;
  }
}

/** Une dependance de plateforme manque (par ex. `react-native-webview` pour l'Act II). */
export class DependencyError extends AetheriusError {}

/** Enveloppe d'une erreur non typee remontee pendant un run. */
export class RunError extends AetheriusError {
  readonly cause: unknown;

  constructor(message: string, cause?: unknown) {
    super(message);
    this.cause = cause;
  }
}
