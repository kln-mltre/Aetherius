/**
 * L'ecran de demonstration : choisir un Blueprint, le jouer sur l'appareil, voir ce que le moteur
 * en dit.
 *
 * Banc de verification, pas vitrine. Il existe pour honorer le point 5 de CONTRIBUTING — « le vrai
 * run, pas seulement les tests » — sur le seul environnement qui compte ici, un telephone.
 *
 * Depuis le jalon 3-E il passe par la **facade** : `new Aetherius({ secrets })` puis
 * `useAetheriusRun`, la ou il appelait `RunEngine` a la main. L'ecran a raccourci, et c'est le
 * propos — la progression, les secrets, la confirmation et la traduction des erreurs ne sont plus
 * du code applicatif.
 *
 * Trois composants montes une fois, en bas de l'arbre, parce que leur vie appartient a l'arbre et
 * pas a un run : la WebView cachee (Act II) et le modal de confirmation.
 *
 * Palette empruntee a la Console (src/aetherius/console/theme.py) pour que les deux surfaces du
 * meme outil se ressemblent.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { StatusBar } from "expo-status-bar";
import * as SecureStore from "expo-secure-store";
import {
  Aetherius,
  AetheriusConfirm,
  AetheriusWebView,
  keychainSecrets,
  useAetheriusRun,
} from "@aetherius/react-native";

import { BLUEPRINTS, STATUS } from "./blueprints";

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

/**
 * Ce qu'une application affiche pour chaque famille d'echec.
 *
 * Le tableau *est* le motif recommande : `describeFailure` rend un `kind`, l'application decide
 * d'un ecran. Sans lui, une source en panne et une reponse vide finissent sur le meme « aucun
 * resultat », et l'utilisateur ne sait pas laquelle des deux il regarde.
 */
const FAILURE_COPY = {
  unavailable: ["Service indisponible", "La source n'a pas repondu. Reessayer plus tard."],
  blocked: ["Etape bloquee", "Le Blueprint a nomme cet echec : voir le code ci-dessous."],
  data: ["La page a change", "Le site ne ressemble plus a ce que le Blueprint decrit."],
  // Distinct de `data`, et la sonde sur appareil a montre pourquoi : un secret absent du trousseau
  // affichait « la page a change ». La page allait tres bien.
  config: ["Donnee manquante", "Un secret ou une entree n'a pas ete fournie. Verifie le trousseau."],
  rejected: ["Reponse inattendue", "La source a repondu, mais pas comme le Blueprint l'exigeait."],
  blueprint: ["Blueprint refuse", "Le fichier est invalide ou non jouable sur cet appareil."],
  unsupported: ["Capacite absente", "Une piece de plateforme manque (WebView, fetch)."],
  cancelled: ["Annule", "Le run a ete interrompu."],
  engine: ["Erreur interne", "Ceci est un bug du moteur : a remonter."],
};

// Une seule instance : elle porte le resolver de secrets et la table des runs en cours.
const client = new Aetherius({ secrets: keychainSecrets(SecureStore) });

/**
 * Applique les deux options qu'un banc de verification doit pouvoir basculer sans reediter un
 * fichier : `options.debug` (la WebView devient visible) et `options.session.persist` (la session
 * survit au run, et donc au redemarrage de l'application). Les deux ne se verifient que sur un
 * appareil, ce qui est precisement la raison d'etre de cet ecran.
 */
function withOptions(blueprint, { debug, persist }) {
  const options = { ...blueprint.options };
  if (debug) options.debug = true;
  if (persist) options.session = { ...options.session, persist: true };
  return { ...blueprint, options };
}

export default function App() {
  const [selected, setSelected] = useState(BLUEPRINTS[0].key);
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [saved, setSaved] = useState(false);
  const [notice, setNotice] = useState(null);
  const [debug, setDebug] = useState(false);
  const [persist, setPersist] = useState(false);
  const [stored, setStored] = useState(null);

  const entry = useMemo(() => BLUEPRINTS.find((item) => item.key === selected), [selected]);
  const { running, events, result, failure, run, cancel } = useAetheriusRun(client);

  // Lire le trousseau plutot que de supposer : le premier run sur appareil a echoue parce que les
  // identifiants n'y etaient pas, et rien a l'ecran ne le disait.
  useEffect(() => {
    let alive = true;
    if (entry.secrets === undefined) {
      setStored(null);
      return () => {};
    }
    void (async () => {
      const found = await Promise.all(entry.secrets.map((name) => SecureStore.getItemAsync(name)));
      if (alive) setStored(found.every((value) => value !== null && value !== ""));
    })();
    return () => {
      alive = false;
    };
  }, [entry, saved]);

  // Les secrets sont saisis une fois et vont dans le trousseau de l'OS, sous les noms que le
  // Blueprint declare ; ensuite le resolver les relit tout seul, run apres run, lancement apres
  // lancement. Ils ne sont jamais dans le Blueprint.
  const storeSecrets = useCallback(async () => {
    const [userKey, passKey] = entry.secrets;
    await SecureStore.setItemAsync(userKey, user);
    await SecureStore.setItemAsync(passKey, password);
    setSaved(true);
    setNotice(`Ranges dans le trousseau : ${userKey}, ${passKey}.`);
  }, [entry, user, password]);

  const start = useCallback(() => {
    setNotice(null);
    void run(withOptions(entry.blueprint, { debug, persist }));
  }, [entry, run, debug, persist]);

  const [failureTitle, failureHint] = failure ? FAILURE_COPY[failure.kind] : [];
  const needsSecrets = entry.secrets !== undefined;

  return (
    <View style={styles.screen}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Aetherius</Text>
        <Text style={styles.subtitle}>moteur embarque · Acts I et II sur l'appareil</Text>

        <View style={styles.group}>
          {BLUEPRINTS.map((item) => {
            const active = item.key === selected;
            return (
              <Pressable
                key={item.key}
                onPress={() => {
                  setSelected(item.key);
                  // Deux Blueprints declarent des secrets differents : garder « range dans le
                  // trousseau » affiche apres un changement de carte serait un mensonge.
                  setSaved(false);
                }}
                style={[styles.card, active && styles.cardActive]}
              >
                <View style={styles.cardHead}>
                  <Text style={[styles.cardTitle, active && styles.cardTitleActive]}>
                    {item.title}
                  </Text>
                  {/* Le badge est ce qui evite de se perdre apres quelques passes : il dit ce qui
                      a deja ete vu sur un telephone, pas ce que les tests couvrent. */}
                  <Text style={[styles.status, { color: STATUS[item.status].color }]}>
                    {STATUS[item.status].label}
                  </Text>
                </View>
                <Text style={styles.cardHint}>{item.hint}</Text>
                {item.note !== undefined && <Text style={styles.cardNote}>{item.note}</Text>}
              </Pressable>
            );
          })}
        </View>

        {needsSecrets && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Secrets</Text>
            <Text style={styles.cardHint}>
              {`${entry.secrets.join(", ")} — saisis une fois, ils restent dans le trousseau.`}
            </Text>
            {stored !== null && (
              <Text style={[styles.stored, { color: stored ? COLORS.laurel : COLORS.amber }]}>
                {stored
                  ? "Presents dans le trousseau."
                  : "Absents du trousseau : le run echouera sur « Donnee manquante »."}
              </Text>
            )}
            <TextInput
              value={user}
              onChangeText={setUser}
              placeholder="identifiant"
              placeholderTextColor={COLORS.stone}
              autoCapitalize="none"
              style={styles.input}
            />
            <TextInput
              value={password}
              onChangeText={setPassword}
              placeholder="mot de passe"
              placeholderTextColor={COLORS.stone}
              autoCapitalize="none"
              secureTextEntry
              style={styles.input}
            />
            <Pressable onPress={storeSecrets} style={styles.secondary}>
              <Text style={styles.secondaryLabel}>
                {saved ? "◉  Ranges dans le trousseau" : "Ranger dans le trousseau"}
              </Text>
            </Pressable>
          </View>
        )}

        {/* Les deux bascules qui n'ont de sens que sur un appareil : voir la WebView, et garder la
            session entre deux lancements. */}
        <Pressable onPress={() => setDebug((on) => !on)} style={styles.toggle}>
          <Text style={[styles.toggleLabel, debug && styles.toggleLabelOn]}>
            {`${debug ? "◉" : "○"}  Act II : montrer la WebView (options.debug)`}
          </Text>
        </Pressable>
        <Pressable onPress={() => setPersist((on) => !on)} style={styles.toggle}>
          <Text style={[styles.toggleLabel, persist && styles.toggleLabelOn]}>
            {`${persist ? "◉" : "○"}  Garder la session (options.session.persist)`}
          </Text>
        </Pressable>

        <Pressable
          onPress={start}
          disabled={running}
          style={[styles.button, running && styles.buttonDisabled]}
        >
          {running ? (
            <ActivityIndicator color={COLORS.void} />
          ) : (
            <Text style={styles.buttonLabel}>Lancer le run</Text>
          )}
        </Pressable>

        {notice !== null && <Text style={styles.notice}>{notice}</Text>}

        {events.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Progression</Text>
            {/* Le flux d'evenements *est* l'interface de progression : aucune machine a etats
                applicative n'est necessaire pour savoir ou en est un run. */}
            {events.map((event, index) => (
              <Text key={index} style={[styles.event, { color: LEVEL_COLOR[event.level] }]}>
                {`[${event.type}]${event.step_id ? ` ${event.step_id}` : ""}${
                  event.message ? ` ${event.message}` : ""
                }`}
              </Text>
            ))}
          </View>
        )}

        {result !== undefined && failure === undefined && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>
              Resultat<Text style={{ color: COLORS.laurel }}>{`  ${result.status}`}</Text>
            </Text>
            {/* Un `outputs` vide ici veut dire « la source n'avait rien a dire » — pas « ca a
                casse ». C'est toute la difference que le modele d'erreur preserve. */}
            <Text style={styles.code}>{JSON.stringify(result.outputs, null, 2)}</Text>
          </View>
        )}

        {failure !== undefined && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>{failureTitle}</Text>
            <Text style={styles.cardHint}>{failureHint}</Text>
            {failure.code !== undefined && <Text style={styles.badge}>{failure.code}</Text>}
            <Text style={styles.error}>{failure.message}</Text>
            {failure.retryable && <Text style={styles.cardHint}>Reessayer peut aboutir.</Text>}
          </View>
        )}
      </ScrollView>

      {/* Montes une fois : leur vie appartient a l'arbre, pas a un run. */}
      <AetheriusWebView onLoadError={setNotice} />
      <AetheriusConfirm />

      {/* Rendu APRES la WebView, donc au-dessus d'elle. En mode debug la vue occupe tout l'ecran :
          un bouton d'annulation place dans le contenu serait recouvert, et donc intestable — ce qui
          etait le cas. Le seul controle qui doit rester atteignable pendant un run, c'est celui-ci. */}
      {running && (
        <Pressable onPress={cancel} style={styles.floatingCancel}>
          <Text style={styles.floatingCancelLabel}>Annuler le run</Text>
        </Pressable>
      )}
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
  cardHead: { flexDirection: "row", alignItems: "flex-start", gap: 10 },
  cardTitle: { flex: 1, color: COLORS.moonlight, fontSize: 16, fontWeight: "600" },
  cardTitleActive: { color: COLORS.violet },
  status: { fontSize: 11, letterSpacing: 1.5, textTransform: "uppercase", fontWeight: "700" },
  cardHint: { color: COLORS.stone, fontSize: 12, marginTop: 4, lineHeight: 17 },
  cardNote: { color: COLORS.violet, fontSize: 11, marginTop: 6, lineHeight: 16, fontStyle: "italic" },
  stored: { fontSize: 12, lineHeight: 17 },
  button: {
    backgroundColor: COLORS.violet,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: "center",
  },
  buttonDisabled: { opacity: 0.6 },
  buttonLabel: { color: COLORS.void, fontSize: 16, fontWeight: "700", letterSpacing: 1 },
  floatingCancel: {
    position: "absolute",
    right: 20,
    bottom: 44,
    backgroundColor: COLORS.pompeian,
    borderRadius: 24,
    paddingVertical: 14,
    paddingHorizontal: 22,
    zIndex: 10,
    elevation: 10,
  },
  floatingCancelLabel: { color: COLORS.moonlight, fontSize: 15, fontWeight: "700" },
  toggle: { paddingVertical: 2 },
  toggleLabel: { color: COLORS.stone, fontSize: 13 },
  toggleLabelOn: { color: COLORS.gold },
  secondary: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: COLORS.violet,
    paddingVertical: 11,
    alignItems: "center",
    marginTop: 4,
  },
  secondaryLabel: { color: COLORS.violet, fontSize: 14, fontWeight: "600" },
  input: {
    backgroundColor: COLORS.void,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: COLORS.panel,
    color: COLORS.moonlight,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
  },
  notice: { color: COLORS.gold, fontSize: 12, lineHeight: 17 },
  section: {
    backgroundColor: COLORS.nimbus,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.panel,
    padding: 14,
    gap: 6,
  },
  sectionTitle: { color: COLORS.violet, fontSize: 13, letterSpacing: 2, textTransform: "uppercase" },
  badge: {
    alignSelf: "flex-start",
    backgroundColor: COLORS.panel,
    color: COLORS.amber,
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    fontFamily: "monospace",
    fontSize: 12,
  },
  event: { color: COLORS.moonlight, fontFamily: "monospace", fontSize: 11, lineHeight: 16 },
  code: { color: COLORS.moonlight, fontFamily: "monospace", fontSize: 12, lineHeight: 18 },
  error: { color: COLORS.pompeian, fontSize: 12, lineHeight: 18 },
});
