# Le moteur sur l'appareil

Ce répertoire porte deux choses : des **Blueprints** destinés au moteur embarqué, et une
**application de démonstration** qui les joue sur un vrai téléphone.

L'application n'est pas une vitrine, c'est un **banc de vérification**. Elle existe pour honorer le
point 5 de [CONTRIBUTING](../../CONTRIBUTING.md#définition-de--terminé-) — « le vrai run, pas
seulement les tests » — sur le seul environnement qui compte pour la Phase 3 : un appareil. Elle
doit rester minimale, et le rester aux jalons suivants.

## Le Blueprint témoin

[`device-ip-check.blueprint.json`](device-ip-check.blueprint.json) demande à un service public
quelle adresse IP a émis la requête. C'est la démonstration la plus courte de la raison d'être de la
phase :

```bash
aetherius run examples/mobile/device-ip-check.blueprint.json     # l'IP du poste de dev
```

Puis le **même fichier** depuis l'application, téléphone en données cellulaires : l'IP est
différente. La requête part de l'appareil, pas d'un serveur — c'est exactement ce qu'un daemon
hébergé ne peut pas offrir.

L'application embarque aussi [`jsonplaceholder-flow`](../vector/jsonplaceholder-flow.blueprint.json)
(extraction JSONPath, `if`, `for_each`) et [`quotes-watch`](../vector/quotes-watch.blueprint.json)
(extraction CSS hors navigateur). Ce sont les fichiers d'`examples/`, importés tels quels : ce sont
les mêmes que joue le moteur Python, sans copie.

## La sonde de session

[`session-cookie-probe.blueprint.json`](session-cookie-probe.blueprint.json) n'est **pas** une
démonstration : elle n'a pas le même résultat partout, et c'est son objet. Un service public pose un
cookie de session par une **redirection**, puis un second step demande qui il est.

| Où | `carried` | Pourquoi |
|----|:---:|----------|
| Sur l'appareil | `true` (observé) | le magasin de cookies de la plateforme porte la session, redirection comprise |
| Moteur Python | `true` | le jar de son client HTTP fait le même travail |
| Sous Node (script, CI) | `false` | `fetch` n'a aucun magasin, et la réponse intermédiaire d'une redirection n'est pas lisible |

Elle **rapporte** l'asymétrie au lieu d'échouer, ce qui la rend lisible d'un coup d'œil. C'est la
limite décrite dans [docs/embedded.md](../../docs/embedded.md#cookies-redirections-et-sessions),
rendue observable — et la seule manière de vérifier sur un vrai téléphone une promesse qui, sinon,
resterait une affirmation.

## Ce qu'on doit voir

Un run affiche sa progression puis son `Result`. Les valeurs attendues, à comparer avec
`aetherius run <le même fichier>` :

| Blueprint | Attendu |
|-----------|---------|
| `device-ip-check` | `status: 200` et une IP **différente** de celle du poste |
| `jsonplaceholder-flow` | `branch: "then"`, `user_count: 3`, et les événements `walk.each_user[0].announce`, `[1]`, `[2]` **dans cet ordre** |
| `quotes-watch` | la première citation de la page et `quotes_on_page: 10` |
| `session-cookie-probe` | `carried: true` (voir le tableau ci-dessus) |

L'ordre des événements du flux imbriqué est le plus instructif : c'est lui qui prouve que les
boucles restent séquentielles et que les chemins de step sont identiques d'un moteur à l'autre.

## Lancer l'application

Prérequis : Node 20+, et **Expo Go** installé sur le téléphone (App Store / Play Store). Aucun SDK
Android ni Xcode n'est nécessaire.

```bash
npm --prefix sdks install
npm --prefix sdks run build --workspace @aetherius/engine   # le moteur est consomme depuis dist/

cd examples/mobile/demo
npm install
npm run doctor                                              # verifie l'accord des versions
npm start                                                   # scanner le QR code avec Expo Go
```

### La version d'Expo Go décide, pas nous

Expo Go est une application **préconstruite** : elle n'exécute qu'une version du SDK Expo, celle
qu'affiche son écran *Settings* (« supported SDK »). Le projet est aligné sur le **SDK 54** ; si ton
Expo Go en annonce un autre, c'est lui qui a raison — réaligne le projet, ne force pas :

```bash
npm install expo@~<SDK>.0.0
npx expo install --fix        # realigne react, react-native, babel-preset-expo, expo-status-bar
npm run doctor                # doit dire "No issues detected"
```

Ne pas déclarer `sdkVersion` dans `app.json` : il est **dérivé** du paquet `expo` installé, et
l'écrire à la main est précisément la façon dont il finit par mentir. Le symptôme d'un désaccord est
reconnaissable — `[runtime not ready]: ReferenceError: Property 'MessageQueue' doesn't exist` — et il
veut dire que la version de `react-native` installée n'est pas celle qu'attend le runtime d'Expo Go.

### Si le téléphone ne trouve pas le serveur

Par défaut Expo sert le bundle sur le **réseau local** : le téléphone et l'ordinateur doivent être
sur le même Wi-Fi (le partage de connexion du téléphone marche aussi — mais alors l'IP de sortie est
celle du téléphone, ce qui fausse la lecture de `device-ip-check`). Sinon, passer par un tunnel :

```bash
npm run tunnel                # expo start --tunnel, installe @expo/ngrok au premier lancement
```

C'est le seul mode qui fonctionne quand l'ordinateur et le téléphone sont sur deux réseaux
différents — typiquement l'ordinateur en Wi-Fi et le téléphone en données cellulaires, qui est
justement la configuration à utiliser pour la sonde de `device-ip-check`.

L'écran liste les Blueprints, lance le run, affiche le flux d'événements en direct et le `Result`.
Le flux d'événements **est** l'interface de progression : c'est ce qu'une application réimplémente
aujourd'hui à la main avec des états ad hoc.

## Ce qui n'est pas là

- **Pas de façade `Aetherius`** : l'écran appelle `RunEngine` directement. La surface applicative
  (façade, secrets par le trousseau, `confirm` en modal) est le jalon
  [3-E](../../docs/phase-3/3-e-integration.md) ; l'écran raccourcira quand elle arrivera.
- **Pas d'Act II** : le driver WebView est le jalon [3-D](../../docs/phase-3/3-d-continuum.md).
  Un Blueprint `continuum` est accepté à la validation mais refusé au démarrage, avec le message qui
  nomme le paquet manquant.
- **Pas de livraison distante** : les Blueprints sont importés depuis le dépôt. Le cache, le
  contrôle d'intégrité et l'interrupteur d'arrêt sont le jalon
  [3-F](../../docs/phase-3/3-f-delivery.md).

L'application n'est pas construite en CI : elle demande un appareil. Ce qui est gardé
automatiquement, c'est le moteur (`make check-all`) et l'accord entre les deux moteurs
(`make conformance`).
