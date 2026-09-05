/**
 * `<AetheriusWebView />` — the hidden WebView a `continuum` Blueprint runs in.
 *
 * Mount it once, high in the application tree, and leave it there: a WebView is a component, and
 * its lifetime belongs to the tree, not to a run. It publishes a `WebViewHost` the Continuum driver
 * picks up (`registry.ts`), and it is the *only* file in this package that touches React Native.
 *
 * **The view itself is created lazily**, at the first `continuum` run — not at mount. An
 * application that only ever plays Act I should not carry a hidden WebView (and its native web
 * process) for nothing, and a run gets exactly one view creation instead of one at start-up plus a
 * remount once the Blueprint's session options are known.
 *
 * Three props of the view carry more weight than their size suggests:
 *
 *   - **`key`**. Session options are bound when the view is created on both platforms, so changing
 *     `persist` or the user agent means recreating it. Bumping the key is the only reliable way,
 *     and it is what the hand-written implementations settled on too.
 *   - **`incognito`**. This is `options.session.persist`, and on a phone the choice is visible to
 *     the user: an isolated session starts clean and asks for credentials every time; a persistent
 *     one does not, but its state outlives the run. Two non-incognito WebViews already share their
 *     cookies — the default data store is process-wide — so persisting is all it takes for a browser
 *     screen to open on an authenticated page.
 *   - **`sharedCookiesEnabled`**. Deliberately **not** tied to `persist`, and off unless a Blueprint
 *     asks for it. It bridges the *native* cookie jar into the view, which only a Blueprint mixing
 *     Act I and Act II needs — and it costs a main-queue copy of every cookie the application holds,
 *     which is a visible freeze that grows with use. See `SessionConfig.shareNativeCookies`.
 *   - **`setSupportMultipleWindows={false}`**. New windows are refused, not followed. In a hidden
 *     WebView, opening one has no meaning — a declared divergence from the Python engine, which
 *     follows new tabs.
 */

import { useEffect, useMemo, useRef, useState, type ReactElement } from "react";
import { WebView, type WebViewHandle } from "react-native-webview";

import { AGENT_SOURCE } from "../generated/agent-source.js";
import { setWebViewHost } from "../registry.js";
import { BridgedHost } from "./bridged-host.js";
import type { PageControl, SessionConfig } from "./host.js";

/**
 * Hiding happens on the **container**, never on the view — and "hidden" here means *hidden from the
 * person, not from the platform*. That distinction is the whole of this constant.
 *
 * `react-native-webview` renders `<View style={[{flex: 1, overflow: 'hidden'}, containerStyle]}>`
 * around the native view. Positioning the inner view off-screen therefore leaves it clipped to
 * nothing inside that container — a WKWebView with no rendered area, which is how iOS ends up
 * terminating the web content process. The container carries the position; the view keeps a real,
 * deterministic size.
 *
 * A full desktop-ish viewport rather than a token one, because a responsive portal serves a
 * different DOM to a small screen — and never `display: none`, because a view that lays nothing out
 * would make every element read as invisible.
 *
 * ## Why it sits *inside* the window, at one percent
 *
 * WebKit decides a page is hidden from three things, and a real size is only the first: the view
 * must also be **in the window's bounds** and **not fully transparent**. An earlier version kept the
 * size but parked the container at `left: -10000` with `opacity: 0`, which satisfies one signal and
 * fails the other two. WebKit then treats the page as backgrounded and is free to stop giving it
 * what it needs to finish work — and a navigation that depends on the page's own JavaScript to
 * continue (an SSO cascade, a SAML auto-submit) simply stops advancing.
 *
 * **Measured on an iPhone, 2026-09-05**, on a university portal reached through a full SSO cascade:
 * the first `navigate` never completed, at 30 s and again at 60 s, while a *retry* — where the
 * service session already existed and no cascade was needed — landed in 281 ms. The same run with
 * the view made visible (`options.debug`) passed first time, every time. Off-screen and transparent
 * was the difference, and nothing else was.
 *
 * So the container stays in the window, at `opacity: 0.01` — enough for WebKit, imperceptible to the
 * eye — and `zIndex: -1` puts it behind everything the host application draws, which is what keeps
 * it out of sight. `pointerEvents: "none"` is belt and braces: a view nobody can see must not be a
 * view anybody can touch.
 *
 * The cost is honest and worth stating: on a host whose own content is translucent, a one-percent
 * ghost of the page is *technically* on screen. Nobody has ever seen it, and the alternative is an
 * engine that cannot log in.
 */
const HIDDEN_CONTAINER = {
  position: "absolute" as const,
  left: 0,
  top: 0,
  width: 1024,
  height: 768,
  // Not zero: zero is what tells WebKit the page is hidden. See above.
  opacity: 0.01,
  // Behind whatever the host draws — this is what actually hides it.
  zIndex: -1,
  pointerEvents: "none" as const,
};

/** Debug: the WebView overlays the application, which is the point of watching it. */
const VISIBLE_CONTAINER = {
  position: "absolute" as const,
  left: 0,
  top: 0,
  right: 0,
  bottom: 0,
};

/** The native view always fills its container, hidden or not: it must have a layout. */
const WEBVIEW_STYLE = { flex: 1 };

const DEFAULT_SESSION: SessionConfig = {
  persist: false,
  shareNativeCookies: false,
  debug: false,
  userAgent: undefined,
};

function sameSession(left: SessionConfig, right: SessionConfig): boolean {
  return (
    left.persist === right.persist &&
    left.shareNativeCookies === right.shareNativeCookies &&
    left.debug === right.debug &&
    left.userAgent === right.userAgent
  );
}

export interface AetheriusWebViewProps {
  /** Called when the view reports a load error, so an application can surface it. */
  readonly onLoadError?: (message: string) => void;
}

export function AetheriusWebView({ onLoadError }: AetheriusWebViewProps = {}): ReactElement | null {
  const ref = useRef<WebViewHandle | null>(null);
  const [session, setSession] = useState<SessionConfig>(DEFAULT_SESSION);
  const [mountKey, setMountKey] = useState(0);
  // The view is created with the URL it is going to load — no blank placeholder, so a run costs one
  // load instead of two and there is no intermediate document to reason about. `undefined` means
  // "no view": nothing is rendered until a run navigates somewhere.
  const [uri, setUri] = useState<string | undefined>(undefined);

  // `useRef` rather than state: the host is driven imperatively by the run, and re-rendering on
  // every operation would be both pointless and a source of stale closures.
  const sessionRef = useRef(session);
  sessionRef.current = session;
  // Same reason, for the URI: `page` is memoised once and would otherwise read the value of the
  // render that built it.
  const uriRef = useRef(uri);
  uriRef.current = uri;

  const host = useMemo(() => {
    const page: PageControl = {
      load: (target) => {
        // Setting the URI the view already has changes no prop, so React re-renders nothing and the
        // view does not load — while the host is waiting for a document. The host only asks for a
        // `load` on a URL the view already carries when the previous navigation *failed*, which is
        // precisely the retry an application offers after "service unavailable". A new key is the
        // reliable way to say "start over" here, exactly as a session change does.
        if (uriRef.current === target) setMountKey((key) => key + 1);
        setUri(target);
      },
      goBack: () => ref.current?.goBack(),
      goForward: () => ref.current?.goForward(),
      reload: () => ref.current?.reload(),
      inject: (source) => ref.current?.injectJavaScript(source),
      applySession: (config) => {
        const unchanged = sessionRef.current !== undefined && sameSession(sessionRef.current, config);
        sessionRef.current = config;
        setSession(config);
        // Session options are bound at creation, so a change means the next `load` must build a new
        // view rather than reuse the current one.
        if (unchanged && ref.current !== null) return false;
        setUri(undefined);
        setMountKey((key) => key + 1);
        return true;
      },
      destroy: () => {
        // The run is over: the view goes with it, and — for an isolated session — the store that
        // came with it. The component stays mounted, ready to create another one.
        ref.current?.stopLoading();
        ref.current = null;
        setUri(undefined);
        setMountKey((key) => key + 1);
      },
    };
    return new BridgedHost(page, AGENT_SOURCE);
  }, []);

  useEffect(() => {
    setWebViewHost(host);
    return () => {
      setWebViewHost(undefined);
      void host.dispose();
    };
  }, [host]);

  if (uri === undefined) return null;

  return (
    <WebView
      key={mountKey}
      ref={ref}
      source={{ uri }}
      style={WEBVIEW_STYLE}
      containerStyle={session.debug ? VISIBLE_CONTAINER : HIDDEN_CONTAINER}
      incognito={!session.persist}
      sharedCookiesEnabled={session.shareNativeCookies}
      thirdPartyCookiesEnabled={session.persist}
      javaScriptEnabled
      domStorageEnabled
      originWhitelist={["*"]}
      setSupportMultipleWindows={false}
      {...(session.userAgent !== undefined ? { userAgent: session.userAgent } : {})}
      onLoadStart={(event) => {
        host.onLoadStarted(event.nativeEvent.url);
      }}
      onLoadEnd={(event) => {
        host.onDocumentLoaded(event.nativeEvent.url);
      }}
      onError={(event) => {
        const description =
          event.nativeEvent.description ?? "the WebView failed to load the document";
        // The host is told, not just the application: a run waiting on this document must fail as
        // "the source is unreachable" rather than time out and look like an engine problem.
        host.onLoadFailed(description);
        onLoadError?.(description);
      }}
      onContentProcessDidTerminate={() => {
        // iOS kills the web content process under memory pressure — and leaves the view blank for
        // good unless someone reloads it. Saying so beats a run that waits for a page that will
        // never come back.
        onLoadError?.("the WebView's content process was terminated by the system");
        host.onContentProcessLost();
      }}
      onMessage={(event) => {
        host.onMessage(event.nativeEvent.data);
      }}
      onNavigationStateChange={(state) => {
        // A fragment or single-page route change fires this without a load: the document is the
        // same one, but a framework may have replaced everything under it. Re-injecting is a no-op
        // for a generation already installed, so this is cheap and never double-installs.
        if (!state.loading) host.ensureAgent();
      }}
    />
  );
}
