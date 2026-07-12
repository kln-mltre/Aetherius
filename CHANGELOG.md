# Changelog

Toutes les évolutions notables du projet sont consignées ici. Le format s'inspire de
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le versionnage suit
[SemVer](https://semver.org/lang/fr/). Tant que la version reste en `0.x`, l'API publique peut encore
évoluer entre deux versions mineures (durcissement de la Phase 1 en conditions réelles).

## [Non publié]

Durcissement du socle Phase 1 avant d'entamer la Phase 2 (audit croisé de la documentation), et
cadrage de la **Phase 1.5** (socle opérationnel : planification, alertes, réactivité).

### Ajouté
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
