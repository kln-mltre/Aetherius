/**
 * The demo screen: pick a Blueprint, run it on the device, watch what the engine says.
 *
 * A verification bench, not a showcase. It exists so milestone 3-C can honour point 5 of
 * CONTRIBUTING — "the real run, not just the tests" — on the only environment that counts here, a
 * phone. The engine is called directly (`RunEngine`), because the application facade is milestone
 * 3-E; when it lands, this screen switches to it and gets shorter.
 *
 * Palette borrowed from the Console (src/aetherius/console/theme.py) so the two surfaces of the
 * same tool look like the same tool.
 */

import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { StatusBar } from "expo-status-bar";
import { RunEngine, validateBlueprintData } from "@aetherius/engine";

import { BLUEPRINTS } from "./blueprints";

const COLORS = {
  void: "#141020",
  nimbus: "#1c1730",
  panel: "#282045",
  moonlight: "#dcd7e8",
  stone: "#7f7a90",
  violet: "#9d7bd8",
  gold: "#d4af37",
  laurel: "#4e8a5a",
  amber: "#d08a3e",
  pompeian: "#c1564a",
};

const LEVEL_COLOR = {
  error: COLORS.pompeian,
  warning: COLORS.amber,
  info: COLORS.moonlight,
  debug: COLORS.stone,
};

export default function App() {
  const [selected, setSelected] = useState(BLUEPRINTS[0].key);
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState([]);
  const [result, setResult] = useState(null);
  const [failure, setFailure] = useState(null);

  const entry = useMemo(() => BLUEPRINTS.find((item) => item.key === selected), [selected]);

  const run = useCallback(async () => {
    setRunning(true);
    setEvents([]);
    setResult(null);
    setFailure(null);

    // The event stream *is* the progress UI: an application does not need a state machine of its
    // own to show where a run is (docs/embedded.md).
    const collected = [];
    const sink = {
      onEvent(event) {
        collected.push(event);
        setEvents([...collected]);
      },
    };

    try {
      // Validate first so a malformed Blueprint is a message, not a mid-run surprise.
      const blueprint = validateBlueprintData(entry.blueprint, entry.key);
      setResult(await new RunEngine().run(blueprint, { sinks: [sink] }));
    } catch (error) {
      // Typed errors reach the caller on purpose: a broken source and an empty answer must stay
      // distinguishable, which is exactly what a mobile service layer usually loses.
      setFailure(`${error.name}: ${error.message}`);
    } finally {
      setRunning(false);
    }
  }, [entry]);

  return (
    <View style={styles.screen}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Aetherius</Text>
        <Text style={styles.subtitle}>moteur embarque · Act I sur fetch</Text>

        <View style={styles.group}>
          {BLUEPRINTS.map((item) => {
            const active = item.key === selected;
            return (
              <Pressable
                key={item.key}
                onPress={() => setSelected(item.key)}
                style={[styles.card, active && styles.cardActive]}
              >
                <Text style={[styles.cardTitle, active && styles.cardTitleActive]}>
                  {item.title}
                </Text>
                <Text style={styles.cardHint}>{item.hint}</Text>
              </Pressable>
            );
          })}
        </View>

        <Pressable
          onPress={run}
          disabled={running}
          style={[styles.button, running && styles.buttonDisabled]}
        >
          {running ? (
            <ActivityIndicator color={COLORS.void} />
          ) : (
            <Text style={styles.buttonLabel}>Lancer le run</Text>
          )}
        </Pressable>

        {events.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Evenements</Text>
            {events.map((event, index) => (
              <Text key={index} style={[styles.event, { color: LEVEL_COLOR[event.level] }]}>
                {`[${event.type}]${event.step_id ? ` ${event.step_id}` : ""}${
                  event.message ? ` ${event.message}` : ""
                }`}
              </Text>
            ))}
          </View>
        )}

        {result !== null && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>
              Resultat
              <Text style={{ color: result.status === "success" ? COLORS.laurel : COLORS.pompeian }}>
                {`  ${result.status}`}
              </Text>
            </Text>
            {result.error !== undefined && <Text style={styles.error}>{result.error}</Text>}
            <Text style={styles.code}>{JSON.stringify(result.outputs, null, 2)}</Text>
          </View>
        )}

        {failure !== null && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Refus</Text>
            <Text style={styles.error}>{failure}</Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.void },
  content: { padding: 20, paddingTop: 64, gap: 16 },
  title: { color: COLORS.gold, fontSize: 30, fontWeight: "600", letterSpacing: 3 },
  subtitle: { color: COLORS.stone, fontSize: 13, marginTop: -12, letterSpacing: 1 },
  group: { gap: 10, marginTop: 8 },
  card: {
    backgroundColor: COLORS.nimbus,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.panel,
    padding: 14,
  },
  cardActive: { borderColor: COLORS.violet, backgroundColor: COLORS.panel },
  cardTitle: { color: COLORS.moonlight, fontSize: 16, fontWeight: "600" },
  cardTitleActive: { color: COLORS.violet },
  cardHint: { color: COLORS.stone, fontSize: 12, marginTop: 4, lineHeight: 17 },
  button: {
    backgroundColor: COLORS.violet,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: "center",
  },
  buttonDisabled: { opacity: 0.6 },
  buttonLabel: { color: COLORS.void, fontSize: 16, fontWeight: "700", letterSpacing: 1 },
  section: {
    backgroundColor: COLORS.nimbus,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.panel,
    padding: 14,
    gap: 6,
  },
  sectionTitle: { color: COLORS.violet, fontSize: 13, letterSpacing: 2, textTransform: "uppercase" },
  event: { color: COLORS.moonlight, fontFamily: "monospace", fontSize: 11, lineHeight: 16 },
  code: { color: COLORS.moonlight, fontFamily: "monospace", fontSize: 12, lineHeight: 18 },
  error: { color: COLORS.pompeian, fontSize: 12, lineHeight: 18 },
});
