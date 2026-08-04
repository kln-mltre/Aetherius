/**
 * La livraison des Blueprints, cote application (jalon 3-F).
 *
 * L'application embarque un Blueprint **volontairement casse** — il demande une page que le site a
 * « renommee » — et le registre va chercher sa correction sur un manifeste distant. C'est le
 * parcours que le jalon existe pour rendre possible : reparer un site casse **sans republier sur
 * les stores**.
 *
 * Deux points de conception se lisent ici, et ils sont le sujet :
 *
 *   - le magasin de cache est **injecte** (`AsyncStorage`, dont la surface satisfait l'interface
 *     telle quelle) : la bibliotheque n'impose aucune dependance a l'application ;
 *   - l'URL du manifeste est **une donnee**, pas une constante. Sur un banc, elle change a chaque
 *     configuration reseau ; en production, c'est une constante de l'application.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { BlueprintRegistry } from "@aetherius/react-native";

import deliveryQuotes from "../delivery-quotes.blueprint.json";

/** Le Blueprint livrable : embarque en v1 (casse), corrige en v2 par le manifeste d'exemple. */
export const DELIVERED = "mobile.delivery.quotes";

/** Ou l'ecran retient la derniere URL saisie — retaper une URL sur un telephone est une punition. */
const URL_KEY = "demo/manifest-url";

/**
 * Une valeur de depart, a remplacer par l'adresse du poste sur le reseau du telephone :
 *
 *   python3 -m http.server 8000 --directory examples/mobile/registry
 *
 * Un manifeste servi en HTTPS statique (gist brut, Pages) marche aussi, et c'est le seul choix
 * quand le telephone est en donnees cellulaires derriere `expo start --tunnel`.
 */
export const DEFAULT_MANIFEST_URL = "http://127.0.0.1:8000/manifest.json";

export function useDelivery() {
  const [manifestUrl, setManifestUrl] = useState(DEFAULT_MANIFEST_URL);
  const [status, setStatus] = useState(null);
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);

  // Le registre depend de l'URL : en changer construit un registre neuf, sur le **meme** magasin —
  // donc la surcouche deja telechargee reste en place.
  const registry = useMemo(
    () =>
      new BlueprintRegistry({
        bundled: { [DELIVERED]: { version: "1", document: deliveryQuotes } },
        manifest: manifestUrl,
        cache: AsyncStorage,
      }),
    [manifestUrl],
  );

  const reload = useCallback(async () => {
    setStatus((await registry.list())[0] ?? null);
  }, [registry]);

  useEffect(() => {
    let alive = true;
    void (async () => {
      const saved = await AsyncStorage.getItem(URL_KEY);
      if (alive && saved) setManifestUrl(saved);
    })();
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      await AsyncStorage.setItem(URL_KEY, manifestUrl);
      setReport(await registry.refresh());
      await reload();
    } finally {
      setBusy(false);
    }
  }, [registry, reload, manifestUrl]);

  const revert = useCallback(async () => {
    await registry.revert();
    setReport(null);
    await reload();
  }, [registry, reload]);

  /** Ce que l'ecran joue : la version distante si elle a gagne, l'embarquee sinon. */
  const resolve = useCallback((name) => registry.resolve(name), [registry]);

  return { manifestUrl, setManifestUrl, status, report, busy, refresh, revert, resolve };
}
