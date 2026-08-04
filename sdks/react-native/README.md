# @aetherius/react-native

Le moteur Aetherius **dans une application mobile** : l'Act II sur l'appareil, et la surface que
consomme l'application.

Ce paquet apporte ce que [`@aetherius/engine`](../engine) ne peut pas porter sans dependre d'une
plateforme : le driver Continuum adosse a une **WebView cachee** pilotee par un agent JavaScript
injecte, les secrets par le **trousseau de l'OS**, `confirm` en **modal natif**, la facade
`Aetherius`, et la **livraison des Blueprints** — un socle embarque, une surcouche distante verifiee,
un cache et un interrupteur d'arret.

C'est la reponse a un cas concret : une application mobile qui se connecte au portail d'une
universite et en extrait des donnees. Aujourd'hui cela s'ecrit en JavaScript injecte sous forme de
gabarits de chaine — non type, non verifiable, et fragile des que le site bouge. Avec Aetherius, le
comportement redevient un **Blueprint**, les requetes partent du telephone de l'utilisateur, et les
identifiants ne quittent jamais l'appareil.

## Prise en main

```tsx
import * as SecureStore from "expo-secure-store";
import {
  Aetherius, AetheriusConfirm, AetheriusWebView, describeFailure, keychainSecrets,
} from "@aetherius/react-native";

// Le magasin de secrets est *injecte* : expo-secure-store, react-native-keychain, ou le tien.
const client = new Aetherius({ secrets: keychainSecrets(SecureStore) });

// Une fois, haut dans l'arbre. La WebView n'est creee qu'au premier run `continuum` et liberee a la
// fin : une application qui ne joue que de l'Act I n'en porte aucune.
export function App() {
  return (
    <>
      <MesEcrans />
      <AetheriusWebView />
      <AetheriusConfirm />
    </>
  );
}

const result = await client.run(blueprint, { inputs, onEvent: setProgression });
const failure = describeFailure(result); // undefined quand le run a reussi
```

Les noms sont ceux du SDK daemon [`@aetherius/client`](../client) : le choix d'embarquer un moteur ou
d'en piloter un a distance ne doit pas se voir dans le code appelant.

Un Blueprint n'a pas a etre fige dans le binaire. Le **registre** resout entre le socle embarque et
une surcouche distante verifiee — donc un site qui change se repare sans republier sur les stores :

```ts
import AsyncStorage from "@react-native-async-storage/async-storage";
import { BlueprintRegistry } from "@aetherius/react-native";

const registry = new BlueprintRegistry({
  bundled: { "ukit.planning.week": { version: "1", document: planning } },
  manifest: "https://cdn.exemple.fr/aetherius/manifest.json",
  cache: AsyncStorage,          // magasin injecte, comme le trousseau
});

const { blueprint, origin } = await registry.resolve("ukit.planning.week");  // aucun reseau
void registry.refresh();                                                    // hors du chemin critique
```

Le distant ne gagne que s'il est **plus recent, entier et valide** : empreinte SHA-256 verifiee a
chaque lecture, secrets bornes par l'application, `min_engine` respecte, et un interrupteur d'arret
des deux cotes. Format du manifeste et modele de menace :
[docs/embedded.md](../../docs/embedded.md#la-livraison-des-blueprints).

`react`, `react-native` et `react-native-webview` sont des **peer dependencies** : le paquet declare
structurellement la surface qu'il utilise plutot que d'emprunter leurs types, ce qui le garde
compilable et testable sans elles.

## Ce qu'il y a dedans

| Module | Role |
|--------|------|
| `aetherius.ts` | La facade : validation, resolution des secrets declares, masquage, passerelle d'approbation, annulation. |
| `secrets/` | `SecretResolver`, l'adaptateur trousseau (magasin injecte), et le rideau qui masque les valeurs dans les evenements et les messages d'echec. |
| `confirm/` | Le rendez-vous d'approbation observable, le hook `useApprovalRequest` (la primitive) et `<AetheriusConfirm />` (l'habillage par defaut). |
| `hooks/use-run.ts` | `useAetheriusRun` : le flux d'evenements branche sur un ecran, annulation au demontage comprise. |
| `webview/protocol.ts` | Le contrat de fil entre le driver et l'agent : vocabulaire ferme, parametres **encodes en JSON**, reponses correlees, jeton de generation. |
| `webview/rpc.ts` | Correlation des appels, echeances, reassemblage des messages decoupes, invalidation a la navigation. |
| `webview/bridged-host.ts` | Le cycle de vie de navigation, ecrit une fois : « pret » veut dire *l'agent s'est annonce sur la generation courante*. |
| `webview/lease.ts` | Une vue, donc un run Act II a la fois : le second est refuse, pas mis en file. |
| `webview/agent/` | L'agent injecte — locators, auto-attente, operations, lecture DOM. Assemble au build en une chaine unique. |
| `webview/component.tsx` | `<AetheriusWebView />` : la WebView cachee, ses sessions et son mode debug. |
| `continuum/` | Le driver et sa table action → operation. |
| `delivery/` | Le registre : manifeste (parseur strict), integrite (SHA-256 ecrit a la main), cache (magasin injecte), perimetre des secrets et interrupteur d'arret. |

Le modele d'erreur (`describeFailure` et la hierarchie typee) est **re-exporte** depuis le moteur :
une application n'a qu'une porte d'entree, et n'a pas a savoir ou vivent les classes.

## Tester

```bash
npm test        # build (dont l'assemblage de l'agent) + suite complete
npm run conformance   # le corpus partage, Act II compris
```

Les tests pilotent la **production** : la vraie facade, le vrai `BridgedHost`, la vraie RPC et le
vrai agent, contre un DOM jsdom au lieu d'une WebView. L'agent est en outre joue dans un **vrai
Chromium** depuis les tests Python (`tests/integration/test_webview_agent.py`), et compare a
Playwright sur la meme page.

Reference d'usage, protocole, limites declarees et sondes jouees :
[`docs/embedded.md`](../../docs/embedded.md#la-surface-applicative). Le cadrage de la phase et ses
sept jalons : [`docs/phase-3/`](../../docs/phase-3/README.md).

> **Etat.** L'Act II s'execute (jalon 3-D) et la surface applicative est livree (jalon 3-E). La
> livraison distante des Blueprints — cache, integrite, interrupteur d'arret — est le jalon
> [3-F](../../docs/phase-3/3-f-delivery.md).
