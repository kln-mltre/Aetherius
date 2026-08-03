/**
 * `<AetheriusConfirm />` — le modal par defaut d'un step `confirm`.
 *
 * Monte-le une fois, haut dans l'arbre, a cote de `<AetheriusWebView />` : un run gare y pose sa
 * question et repart des que l'utilisateur repond. Sans lui, un `confirm` reste **non surveille** et
 * applique sa politique `on_timeout` tout de suite — refus par defaut. Ce n'est pas une panne : un
 * run non surveille est sur, il ne fait simplement rien de sensible.
 *
 * Le composant est volontairement mince, parce que la vraie surface publique est
 * `useApprovalRequest` : une application qui a son propre langage visuel passe une prop `render`,
 * ou n'utilise pas ce fichier du tout. Ce qui ne doit pas etre reecrit, c'est la logique du
 * rendez-vous — pas les couleurs.
 *
 * Palette empruntee a la Console (`src/aetherius/console/theme.py`), pour que les deux surfaces du
 * meme outil se ressemblent.
 */

import type { ReactElement, ReactNode } from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";

import type { ApprovalRequest } from "@aetherius/engine";

import { defaultConfirmGateway, type ConfirmGateway } from "./gateway.js";
import { useApprovalRequest } from "./use-approval.js";

const COLORS = {
  scrim: "rgba(20, 16, 32, 0.72)",
  panel: "#1c1730",
  border: "#282045",
  text: "#dcd7e8",
  muted: "#7f7a90",
  accent: "#9d7bd8",
  deny: "#c1564a",
  void: "#141020",
};

export interface AetheriusConfirmProps {
  /** La passerelle a ecouter. Celle de la facade par defaut. */
  readonly gateway?: ConfirmGateway;
  readonly approveLabel?: string;
  readonly rejectLabel?: string;
  /** Remplace entierement l'habillage ; la logique du rendez-vous reste celle du hook. */
  readonly render?: (props: {
    readonly request: ApprovalRequest;
    readonly approve: () => void;
    readonly reject: () => void;
  }) => ReactNode;
}

export function AetheriusConfirm({
  gateway = defaultConfirmGateway,
  approveLabel = "Approuver",
  rejectLabel = "Refuser",
  render,
}: AetheriusConfirmProps = {}): ReactElement | null {
  const { request, approve, reject } = useApprovalRequest(gateway);
  if (request === undefined) return null;

  const decline = (): void => reject();

  return (
    <Modal visible transparent animationType="fade" onRequestClose={decline}>
      {render !== undefined ? (
        render({ request, approve: () => approve(), reject: decline })
      ) : (
        <View style={styles.scrim}>
          <View style={styles.panel}>
            {request.title !== undefined && <Text style={styles.title}>{request.title}</Text>}
            <Text style={styles.message}>{request.message}</Text>
            <View style={styles.actions}>
              {/* Le refus est a gauche et discret, l'approbation a droite et affirmee : sur une
                  action sensible, la geste par defaut ne doit pas etre celle qui engage. */}
              <Pressable
                style={styles.reject}
                onPress={decline}
                accessibilityRole="button"
                accessibilityLabel={rejectLabel}
              >
                <Text style={styles.rejectLabel}>{rejectLabel}</Text>
              </Pressable>
              <Pressable
                style={styles.approve}
                onPress={() => approve()}
                accessibilityRole="button"
                accessibilityLabel={approveLabel}
              >
                <Text style={styles.approveLabel}>{approveLabel}</Text>
              </Pressable>
            </View>
          </View>
        </View>
      )}
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: {
    flex: 1,
    backgroundColor: COLORS.scrim,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
  },
  panel: {
    width: "100%",
    maxWidth: 420,
    backgroundColor: COLORS.panel,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: 20,
    gap: 12,
  },
  title: { color: COLORS.accent, fontSize: 13, letterSpacing: 2, textTransform: "uppercase" },
  message: { color: COLORS.text, fontSize: 16, lineHeight: 23 },
  actions: { flexDirection: "row", justifyContent: "flex-end", gap: 10, marginTop: 8 },
  reject: { paddingVertical: 12, paddingHorizontal: 18, borderRadius: 10 },
  rejectLabel: { color: COLORS.deny, fontSize: 15, fontWeight: "600" },
  approve: {
    backgroundColor: COLORS.accent,
    paddingVertical: 12,
    paddingHorizontal: 22,
    borderRadius: 10,
  },
  approveLabel: { color: COLORS.void, fontSize: 15, fontWeight: "700" },
});
