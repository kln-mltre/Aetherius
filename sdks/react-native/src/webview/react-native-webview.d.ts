/**
 * The slice of `react-native-webview` this package uses, declared structurally.
 *
 * Same posture as the engine's `src/http.ts` for `fetch`: the surface is *declared*, not borrowed.
 * Depending on `react-native` and `react-native-webview` for their types would drag a hundred
 * megabytes of development dependencies into a workspace whose gate runs on every change, to type
 * a dozen props. The real packages are peer dependencies, resolved by the application.
 *
 * Only what is actually used is here. Anything missing is a deliberate omission, not an oversight:
 * `enableApplePay`, for instance, silently disables `injectJavaScript` on iOS and has no business
 * being reachable from this package.
 */

declare module "react-native-webview" {
  import type { ComponentType, Ref } from "react";

  export interface WebViewNavigation {
    readonly url: string;
    readonly loading: boolean;
    readonly title?: string;
  }

  export interface WebViewMessageEvent {
    readonly nativeEvent: { readonly data: string };
  }

  export interface WebViewLoadEvent {
    readonly nativeEvent: { readonly url: string; readonly loading?: boolean };
  }

  export interface WebViewErrorEvent {
    readonly nativeEvent: { readonly url?: string; readonly description?: string };
  }

  /** The imperative handle the host drives: injection, history, and stopping a load. */
  export interface WebViewHandle {
    injectJavaScript(source: string): void;
    goBack(): void;
    goForward(): void;
    reload(): void;
    stopLoading(): void;
  }

  export interface WebViewProps {
    readonly ref?: Ref<WebViewHandle>;
    readonly source?: { readonly uri: string };
    /** The *inner* native view. It must keep a real size: this is not where hiding happens. */
    readonly style?: unknown;
    /**
     * The wrapper the library renders around the native view (`flex: 1`, `overflow: hidden`).
     *
     * This is where an off-screen position belongs. Hiding the inner view instead leaves the
     * WebView with no rendered area inside a clipping container — and a WKWebView with no area is
     * how the web content process gets terminated.
     */
    readonly containerStyle?: unknown;
    readonly incognito?: boolean;
    readonly sharedCookiesEnabled?: boolean;
    readonly thirdPartyCookiesEnabled?: boolean;
    readonly javaScriptEnabled?: boolean;
    readonly domStorageEnabled?: boolean;
    readonly originWhitelist?: readonly string[];
    readonly userAgent?: string;
    readonly setSupportMultipleWindows?: boolean;
    readonly onLoadStart?: (event: WebViewLoadEvent) => void;
    readonly onLoadEnd?: (event: WebViewLoadEvent) => void;
    readonly onError?: (event: WebViewErrorEvent) => void;
    /** iOS: the web content process died. Without a handler, the view is left blank for good. */
    readonly onContentProcessDidTerminate?: (event: WebViewErrorEvent) => void;
    readonly onMessage?: (event: WebViewMessageEvent) => void;
    readonly onNavigationStateChange?: (state: WebViewNavigation) => void;
    readonly onShouldStartLoadWithRequest?: (request: { readonly url: string }) => boolean;
  }

  export const WebView: ComponentType<WebViewProps>;
}
