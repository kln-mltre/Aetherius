/**
 * Le panneau de livraison : d'ou vient le Blueprint qu'on s'apprete a jouer.
 *
 * Il n'apparait que pour la carte livrable. Trois choses a l'ecran, et ce sont les trois gestes du
 * jalon : voir l'**origine** (embarque / distant, avec sa version), **rafraichir** depuis le
 * manifeste, et **revenir a l'embarque** — l'interrupteur d'arret, sans lequel un mecanisme de
 * deploiement n'en est pas un.
 *
 * Le rapport de rafraichissement est affiche tel quel, entree par entree : c'est lui qui dit
 * *pourquoi* une correction n'a pas ete prise (empreinte fausse, secret hors perimetre, moteur trop
 * ancien), et un publieur qui ne le voit pas debuggue a l'aveugle.
 */

import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { COLORS } from "./theme";

const OUTCOME_COLOR = {
  updated: COLORS.laurel,
  kept: COLORS.stone,
  ignored: COLORS.amber,
  rejected: COLORS.pompeian,
};

export default function DeliveryPanel({ delivery }) {
  const { manifestUrl, setManifestUrl, status, report, busy, refresh, revert } = delivery;
  const remote = status?.origin === "remote";

  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>Livraison</Text>

      <Text style={[styles.origin, { color: remote ? COLORS.laurel : COLORS.stone }]}>
        {status === null
          ? "…"
          : `${remote ? "distant" : "embarque"} · v${status.version}${
              remote ? "" : " (la version cassee)"
            }`}
      </Text>

      <Text style={styles.hint}>
        L'URL du manifeste. Sur le reseau du poste : http://IP-DU-POSTE:8000/manifest.json
      </Text>
      <TextInput
        value={manifestUrl}
        onChangeText={setManifestUrl}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        placeholder="https://…/manifest.json"
        placeholderTextColor={COLORS.stone}
        style={styles.input}
      />

      <View style={styles.row}>
        <Pressable onPress={refresh} disabled={busy} style={[styles.action, busy && styles.faded]}>
          {busy ? (
            <ActivityIndicator color={COLORS.violet} />
          ) : (
            <Text style={styles.actionLabel}>Rafraichir</Text>
          )}
        </Pressable>
        <Pressable onPress={revert} style={styles.action}>
          <Text style={styles.actionLabel}>Revenir a l'embarque</Text>
        </Pressable>
      </View>

      {report !== null && (
        <View style={styles.report}>
          <Text style={[styles.line, { color: report.ok ? COLORS.moonlight : COLORS.amber }]}>
            {report.ok ? "manifeste lu" : `manifeste non lu : ${report.reason}`}
          </Text>
          {report.entries.map((entry) => (
            <Text key={entry.name} style={[styles.line, { color: OUTCOME_COLOR[entry.outcome] }]}>
              {`${entry.outcome}${entry.version ? ` v${entry.version}` : ""} · ${entry.name}${
                entry.reason ? `\n  ${entry.reason}` : ""
              }`}
            </Text>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    backgroundColor: COLORS.nimbus,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.panel,
    padding: 14,
    gap: 8,
  },
  sectionTitle: { color: COLORS.violet, fontSize: 13, letterSpacing: 2, textTransform: "uppercase" },
  origin: { fontSize: 15, fontWeight: "700" },
  hint: { color: COLORS.stone, fontSize: 12, lineHeight: 17 },
  input: {
    backgroundColor: COLORS.void,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: COLORS.panel,
    color: COLORS.moonlight,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 13,
  },
  row: { flexDirection: "row", gap: 10 },
  action: {
    flex: 1,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: COLORS.violet,
    paddingVertical: 11,
    alignItems: "center",
  },
  faded: { opacity: 0.6 },
  actionLabel: { color: COLORS.violet, fontSize: 14, fontWeight: "600" },
  report: { gap: 4, marginTop: 2 },
  line: { fontFamily: "monospace", fontSize: 11, lineHeight: 16 },
});
