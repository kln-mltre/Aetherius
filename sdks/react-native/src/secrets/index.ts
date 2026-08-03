/** La resolution des secrets et l'hygiene qui va avec (jalon 3-E). Voir `resolver.ts`. */

export { keychainSecrets, type KeychainOptions, type SecretStore } from "./keychain.js";
export { REDACTED, redactEvent, redactText, redactValue, redactingSink, usable } from "./redact.js";
export type { SecretResolver } from "./resolver.js";
export { staticSecrets } from "./static.js";
