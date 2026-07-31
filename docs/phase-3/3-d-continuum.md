# Jalon 3-D — Act II (Continuum) sur WebView

**Statut : à faire.** Le jalon le plus volumineux de la phase. C'est celui qui remplace les WebView
cachées écrites à la main : là où une application pilote aujourd'hui un portail avec des gabarits de
chaîne JavaScript, elle décrira un Blueprint.

## Objectif

Rendre `act: "continuum"` exécutable sur appareil : navigation, interaction, extraction DOM,
attentes, sessions — à travers une **WebView cachée** pilotée par un **agent JavaScript injecté**.

## Dépendances

Jalon 3-C (runtime et Act I).

## Interfaces et fichiers

Références côté Python — ce jalon reproduit leur surface, pas leur implémentation :

- [`acts/continuum/actions.py`](../../src/aetherius/acts/continuum/actions.py) — la table
  action → opération et la résolution de locators.
- [`acts/continuum/bridge.py`](../../src/aetherius/acts/continuum/bridge.py) — `extract`,
  `wait_for`, `evaluate`, le vocabulaire `as:` et la sémantique `fail:CODE`.
- [`acts/continuum/browser.py`](../../src/aetherius/acts/continuum/browser.py) — cycle de vie,
  sessions persistantes, suivi des nouvelles pages, mode debug.

Déjà en place (stub à implémenter) :

- [`sdks/react-native/src/webview/host.ts`](../../sdks/react-native/src/webview/host.ts) —
  `WebViewHost`, le joint entre le driver et la WebView réelle.

À créer sous [`sdks/react-native/src/`](../../sdks/react-native/src) :

- **`continuum/driver.ts`** — le driver, implémentant `ActDriver`.
- **`continuum/actions.ts`** — la table action → opération.
- **`webview/agent/`** — l'**agent injecté** : résolution de locators, auto-attente, exécution des
  actions, lecture du DOM, boucle d'observation pour `wait_for`. Découpé en modules et **assemblé au
  build** en une chaîne unique injectable.
- **`webview/rpc.ts`** — corrélation des appels, délais d'attente, découpage des messages.
- **`webview/component.tsx`** — le composant hôte qui monte la WebView cachée.

## Contrat

Aucune modification des contrats. Ce jalon **déclare en revanche la table des capacités non
portables** (décision 6 de la phase) : les actions de Continuum qui n'ont pas d'équivalent honnête en
WebView sont refusées **à la validation**, avec un message qui dit pourquoi et ce qu'on peut faire à
la place. Le premier candidat est l'envoi de fichier ; le code de statut HTTP de `navigate` en est un
autre, plus subtil, parce que l'action réussit tout en ne pouvant pas remplir une de ses sorties.

## Points de conception

- **Le contrat de l'agent injecté est le vrai livrable.** Ce n'est pas « du JavaScript qu'on injecte »
  mais un protocole : un vocabulaire d'opérations fermé, des paramètres **encodés en JSON**, des
  réponses corrélées par identifiant, des délais d'attente côté appelant. La règle absolue : **aucun
  paramètre n'est jamais interpolé dans la source du script**. C'est ce qui rend impossible par
  construction la classe de bug la plus courante des WebView écrites à la main — un mot de passe
  contenant une apostrophe qui casse le script, ou pire.
- **L'auto-attente est à réimplémenter, et c'est ce qui fait la différence.** Un pilote de navigateur
  mature attend qu'un élément existe, soit visible et soit stable avant d'agir. Une WebView n'offre
  rien de tel. Sans cette couche, chaque Blueprint devrait semer des attentes fixes — exactement la
  fragilité qu'on cherche à supprimer. Le motif à reprendre est celui, éprouvé, des WebView
  artisanales : *tenter la lecture immédiatement ; si elle échoue, observer les mutations du document
  jusqu'à l'échéance ; à l'échéance, rendre un échec explicite plutôt que rester bloqué*.
- **Le cycle de vie de navigation est le piège majeur.** Chaque navigation détruit le contexte de la
  page : l'agent doit être réinjecté, et toute opération en vol doit être résolue ou annulée
  proprement. Il faut un état explicite « page prête, agent présent » ; le déduire d'un événement de
  chargement seul produit des courses de conditions non reproductibles.
- **Les locators, dans l'ordre décroissant d'utilité.** Sélecteurs CSS d'abord, XPath ensuite,
  recherche par texte enfin. Le mode strict du moteur Python — plusieurs correspondances est une
  erreur, pas un choix implicite du premier — doit être reproduit : c'est lui qui transforme un
  Blueprint devenu ambigu en échec lisible plutôt qu'en clic sur le mauvais bouton.
- **Le vocabulaire `as:` est un contrat de données.** `text`, `number`, `html`, `attr`, `count`,
  `list`, plus le motif `each`/`fields` pour les enregistrements. Les détails comptent : le nombre
  est extrait par expression régulière avec la virgule décimale convertie en point, le texte est
  détouré, `count` ne prend pas la première correspondance. Un écart ici ne casse pas un run, il
  produit une **donnée fausse** — le pire des échecs.
- **Sessions et cookies.** `options.session.persist` décide si la WebView réutilise l'état du
  navigateur système ou repart vierge. Sur mobile, ce choix a une conséquence directe et visible pour
  l'utilisateur : une session persistante évite de se ré-authentifier à chaque lancement, une session
  isolée garantit un départ propre. Documenter les deux, et ce que chacune coûte.
- **Les fenêtres multiples : les interdire plutôt que les suivre.** Le moteur Python suit les
  nouveaux onglets. Dans une WebView cachée, ouvrir une fenêtre n'a pas de sens : la contraindre à
  rester dans la même vue est le comportement correct, et il doit être explicite.
- **Le mode debug rend la WebView visible.** C'est l'équivalent mobile de la fenêtre de navigateur
  visible du mode debug côté Python, et le seul moyen réaliste de comprendre pourquoi un step échoue
  sur un portail réel.
- **Les messages volumineux doivent être découpés.** Le pont entre la page et l'application n'est pas
  fait pour transporter un document entier. Une extraction large doit être segmentée par le protocole,
  pas laissée à la chance.

## Plan de test

- **Agent, hors appareil** : la table d'opérations est testée contre un DOM simulé — locators
  (les trois types, correspondance unique, multiple, absente), chaque valeur de `as:` y compris les
  cas limites du nombre, `each`/`fields` avec des champs manquants, `wait_for` qui réussit après une
  mutation et qui expire avec le code nommé.
- **RPC** : corrélation de deux appels concurrents, expiration d'un appel, message découpé et
  réassemblé, réponse arrivant après une navigation (doit être rejetée, pas attribuée au mauvais
  appel).
- **Sur appareil** : le parcours complet sur un site public — navigation, saisie, clic, attente,
  extraction — puis une **sonde réaliste dure** sur un portail authentifiant réel, conformément au
  point 5 de [CONTRIBUTING](../../CONTRIBUTING.md#définition-de--terminé-). Vérifier la persistance
  de session entre deux lancements, et le mode debug.
- **Capacités non portables** : chacune est refusée à la validation, avec son message.
- **Conformance** : les Blueprints `continuum` du corpus produisent les mêmes sorties et la même
  séquence d'événements que le moteur Python. Là où l'agent injecté peut être exercé contre un
  navigateur réel piloté depuis les tests Python existants, le faire : c'est la comparaison la plus
  directe entre les deux implémentations.

## Exemple exécutable à livrer

Un Blueprint `continuum` **zéro configuration** (site public, sans identifiants) exécutable depuis
l'application de démonstration et depuis `aetherius run`. Le parcours authentifié réel, lui, arrive
au jalon 3-G — il demande des identifiants et ne peut pas être zéro configuration.

## Définition de terminé

Les 6 points de [CONTRIBUTING](../../CONTRIBUTING.md#définition-de--terminé-), le point 5 joué sur
appareil avec sa sonde dure ; `make check-all` et `make conformance` verts ; `docs/embedded.md`
complétée du protocole de l'agent, de la table des capacités non portables et du modèle de session ;
`@aetherius/react-native` peut sortir de `private`.

## Critères d'acceptation

Un Blueprint `continuum` scriptant une authentification puis une extraction tourne sur appareil et
rend les mêmes données que le moteur Python sur le même site ; aucun paramètre n'est interpolé dans
la source d'un script injecté, et un test le prouve avec une valeur contenant guillemets et
apostrophes ; une capacité non portable est refusée avant le run ; le mode debug montre la WebView.
