/**
 * The slice of `react-native` this package uses, declared structurally.
 *
 * Same posture — and the same reason — as `webview/react-native-webview.d.ts`: `react-native` is a
 * peer dependency, resolved by the application. Installing it in this workspace to type one modal
 * would drag a hundred megabytes of development dependencies into a gate that runs on every change,
 * and would put a second copy of React in reach of the build.
 *
 * Only what the default confirmation modal uses is declared. Anything an application wants beyond
 * that belongs in *its* code, behind `useApprovalRequest`.
 */

declare module "react-native" {
  import type { ComponentType, ReactNode } from "react";

  /** A style object. Kept opaque: this package composes styles, it never inspects them. */
  export type Style = unknown;

  export interface ViewProps {
    readonly style?: Style;
    readonly children?: ReactNode;
  }

  export interface TextProps extends ViewProps {
    readonly numberOfLines?: number;
  }

  export interface PressableProps extends ViewProps {
    readonly onPress?: () => void;
    readonly accessibilityRole?: string;
    readonly accessibilityLabel?: string;
  }

  export interface ModalProps extends ViewProps {
    readonly visible?: boolean;
    readonly transparent?: boolean;
    readonly animationType?: "none" | "slide" | "fade";
    /** Android's back button, and iOS' swipe-to-dismiss where the platform offers one. */
    readonly onRequestClose?: () => void;
  }

  export const View: ComponentType<ViewProps>;
  export const Text: ComponentType<TextProps>;
  export const Pressable: ComponentType<PressableProps>;
  export const Modal: ComponentType<ModalProps>;

  export const StyleSheet: {
    create<T extends Record<string, unknown>>(styles: T): T;
  };
}
