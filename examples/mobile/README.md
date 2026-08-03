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

## Le Blueprint Act II

[`webview-quotes.blueprint.json`](webview-quotes.blueprint.json) est le témoin du jalon 3-D : une
**WebView cachée** ouvre une page, attend son DOM, en lit des données typées (texte, nombre à virgule
décimale, comptage, liste, enregistrements `each`/`fields`) puis recoupe le tout avec du JavaScript
injecté. Zéro configuration, et le **même fichier** des deux côtés :

```bash
aetherius run examples/mobile/webview-quotes.blueprint.json     # Playwright, sur le poste
```

Puis depuis l'application : mêmes sorties, mais la navigation et le scraping se font dans la WebView
du téléphone, sans daemon.

La WebView n'existe **qu'à partir du premier run `continuum`** : lancer un Blueprint `vector` ne
crée aucune vue, et l'écran d'accueil est identique à celui du jalon 3-C.

Passer `options.debug` à `true` dans le Blueprint **rend la WebView visible** sur le téléphone —
l'équivalent mobile de la fenêtre Chromium que le mode debug ouvre côté Python, et le seul moyen
réaliste de comprendre pourquoi un step échoue sur un portail réel.

## Le parcours applicatif complet

[`quotes-login-confirm.blueprint.json`](quotes-login-confirm.blueprint.json) est le témoin du jalon
3-E, et le seul Blueprint livré qui exerce les trois capacités du jalon d'un coup : des identifiants
venus du **trousseau de l'OS**, une **confirmation humaine** avant de les envoyer, et un **échec
nommé** (`fail:LOGIN_FAILED`) si le portail refuse.

```bash
aetherius run examples/mobile/quotes-login-confirm.blueprint.json \
  --secret quotes_user=demo --secret quotes_pass=demo
```

Le site de démonstration accepte n'importe quels identifiants, donc l'exemple tourne partout. Sur le
téléphone, l'écran demande les identifiants **une fois** et les range dans `expo-secure-store` ; les
runs suivants les relisent tout seuls, y compris après un redémarrage de l'application.

Ce qu'il montre, et qu'il faut regarder dans cet ordre :

| Geste | Ce qui doit se passer |
|-------|------------------------|
| Approuver au modal | le run repart, `decision: "approved"`, `connecte: 1` |
| Refuser | les quatre steps gardés passent en `skipped` et le run reste un **succès** — le refus par défaut compose, il ne casse pas |
| Ne rien faire | même issue que le refus : c'est le comportement qui arrive tout seul quand l'application est en arrière-plan |
| Passer en mode avion | « Service indisponible », **pas** un résultat vide — c'est toute la raison d'être du modèle d'erreur |
| Quitter l'écran en cours de run | le run est annulé et la WebView libérée (visible en `options.debug`) |

Une note d'ergonomie qui a coûté deux tentatives : le bouton **Annuler le run** est *flottant*, en bas
à droite, et rendu **après** la WebView. En mode debug la vue occupe tout l'écran, et un bouton placé
dans le contenu se retrouvait dessous — donc intestable. C'est le seul contrôle qui doit rester
atteignable pendant un run, et il faut le tester sur un Blueprint **sans `confirm`** (le modal, lui,
recouvre tout par nature) : `bordeaux-cas-login` avec la bascule WebView activée.

Le message du modal cite l'identifiant, alors que le flux d'événements affiche `[secret]` à sa
place. Ce n'est pas une incohérence : **l'humain doit voir ce qu'il approuve**, le journal non.

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
| `webview-quotes` | la citation d'Einstein, `citations_sur_la_page: 10`, quatre étiquettes, dix enregistrements et `auteurs_comptes_par_js: 10` |
| `session-cookie-probe` | `carried: true` (voir le tableau ci-dessus) |
| `quotes-login-confirm` | un modal, puis `decision: "approved"` et `connecte: 1` — ou `rejected` et `connecte: 0` |
| `bordeaux-cas-login` | `peut_se_deconnecter: 1` avec les bons identifiants ; `LOGIN_FAILED` avec de mauvais |
| `ukit-planning` | la liste d'événements de la semaine, identique à `aetherius run` — c'est l'encodage `form` (clé répétée `federationIds[]`) éprouvé sur l'appareil |
| `session-persist-probe` | `connecte: 1` si la session tient, `0` sinon — voir ci-dessous |

## La sonde de persistance

[`session-persist-probe.blueprint.json`](session-persist-probe.blueprint.json) est le pendant Act II
de la sonde de session : elle **rapporte** au lieu d'échouer. Elle ouvre la page et compte le lien de
déconnexion, sans jamais se connecter — donc `1` veut dire « la session d'un run précédent est encore
là », `0` veut dire « départ propre ».

Elle ne déclare **pas** `options.session.persist` : c'est la bascule de l'application qui décide, ce
qui permet de comparer les deux régimes sans éditer un fichier. Le parcours qui rend la persistance
visible tient en un A/B, **sans redémarrer quoi que ce soit** :

1. bascule « garder la session » **activée**, jouer `quotes-login-confirm` et approuver ;
2. jouer `session-persist-probe` → **`connecte: 1`** : la session a franchi la frontière du run ;
3. bascule **désactivée**, rejouer `quotes-login-confirm` puis la sonde → **`connecte: 0`** : la vue
   incognito repart propre.

C'est cette différence-là que `options.session.persist` achète, et c'est le point que le jalon 3-D
laissait à observer sur un appareil.

> **Et après avoir tué l'application ?** `connecte: 0`, et **c'est correct**. `quotes.toscrape.com`
> pose `session=…; HttpOnly; Path=/` — **sans `Expires` ni `Max-Age`**, donc un *cookie de session*,
> qui meurt avec le processus par définition HTTP. `persist: true` fait vivre la session **entre les
> runs**, pas au-delà du processus ; seul un cookie daté survivrait à un redémarrage, et aucun moteur
> ne peut inventer une date que le serveur n'a pas envoyée. Une version antérieure de cette
> procédure demandait le contraire : elle était fausse.

L'ordre des événements du flux imbriqué est le plus instructif : c'est lui qui prouve que les
boucles restent séquentielles et que les chemins de step sont identiques d'un moteur à l'autre.

## Lancer l'application

Prérequis : Node 20+, et **Expo Go** installé sur le téléphone (App Store / Play Store). Aucun SDK
Android ni Xcode n'est nécessaire.

```bash
npm --prefix sdks install
npm --prefix sdks run build --workspaces                    # les paquets sont consommes depuis dist/

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

### `Invalid hook call` / `Cannot read property 'useRef' of null`

Le symptôme d'une **seconde copie de React** dans le bundle, et il pointe vers le composant plutôt
que vers sa cause. Un paquet du workspace lié en `file:` résout ses *peer dependencies* depuis
`sdks/node_modules`, où npm les installe quel que soit `peerDependenciesMeta.optional` : deux copies
de React, donc deux dispatchers de hooks, dont le second est `null`.

[`metro.config.js`](demo/metro.config.js) le règle en **rerootant** la résolution de `react`,
`react-native`, `react-native-webview` et `scheduler` sur l'application. Vérifier qu'une seule copie
est bundlée :

```bash
npx expo export --platform ios --source-maps --output-dir /tmp/aeth-map
python3 -c "import json,glob;s=json.load(open(glob.glob('/tmp/aeth-map/**/*.map',recursive=True)[0]))['sources'];print(sorted({x for x in s if '/node_modules/react/' in x}))"
```

Aucun chemin ne doit passer par `sdks/`.

### Expo Go se ferme d'un coup, sans message

Un crash **natif** : ni écran rouge, ni erreur JavaScript. Deux causes rencontrées, dans cet ordre :

- **une WebView montée sur `about:blank`** dont on change ensuite la source. C'est ce qui tuait
  l'application au premier run `continuum` ; la vue est désormais créée directement avec l'URL
  qu'elle doit charger ;
- **une WebView cachée par son `style` plutôt que par son `containerStyle`** : la vue interne se
  retrouve rognée à néant dans le conteneur `overflow: hidden` de la bibliothèque, et une WKWebView
  sans aire de rendu finit par voir son processus de contenu tué.

La façon de trancher, quand ça recommence : monter une **WebView nue** (`<WebView source={{ uri }} />`,
aucun code Aetherius) derrière un bouton. Si elle crashe aussi, le problème est la bibliothèque ou
Expo Go ; si elle s'affiche, il est dans le composant, et l'espace de recherche devient minuscule.
C'est cette bissection qui a désigné `about:blank`, après deux correctifs plausibles qui n'étaient
pas la cause.

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

## L'écran, depuis le jalon 3-E

L'écran passe par la **façade** : `new Aetherius({ secrets: keychainSecrets(SecureStore) })`, puis
`useAetheriusRun`. Il a **raccourci** en gagnant des capacités, et c'est le propos du jalon — la
progression, les secrets, la confirmation et la traduction des erreurs ne sont plus du code
applicatif.

Chaque carte porte un **badge** : `vérifié` (observé sur un téléphone), `partiel` (le chemin nominal
est vu, des variantes restent), `à faire`, ou `bloqué` (par un tiers indisponible). C'est ce qui évite
de se perdre après quelques passes — et il dit ce qui a été *vu sur l'appareil*, pas ce que la suite
de tests couvre. `partiel` existe parce que plusieurs vérifications montent souvent sur le même
Blueprint : la note de la carte dit alors ce qu'il reste.

```
┌─ Blueprints ────────────────┐   la liste, un par carte + son badge
├─ Secrets ───────────────────┤   visible seulement pour les Blueprints qui en declarent, et il
│  identifiant / mot de passe │   LIT le trousseau : « presents » ou « absents » avant de lancer.
│                             │   « Ranger dans le trousseau » y ecrit sous les noms declares
├─ ○ montrer la WebView ──────┤   options.debug
├─ ○ garder la session ───────┤   options.session.persist
├─ [ Lancer le run ] [Annuler]┤   Annuler n'apparait que pendant un run
├─ Progression ───────────────┤   une ligne par evenement : [step_started] fill, [input_requested] …
├─ Resultat  success ─────────┤   les `outputs` bruts — une liste vide y est une vraie liste vide
└─ ou : La page a change ─────┘   le titre vient de `describeFailure(...).kind`, pas d'un message
```

Les deux bascules **écrasent les `options` du Blueprint au lancement** : elles évitent d'éditer un
fichier pour vérifier deux comportements qui n'existent que sur un appareil. Elles ne changent rien
au fichier livré.

Trois composants sont montés une fois, en bas de l'arbre, parce que leur vie appartient à l'arbre et
pas à un run : `<AetheriusWebView />` (l'Act II) et `<AetheriusConfirm />` (le modal). Le modal
n'apparaît que lorsqu'un run se gare.

Le bloc d'échec est le plus instructif à lire dans le code : il n'affiche **jamais** le message brut
comme titre. Le titre vient du `kind` rendu par `describeFailure`, le code nommé (`LOGIN_FAILED`)
devient une pastille, et le message ne sert qu'au détail. C'est le motif recommandé, montré plutôt
que décrit.

## Ce qui n'est pas là

- **Pas de livraison distante** : les Blueprints sont importés depuis le dépôt. Le cache, le
  contrôle d'intégrité et l'interrupteur d'arrêt sont le jalon
  [3-F](../../docs/phase-3/3-f-delivery.md).
- **Pas de biométrie sur le modal** : `<AetheriusConfirm />` est l'habillage par défaut. Une
  application qui veut Face ID passe par `useApprovalRequest`, la primitive sur laquelle il est
  bâti.

L'application n'est pas construite en CI : elle demande un appareil. Ce qui est gardé
automatiquement, c'est le moteur (`make check-all`) et l'accord entre les deux moteurs
(`make conformance`).
