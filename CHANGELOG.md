# Changelog

Toutes les évolutions notables du projet sont consignées ici. Le format s'inspire de
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le versionnage suit
[SemVer](https://semver.org/lang/fr/). Tant que la version reste en `0.x`, l'API publique peut encore
évoluer entre deux versions mineures (durcissement de la Phase 1 en conditions réelles).

## [Non publié]

Durcissement du socle Phase 1 avant d'entamer la Phase 2 (audit croisé de la documentation), et
cadrage de la **Phase 1.5** (socle opérationnel : planification, alertes, réactivité).

### Ajouté
- **Actions custom / plugins (Jalon 1.5-E)** — points d'extension activés : un paquet tiers ajoute
  des actions de Blueprint et des canaux de notification sans forker le cœur. Découverte par
  entry-points (`aetherius.actions`, `aetherius.notify_channels`) dans le nouveau module
  `aetherius.plugins` (`load_plugins()` idempotent, appelé au démarrage par la CLI, le lifespan du
  daemon et `RunEngine.run` ; surface d'import unique pour les auteurs de plugins). Le registre
  d'actions dormant est activé : une action plugin embarque son `ActionSpec` (visible du Studio et
  des validators, invariant « registre = source, catalogue = projection » préservé), est
  **act-agnostique** (hors capability-table, validée dynamiquement) et dispatchée par les drivers
  en repli après leur `match` built-in. Gardes de collision sur les deux registres (les built-ins
  restent prioritaires, un conflit est un échec de chargement explicite) et pannes isolées (un
  plugin qui lève à l'import est loggé et sauté, jamais fatal). Plugin d'exemple exécutable
  (`examples/plugins/` : action `demo.slugify` + canal `logfile` + Blueprint zéro réseau), chargé
  par de vrais entry-points dans les tests. Voir [docs/plugins.md](docs/plugins.md).
- **Écran Console « Schedules »** — l'UI du scheduler (Jalon 1.5-D) dans la Console : liste des
  schedules (trigger, politique d'alerte, statut, prochains/derniers tirs en heure locale, sonde
  d'honnêteté « daemon actif ou non »), pause/reprise (`p`, la reprise recale la cadence),
  suppression confirmée (`d`, nouveau `ConfirmModal` réutilisable), **détail** avec l'historique
  des runs du schedule et un **tir manuel** aux événements streamés en direct (même brique
  in-process que `aetherius schedule run`, extraite dans `server/scheduler/manual.py::fire_schedule`
  et partagée CLI/Console), et **formulaire guidé** de création/édition (inputs du Blueprint en
  champs, secrets jamais saisis — état `.env` affiché, trigger/misfire/notify validés à la
  sauvegarde). Raccourci `s` dans Library pour planifier le Blueprint surligné. Captures SVG
  déterministes (fuseau épinglé, store de démo figé) et neutralisation renforcée des chemins
  (le home ne fuit plus, même tronqué dans une colonne). Voir [docs/console.md](docs/console.md).
- **Scheduler intégré au daemon (Jalon 1.5-D)** — rejeu persistant d'un Blueprint à heure fixe
  (cron à 5 champs, évalué dans le fuseau local, DST gérés via `tzlocal`), par intervalle ou en tir
  unique (`at`). Boucle de tick dans le lifespan du daemon (30 s, `AETHERIUS_DAEMON_SCHEDULER_TICK_SECONDS`) ;
  un run planifié passe par `RunManager.submit` — mêmes événements, même historique, plus le lien
  `schedule_id`. Rattrapage des tirs manqués par politique `misfire` (`skip`/`run_once`/`run_all`,
  portée par le trigger, résolue par le tick au-delà d'une fenêtre de grâce) et politique d'alerte
  par schedule (`failure`/`success`/`always`/`change` — la dédup au changement d'état s'appuie sur
  `state.compare_and_set`, cibles `{{ secrets.x }}` rendues au tir, jamais persistées). CLI
  `aetherius schedule add|list|rm|pause|resume|run` (écrit directement dans le store : marche daemon
  éteint ; `cli.py` devient le package `cli/`) et API `/v1/schedules` (CRUD + tir immédiat,
  contrat OpenAPI à jour). Exemple zéro config : `examples/vector/quotes-watch.blueprint.json`.
  Dépendances : `croniter` (déjà déclarée) + `tzlocal`. Voir [docs/scheduler.md](docs/scheduler.md).
- **Notifications natives (Jalon 1.5-C)** — couche d'alerte sans dépendance nouvelle (`notify/`) :
  quatre canaux built-in en un POST `httpx` chacun (webhook générique, Discord, Telegram, ntfy pour
  la push téléphone, en mode JSON publishing), action `notify` Act-agnostique (handler partagé, se
  combine à `when`), `NotifySink` de fin de run (`failure`/`success`/`always`) et registre de canaux
  prêt pour les plugins (Jalon E). Échec d'envoi contenu : jamais fatal au run, `delivered` exposé
  dans les outputs du step. Exemple zéro config :
  `examples/vector/books-restock-notify.blueprint.json`. Voir
  [docs/notifications.md](docs/notifications.md).
- **Réactivité et flux conditionnel (Jalon 1.5-B)** — garde d'étape `when` universelle (évaluée
  avant dispatch, même règle de véracité que `assert` ; step sauté = statut `skipped` + événement
  `step_skipped`, contrats et SDK TypeScript à jour) et actions `if`/`repeat`/`for_each` exécutées
  par un **exécuteur récursif** dans le moteur (`core/runtime/steps.py`), en amont des drivers —
  tous les Acts en héritent sans câblage, `repeat` rejoint les capacités Vector. Variable de boucle
  `as` (défaut `item`) exposée au template le temps de l'itération, validation sémantique récursive
  des branches, identifiants de steps imbriqués traçables (`loop[2].fetch`), schéma des steps
  formalisé (`when`, `then`/`else`/`steps`). Deux exemples zéro config dans `examples/vector/`.
  Voir [docs/blueprint-schema.md](docs/blueprint-schema.md).
- **Persistance durable (Jalon 1.5-A)** — socle de stockage SQLite (stdlib `sqlite3`, mode WAL, zéro
  dépendance) sous `~/.aetherius/aetherius.db`, avec migrations versionnées (`PRAGMA user_version`) et
  trois dépôts typés : schedules, historique des runs, état clé/valeur inter-run (`compare_and_set`
  pour la déduplication d'alertes). Le daemon persiste désormais le résultat de ses runs dans le store
  (migration douce, sans régression). Voir [docs/store.md](docs/store.md).
- **Cadrage Phase 1.5** — squelette (stubs, interfaces, contrats) et spécifications par jalon pour
  rendre le socle **récurrent, réactif et furtif** : persistance SQLite (`store/`), notifications
  natives (`notify/`), scheduler du daemon, flux conditionnel (`when`, `if`/`repeat`/`for_each`),
  plugins, déploiement 24/7, **identité réseau** (`network/` : proxy, rotation d'IP, anti-fuite
  WebRTC, cohérence géo, impersonation TLS) et **durcissement de l'empreinte**
  (`stealth/fingerprint/` : canvas/audio/UA-CH/écran/WebGL2 + identité d'en-têtes pour Vector).
  Aucune capacité n'est encore activée (jalons en attente : l'action `notify` est déclarée mais
  marquée `PENDING`, les modules lèvent une erreur « jalon en attente ») ; `make check` reste vert.
  Nouvel extra optionnel `[network]` (SOCKS5 + `curl_cffi`). Voir [docs/phase-1.5/](docs/phase-1.5/README.md).

### Sécurité
- **Évaluateur `where` (Act I — Vector)** : rejet explicite des attributs magiques (`__class__`,
  `__globals__`, tout nom en `__`) dans l'AST-walk. L'allowlist de nœuds bloquait déjà l'exécution de
  code, mais la traversée d'attributs dunder combinée à une comparaison restait un oracle booléen sur
  le graphe d'objets Python — la garde ferme cette évasion de sandbox sans dépendre de l'absence
  d'appels/indexation.

### Corrigé
- **`precise_sleep` (stealth/humanizer)** : le busy-wait pur sous 20 ms saturait un cœur CPU à 100 %
  (chaque point de geste souris), risque de privation de ressources sur le daemon en multi-run.
  Désormais `time.sleep` cède le CPU pour le gros du délai et le busy-wait ne couvre que la queue
  (~1,5 ms) — précision de timing inchangée, CPU au repos (~9 %).
- **Debug (Act II — Continuum)** : quand les entrées sont humanisées, `slow_mo` est à 0 et les actions
  brutes (`select`, `upload`, `navigate`, …) défilaient instantanément, illisibles en debug. Elles
  reçoivent maintenant un délai manuel équivalent.

### Ajouté
- **Suivi des nouveaux onglets (Act II — Continuum)** : un clic ouvrant un onglet (`target="_blank"`,
  `window.open`) rend la nouvelle page active pour les steps suivants, avec retombée sur une page
  survivante si l'onglet actif se referme. Auparavant les steps restaient bloqués sur l'onglet initial.
- **Recorder « Make input »** : le `type`/`format` de l'input produit est inféré du type HTML du champ
  (`number`, `date`+`format`, `email`/`url`, …) au lieu d'un `string` générique.

## [0.2.0] - 2026-07-10

Première release publique. Elle clôt la **Phase 1** : le socle d'Aetherius, utilisable comme
**bibliothèque** (in-process Python) et comme **service** (daemon local + SDK), avec sa Console.

### Ajouté
- **Daemon local (FastAPI)** — passerelle HTTP + WebSocket exposant le moteur à tout langage
  (`aetherius serve`, bind loopback, token bearer optionnel) : `POST /v1/runs`, `GET /v1/runs/{id}`,
  `WS /v1/runs/{id}/events` (rejeu bufferisé + flux live jusqu'à `done`), `POST /v1/blueprints/validate`,
  `GET /v1/schema`, `GET /health`. L'enregistrement reste host-local (`POST /v1/recorder/sessions` → 501).
  Voir [docs/daemon.md](docs/daemon.md).
- **SDK TypeScript** `@aetherius/client` (Node 20+) — spawn du daemon (ou `baseUrl`),
  `client.run(blueprint, { inputs, secrets, onEvent })`, streaming d'événements typé.
- **Console : écran Settings** — démarrer/arrêter le daemon et voir son statut, sans quitter le terminal.
- **Act I — Vector** : client HTTP/API (requêtes, retries/backoff, 5 stratégies d'auth, extraction
  JSONPath et CSS/XPath, moteur de templates Jinja2).
- **Act II — Continuum** : automatisation d'un vrai navigateur (Playwright, extra `[browser]`) —
  navigation, interactions, extraction DOM, `wait_for` avec échec nommé, sessions persistantes, debug.
- **Système de discrétion (stealth)** : couche transverse (`options.stealth`) — souris humaine par
  rejeu géométrique de gestes, clavier/scroll/timing humains, fingerprint, warmup de profil.
- **Recorder** : création de Blueprint par démonstration (Continuum et Vector) + gesture recorder.
- **Builder headless + Blueprint Studio** : construction guidée de Blueprints sans JSON, avec aperçu
  validé en direct, réutilisable par la Console, le daemon et les SDKs.
- **Console (Textual)** : Library, Runs, Catalog, Recorder, Blueprint Studio, Settings.
- **Contrats** langage-agnostiques (`contracts/`) : schéma Blueprint, OpenAPI du daemon, schéma
  d'événements — source de vérité, gardés par des tests.

### Notes
- SemVer `0.x` : l'API peut évoluer pendant le durcissement de la Phase 1.
- La **Phase 2** ajoutera Act III (Oracle, vision) et Act IV (Phantom, agent autonome).

[Non publié]: https://github.com/kln-mltre/Aetherius/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/kln-mltre/Aetherius/releases/tag/v0.2.0
