/**
 * Le joint entre le driver Continuum et la WebView reelle.
 *
 * Playwright n'existe pas sur appareil : il n'y a ni moteur de locators, ni auto-attente, ni appel
 * synchrone dans la page. Le driver pilote donc un agent JavaScript injecte, via une RPC correlee
 * (`injectJavaScript` d'un cote, `window.ReactNativeWebView.postMessage` de l'autre).
 *
 * Cette interface est volontairement la seule chose que le driver connait de React Native : elle
 * rend le driver testable hors simulateur et garde le paquet compilable sans les peer dependencies.
 *
 * Regle de securite structurante : les parametres d'une operation traversent **encodes en JSON**,
 * jamais interpoles dans la source du script injecte. C'est ce qui rend impossible par construction
 * la classe de bug qu'on trouve aujourd'hui dans les WebView ecrites a la main (un mot de passe
 * contenant une apostrophe qui casse le script, ou pire).
 *
 * Squelette Phase 3 : le protocole d'operations, l'agent injecte et le cycle de vie de navigation
 * sont specifies au jalon 3-D (docs/phase-3/3-d-continuum.md).
 */

/** Une operation adressee a l'agent injecte. Le vocabulaire exact est fige au jalon 3-D. */
export interface WebViewOp {
  readonly op: string;
  readonly params: Readonly<Record<string, unknown>>;
  readonly timeoutMs: number;
}

export interface WebViewHost {
  /** Charge une URL et resout quand la page est prete et l'agent reinjecte. */
  navigate(url: string, timeoutMs: number): Promise<void>;

  /** Envoie une operation a l'agent injecte et attend sa reponse correlee. */
  call(op: WebViewOp): Promise<unknown>;

  /** Libere la WebView (et, selon `options.session.persist`, la session et ses cookies). */
  dispose(): Promise<void>;
}
