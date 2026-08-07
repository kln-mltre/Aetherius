/**
 * `@aetherius/react-native` — le moteur Aetherius dans une application mobile.
 *
 * Ce paquet porte ce que `@aetherius/engine` ne peut pas tenir sans dependre d'une plateforme :
 * l'**Act II** sur une WebView cachee pilotee par un agent JavaScript injecte (jalon 3-D), la
 * **surface applicative** (jalon 3-E) — la facade `Aetherius`, les secrets par le trousseau de
 * l'OS, `confirm` en modal natif, l'annulation d'un run — et la **livraison des Blueprints**
 * (jalon 3-F) : socle embarque, surcouche distante, cache et interrupteur d'arret — etendue au
 * jalon 3-H par le prefixe reserve sous lequel un manifeste peut *ajouter*.
 *
 * ```tsx
 * import * as SecureStore from "expo-secure-store";
 * import {
 *   Aetherius, AetheriusConfirm, AetheriusWebView, keychainSecrets,
 * } from "@aetherius/react-native";
 *
 * const client = new Aetherius({ secrets: keychainSecrets(SecureStore) });
 *
 * // Une fois, haut dans l'arbre : la WebView et le modal vivent avec l'application, pas avec un run.
 * <><AetheriusWebView /><AetheriusConfirm /></>
 *
 * const result = await client.run(blueprint, { inputs, onEvent: setProgress });
 * ```
 *
 * Importer ce module **enregistre le driver** Continuum aupres du moteur : une application n'a
 * jamais a cabler l'act a la main. Reference d'usage, protocole et limites declarees :
 * docs/embedded.md.
 */

import { registerContinuum } from "./registry.js";

export { Aetherius, type AetheriusConfig, type BlueprintSource, type RunOptions } from "./aetherius.js";
export {
  BlueprintRegistry,
  CACHE_KEY,
  MANIFEST_FORMAT,
  ManifestError,
  compareVersions,
  memoryCache,
  parseManifest,
  resolveUrl,
  sha256Hex,
  type AllowNew,
  type BlueprintCacheStore,
  type BlueprintOrigin,
  type BlueprintStatus,
  type BundledBlueprint,
  type CachedBlueprint,
  type Manifest,
  type ManifestEntry,
  type RefreshEntry,
  type RefreshOutcome,
  type RefreshReport,
  type RegistryConfig,
  type ResolvedBlueprint,
} from "./delivery/index.js";
export { ContinuumDriver, type HostProvider } from "./continuum/driver.js";
export { AGENT_ACTIONS, failureCode, type AgentOp } from "./continuum/actions.js";
export {
  AetheriusConfirm,
  ConfirmGateway,
  defaultConfirmGateway,
  useApprovalRequest,
  type AetheriusConfirmProps,
  type ApprovalControls,
  type ApprovalListener,
} from "./confirm/index.js";
export { useAetheriusRun, type RunState } from "./hooks/use-run.js";
export {
  REDACTED,
  keychainSecrets,
  redactEvent,
  redactText,
  redactValue,
  redactingSink,
  staticSecrets,
  type KeychainOptions,
  type SecretResolver,
  type SecretStore,
} from "./secrets/index.js";
export { AetheriusWebView, type AetheriusWebViewProps } from "./webview/component.js";
export { BridgedHost, NAVIGATION_SETTLE_MS } from "./webview/bridged-host.js";
export { evaluateSource } from "./webview/evaluate.js";
export { acquireWebViewHost, releaseWebViewHost, webViewLease } from "./webview/lease.js";
export { AgentBridge, type Inject } from "./webview/rpc.js";
export { AGENT_SHA256, AGENT_SOURCE } from "./generated/agent-source.js";
export { currentWebViewHost, registerContinuum, setWebViewHost } from "./registry.js";
export type { PageControl, SessionConfig, WebViewHost } from "./webview/host.js";
export {
  AGENT_GEN_GLOBAL,
  AGENT_GLOBAL,
  MAX_MESSAGE_CHARS,
  MAY_NAVIGATE,
  OPS,
  PROTOCOL_VERSION,
  dispatchSource,
  installSource,
  isAgentMessage,
  isChunk,
  isReady,
  type AgentMessage,
  type AgentReady,
  type AgentRequest,
  type AgentResult,
  type OpName,
} from "./webview/protocol.js";

/**
 * Le modele d'erreur, re-exporte depuis le moteur.
 *
 * Une application n'a qu'une porte d'entree : elle importe `describeFailure` d'ici, et n'a pas a
 * savoir que la hierarchie d'erreurs vit dans le paquet neutre.
 */
export {
  ActionError,
  AetheriusError,
  BlueprintError,
  BlueprintLoadError,
  BlueprintSchemaError,
  BlueprintValidationError,
  DependencyError,
  ExtractionError,
  NetworkError,
  RetryExhaustedError,
  RunCancelledError,
  RunError,
  StatusAssertionError,
  StepTimeoutError,
  TemplateError,
  TimeoutError,
  describeFailure,
  type Failure,
  type FailureKind,
  type Result,
  type RunEvent,
  type StepResult,
} from "@aetherius/engine";

// Registering on import is what makes the engine's message ("import '@aetherius/react-native',
// which registers the WebView driver") true: an application never has to wire the act by hand.
registerContinuum();
