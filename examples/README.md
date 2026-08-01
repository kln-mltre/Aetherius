# Blueprints d'exemple

Des Blueprints exécutables, rangés par Act. La Console les découvre récursivement
(`aetherius` → Library) et la CLI les exécute (`aetherius run <chemin>`). Les exemples visant un
site public ciblent des bacs à sable de scraping prévus pour ça (`toscrape.com`) : ils tournent
tels quels, sans identifiant réel.

```
examples/
  vector/       Act I  — HTTP/API (le plus rapide, pas de navigateur)
  continuum/    Act II — navigateur scripté (Playwright)
  oracle/       Act III — vision + discrétion (ciblage {vision} + read)
  phantom/      Act IV — agent autonome orienté objectif (goal/constraints)
  composition/  Multi-Act : act par step + self-healing (Jalon 2-D)
  plugins/      Extension par paquet tiers : action + canal custom (Jalon 1.5-E)
  mobile/       Moteur embarqué : Blueprint témoin + application de démonstration (Jalon 3-C)
```

## Act I — Vector

| Fichier | Ce qu'il montre |
|---------|-----------------|
| [`vector/ukit-planning-week.blueprint.json`](vector/ukit-planning-week.blueprint.json) | `http.request` POST form + extraction JSONPath avec filtre `where`. Requiert l'API réelle (ou un mock). |
| [`vector/ukit-inf601a5-test.blueprint.json`](vector/ukit-inf601a5-test.blueprint.json) | Variante de test du même flux. |
| [`vector/jsonplaceholder-users-recorded.blueprint.json`](vector/jsonplaceholder-users-recorded.blueprint.json) | **Sortie réelle du Vector recorder** (`--act vector`) : `http.request` GET + extraction de records JSONPath (`$[*]` + `fields`). Zéro config. Voir [docs/recorder.md](../docs/recorder.md). |
| [`vector/jsonplaceholder-posts-studio.blueprint.json`](vector/jsonplaceholder-posts-studio.blueprint.json) | **Sortie réelle du Blueprint Studio** (template `vector.api-fetch`) : GET public + extraction de champs. Zéro config. Voir [docs/builder.md](../docs/builder.md). |
| [`vector/jsonplaceholder-flow.blueprint.json`](vector/jsonplaceholder-flow.blueprint.json) | Flux conditionnel (Jalon 1.5-B) : `if` choisit la branche, `for_each` parcourt les utilisateurs extraits et émet un événement par élément. Zéro config. |
| [`vector/jsonplaceholder-todo-alert.blueprint.json`](vector/jsonplaceholder-todo-alert.blueprint.json) | Garde `when` (Jalon 1.5-B) : lit un todo public et n'émet que la branche correspondant à son état (`--input todo_id=4` pour l'autre branche). Zéro config. |
| [`vector/books-restock-notify.blueprint.json`](vector/books-restock-notify.blueprint.json) | Le cas fil rouge (Jalon 1.5-C) : vérifie la disponibilité d'un produit (books.toscrape.com) et alerte via `when` + `notify` quand il est en stock. Zéro config (webhook d'écho httpbin.org) ; cible réelle via `.env`. Voir [docs/notifications.md](../docs/notifications.md). |
| [`vector/quotes-watch.blueprint.json`](vector/quotes-watch.blueprint.json) | La cible de démonstration du scheduler (Jalon 1.5-D) : scrape la première citation de quotes.toscrape.com ; planifié via `aetherius schedule add`, il alerte au changement avec la politique `change`. Zéro config. Voir [docs/scheduler.md](../docs/scheduler.md). |
| [`vector/daemon-selftest.blueprint.json`](vector/daemon-selftest.blueprint.json) | Self-test **zéro réseau** (`set`/`emit` uniquement) : prouve qu'un daemon exécute un Blueprint de bout en bout et streame ses événements. Voir [docs/daemon.md](../docs/daemon.md). |

## Act II — Continuum

Requiert l'extra navigateur : `pip install -e ".[browser]" && playwright install chromium`. Ces
Blueprints ont `options.debug: true` pour ouvrir une **fenêtre visible** — pratique pour regarder
le run depuis la Console.

| Fichier | Ce qu'il montre | Prérequis |
|---------|-----------------|-----------|
| [`continuum/quotes-scrape.blueprint.json`](continuum/quotes-scrape.blueprint.json) | `navigate` + `extract` (text/count). Le plus simple. | Aucun |
| [`continuum/quotes-login.blueprint.json`](continuum/quotes-login.blueprint.json) | `fill`/`click`, `wait_for` avec échec nommé (`on_timeout: "fail:LOGIN_FAILED"`), session persistante. | Secrets `quotes_user`/`quotes_pass` : **n'importe quelle valeur** convient (site de démo). |
| [`continuum/quotes-recorded-login.blueprint.json`](continuum/quotes-recorded-login.blueprint.json) | **Sortie réelle du recorder** (`aetherius record`) pour le login de démo : `navigate`/`fill`/`fill`/`click`, credentials en secrets. Voir [docs/recorder.md](../docs/recorder.md). | Secrets `username`/`password` : n'importe quelle valeur. |
| [`continuum/quotes-recorded-scrape.blueprint.json`](continuum/quotes-recorded-scrape.blueprint.json) | **Sortie réelle du recorder** (menu flottant) : `wait_for` + extraction de records `{text, author}` (`each`/`fields`) + liste de tags (`as: list`), avec bloc `outputs`. | Aucun |
| [`continuum/quotes-js-render.blueprint.json`](continuum/quotes-js-render.blueprint.json) | Page rendue en JavaScript (hors de portée de l'Act I) : attente du rendu, extraction DOM + `evaluate` (JS injecté). | Aucun |
| [`continuum/quotes-stealth.blueprint.json`](continuum/quotes-stealth.blueprint.json) | **Discrétion activée** (`options.stealth`) : fingerprint `chrome-desktop`, souris à gestes rejoués, frappe humaine, scroll adouci — en debug on voit le curseur glisser, dériver pendant l'attente, puis cliquer par un vrai geste. Voir [docs/stealth.md](../docs/stealth.md). | Aucun |
| [`continuum/books-catalog.blueprint.json`](continuum/books-catalog.blueprint.json) | Extraction `attr`/`text`/`count` + `screenshot` (artefact écrit dans `~/.aetherius/runs/<run_id>/`). | Aucun |
| [`continuum/bordeaux-cas-login.blueprint.json`](continuum/bordeaux-cas-login.blueprint.json) | Login CAS **réel** (Université de Bordeaux) + confirmation de l'état authentifié. Login à froid (fiable à chaque run). | Secrets `bordeaux_user`/`bordeaux_pass` dans `.env` |
| [`continuum/ukit-scolarite-login.blueprint.json`](continuum/ukit-scolarite-login.blueprint.json) | Cas fondateur : login CAS + scraping de la scolarité. Gabarit à adapter à un vrai ENT (les URLs `exemple.fr` sont des placeholders). | Secrets + vraies URLs/sélecteurs |

### Secrets

Un Blueprint ne stocke **jamais** de valeur de secret, seulement son nom. À l'exécution, chaque
secret `<nom>` est résolu depuis la variable d'environnement `AETHERIUS_SECRET_<NOM>` (en
majuscules), avec un fichier **`.env`** local (git-ignoré, jamais commité) chargé automatiquement.
Copier [`.env.example`](../.env.example) vers `.env` à la racine, y mettre ses identifiants, et
lancer depuis la racine du dépôt. Dans la Console, un secret présent dans `.env` s'affiche « loaded
from .env » et peut être laissé vide. Une valeur passée explicitement (`--secret k=v` ou le
formulaire) l'emporte toujours sur l'environnement.

## Act III — Oracle

Requiert les extras `[cognition]`+`[browser]` et la clé moteur `ANTHROPIC_API_KEY` (env ou `.env`,
jamais un secret de Blueprint). Voir [docs/acts/oracle.md](../docs/acts/oracle.md).

| Fichier | Ce qu'il montre |
|---------|-----------------|
| [`oracle/quotes-vision-demo.blueprint.json`](oracle/quotes-vision-demo.blueprint.json) | Ciblage `{vision}` (`click`/`wait_for`) + action `read` avec `schema`. Zéro config sur quotes.toscrape.com. |
| [`oracle/books-scan-below-fold.blueprint.json`](oracle/books-scan-below-fold.blueprint.json) | Recherche par défilement : une cible vision hors du viewport est trouvée en scrollant. Zéro config sur books.toscrape.com. |
| [`oracle/tiktok-upload.blueprint.json`](oracle/tiktok-upload.blueprint.json) | Gabarit de référence (service privé) : `upload`/`type` ciblés par vision + discrétion. Non exécutable tel quel. |

## Act IV — Phantom

Agent autonome orienté **objectif** : le Blueprint déclare un `goal` et des `constraints` (pas de
`steps`), et l'agent boucle percevoir → raisonner → agir. Mêmes extras et clé moteur qu'Oracle.
Voir [docs/acts/phantom.md](../docs/acts/phantom.md).

| Fichier | Ce qu'il montre |
|---------|-----------------|
| [`phantom/quotes-find-author.blueprint.json`](phantom/quotes-find-author.blueprint.json) | Objectif « trouve la première citation de l'auteur X » sur quotes.toscrape.com, borné par `options.agent.max_steps`. Sans `outputs` déclarés : le résultat de l'agent est renvoyé tel quel. Zéro config (`--input author=...` pour changer d'auteur). |

## Composition multi-Act (Jalon 2-D)

Un même run mélange les Acts (`act` par step) et se répare seul (`describe` +
`options.fallback`) — les Acts navigateur partagent un seul navigateur. Mêmes extras et clé
moteur qu'Oracle. Voir [docs/composition.md](../docs/composition.md).

| Fichier | Ce qu'il montre |
|---------|-----------------|
| [`composition/quotes-mixed-read.blueprint.json`](composition/quotes-mixed-read.blueprint.json) | Run Continuum (navigate + extract DOM) dont le dernier step passe `act: oracle` pour un `read` sémantique. Zéro config sur quotes.toscrape.com. |
| [`composition/quotes-selfheal-click.blueprint.json`](composition/quotes-selfheal-click.blueprint.json) | Self-healing : un `click` au sélecteur volontairement cassé est rejoué par ciblage vision (`describe` + `fallback: ["oracle"]`), puis le run repart sur Continuum. Zéro config. |

## Plugins

Le plugin de démonstration du Jalon 1.5-E : un paquet tiers minimal
([`plugins/aetherius-plugin-demo/`](plugins/aetherius-plugin-demo/)) qui ajoute l'action
`demo.slugify` et le canal de notification `logfile` par entry-points, sans toucher au cœur.
Contrat d'extension complet : [docs/plugins.md](../docs/plugins.md).

| Fichier | Ce qu'il montre | Prérequis |
|---------|-----------------|-----------|
| [`plugins/demo-notify.blueprint.json`](plugins/demo-notify.blueprint.json) | Une action plugin (`demo.slugify`) enchaînée à `notify` sur un canal plugin (`logfile`, alerte ajoutée à `./aetherius-demo-notifications.log`). Zéro réseau. | `pip install -e examples/plugins/aetherius-plugin-demo` |

Sans le plugin installé, la validation rejette l'action inconnue — c'est le comportement attendu.
Après l'essai, le désinstaller (`pip uninstall aetherius-plugin-demo`) avant de relancer
`make check` : les tests d'intégration démarrent le vrai moteur, qui le découvrirait.

## Moteur embarqué (Jalon 3-C)

Les mêmes Blueprints, joués par le **second moteur** directement sur un téléphone. Prise en main,
prérequis et lancement : [`mobile/README.md`](mobile/README.md).

| Fichier | Ce qu'il montre | Prérequis |
|---------|-----------------|-----------|
| [`mobile/device-ip-check.blueprint.json`](mobile/device-ip-check.blueprint.json) | Le Blueprint témoin : quelle IP a émis la requête. Jouée depuis `aetherius run` puis depuis l'appareil, elle diffère — la preuve que la requête part bien du téléphone. Zéro config. | Aucun |
| [`mobile/session-cookie-probe.blueprint.json`](mobile/session-cookie-probe.blueprint.json) | **Sonde, pas démonstration** : un cookie de session posé par une redirection. `carried: true` sur l'appareil et sous le moteur Python, `false` sous Node — l'asymétrie est le résultat, et elle est rapportée plutôt que subie. Zéro config. | Aucun |
| [`mobile/demo/`](mobile/demo/) | L'application de démonstration (Expo) : liste de Blueprints, run sur l'appareil, flux d'événements en direct, `Result`. Banc de vérification, pas vitrine. | Node 20+, Expo Go |

## Lancer un exemple

Depuis la Console (recommandé pour voir le flux en direct) :

```bash
aetherius                 # Library -> choisir un Blueprint -> Run
```

Depuis la CLI :

```bash
aetherius run examples/continuum/quotes-scrape.blueprint.json
aetherius run examples/continuum/quotes-login.blueprint.json \
  --secret quotes_user=demo --secret quotes_pass=demo
aetherius run examples/continuum/quotes-recorded-login.blueprint.json \
  --secret username=demo --secret password=demo
```

## Convention de nommage

Un Blueprint d'exemple se nomme `<sujet>.blueprint.json` et déclare un `name` en notation pointée
(`domaine.tache`). Tout fichier `*.blueprint.json` sous `examples/` (à n'importe quelle profondeur)
est découvert par la Console et validé contre le schéma par la CI.
