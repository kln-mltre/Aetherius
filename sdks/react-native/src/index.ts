/**
 * `@aetherius/react-native` — l'Act II sur appareil, et la surface que consomme une application.
 *
 * Ce paquet apporte ce que `@aetherius/engine` ne peut pas porter sans dependre d'une plateforme :
 * le driver Continuum adosse a une WebView cachee, la resolution des secrets par le trousseau, et
 * la facade `Aetherius` que l'application appelle.
 *
 * Squelette Phase 3 : seules les interfaces sont posees. Voir docs/phase-3/README.md.
 */

export type { SecretResolver } from "./secrets.js";
export type { WebViewHost, WebViewOp } from "./webview/host.js";
