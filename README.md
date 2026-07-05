# Aetherius

```text
▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚
 ˚ ✦ ·       ✦      · ˚       ✦ ·      ˚ ·     ✦    · ˚ ✦      · ✦ ˚
 █████╗ ███████╗████████╗██╗  ██╗███████╗██████╗ ██╗██╗   ██╗███████╗
██╔══██╗██╔════╝╚══██╔══╝██║  ██║██╔════╝██╔══██╗██║██║   ██║██╔════╝
███████║█████╗     ██║   ███████║█████╗  ██████╔╝██║██║   ██║███████╗
██╔══██║██╔══╝     ██║   ██╔══██║██╔══╝  ██╔══██╗██║╚██╗ ██╔╝╚════██║
██║  ██║███████╗   ██║   ██║  ██║███████╗██║  ██║██║ ╚████╔╝ ███████║
╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝  ╚══════╝
            ❧──────────────────── ❦ ────────────────────❧
                     ✦  per nubes, ad aethera  ✦
▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚▞▚
```

> Se veut le produit du concept de bot web modulaire, poussé à son paroxysme.   
> Capable de réaliser, sur la base d'un simple fichier d'instructions, n'importe quelle tâche.

## La vision

Dans la plupart des projets on réécrit le même code fragile : requêtes `axios`/HTTP, scraping,
automatisation de navigateur. C'est répétitif, fastidieux, et ça casse dès que le site ou l'API
change — il faut alors éditer ce code éparpillé dans chaque projet.

**Aetherius inverse le problème.** Le moteur du bot est fixe et robuste. Le comportement, lui, est
décrit dans un **fichier d'instructions déclaratif** (un *Blueprint*, en JSON). Quand un site
change, on corrige **un Blueprint**, pas N codebases. Et parce que le moteur est exposé via un
**daemon local**, on le pilote depuis **n'importe quel langage** (TypeScript, Python, …) avec le
même fichier d'instructions.

Aetherius est conçu pour être **exporté comme bibliothèque** et alimenter tous les projets :
récupérer un emploi du temps via API, scraper une page derrière un login, publier une vidéo en
restant indétectable, ou lâcher un agent autonome sur une tâche non scriptée.

Aetherius est à la fois une **bibliothèque** (consommée en direct ou via un daemon par les apps clientes)
et un **outil** : une **Console dans le terminal** pour créer, tester et gérer tout ça sans écrire
une ligne de JSON à la main.

<p align="center"><sub>▚▞▚ ✦ ▞▚▞</sub></p>

## Le concept : 4 Acts

Aetherius est un interprète qui joue en quatre **Acts**, du plus léger au plus puissant. Le
Blueprint choisit l'Act adapté à la tâche.

| Act | Nom | Moteur | Quand l'utiliser |
|-----|-----|--------|------------------|
| **I** | **Vector** | Requêtes HTTP/API | Les données sont derrière une API ou des endpoints stables. Le cas « axios ». Le plus rapide. |
| **II** | **Continuum** | Navigateur scripté (Playwright) | Il faut un vrai navigateur : login, JS, session, DOM. Sélecteurs connus et stables. |
| **III** | **Oracle** | Navigateur guidé par vision + discrétion | L'UI est fragile/obfusquée : Aetherius « voit » l'écran via un petit modèle entraîné et agit avec discrétion. |
| **IV** | **Phantom** | Agent autonome | Objectif non scripté. Perçoit, raisonne, agit en boucle. Résilience maximale. Le plus lourd. |

Plus l'Act est élevé, plus le Blueprint est **haut-niveau** (on décrit *quoi*, plus *comment*) et
plus les dépendances sont lourdes (installées à la demande via des *extras*).

### Act I — Vector
Client HTTP robuste : requêtes GET/POST, encodage form/JSON, en-têtes, retries avec backoff,
pagination, stratégies d'authentification (cookie, bearer, basic, form-login type CAS), extraction
déclarative (JSONPath pour le JSON, CSS/XPath pour le HTML). Remplace les services `axios` écrits à
la main ; les constantes magiques disséminées deviennent des `inputs` typés et documentés.

### Act II — Continuum
Automatisation d'un vrai navigateur (Playwright) qui suit le Blueprint à la lettre : navigation,
remplissage, clics, attentes, extraction DOM, bridge JavaScript injecté. Gère les scénarios qui
exigent un navigateur : login, cookies de session, contenu rendu par JS. C'est l'équivalent propre
et réutilisable d'une « WebView cachée qui scrape ». Discrétion optionnelle.

### Act III — Oracle
Quand les sélecteurs sont trop fragiles ou absents, Oracle **regarde l'écran**. Un petit modèle de
vision entraîné spécifiquement pour la tâche (exporté en ONNX) localise les éléments cibles sur des
captures d'écran ; Aetherius clique par coordonnées à travers la couche de discrétion. Idéal pour
les interfaces qui changent souvent ou piègent les bots.

### Act IV — Phantom
Un agent décisionnel autonome. Boucle **percevoir → raisonner → agir** : il perçoit la page (vision
+ DOM + arbre d'accessibilité), un planner (par défaut Claude, ex. `claude-fable-5` /
`claude-opus-4-8`, remplaçable par un VLM local) décide de l'action suivante, et l'action est jouée
via la couche de discrétion. Pour les objectifs non scriptés et la résilience maximale.

> Aetherius est destiné à l'automatisation **autorisée** : ses propres comptes, ses propres données,
> ses propres workflows.

<p align="center"><sub>▚▞▚ ✦ ▞▚▞</sub></p>

## Les fichiers d'instructions : les Blueprints

Un Blueprint est un fichier JSON déclaratif et versionné. Enveloppe :

```json
{
  "aetherius": "1.0",
  "name": "domaine.tache",
  "act": "vector",
  "inputs":  { "param": { "type": "string", "required": true } },
  "secrets": ["cle_injectee_au_runtime"],
  "vars":    { "domain": "https://exemple.fr" },
  "options": {
    "debug": false,
    "stealth": "off",
    "session": { "profile": "mon-profil", "persist": true },
    "timeout_ms": 30000,
    "retries": { "max": 3, "backoff": "exponential" }
  },
  "steps":   [ /* la séquence d'actions */ ],
  "outputs": { "resultat": "{{ steps.x.champ }}" }
}
```

- **inputs** : paramètres typés (le Blueprint est réutilisable, pas figé sur une valeur).
- **secrets** : identifiants/token fournis au runtime, **jamais** écrits dans le fichier.
- **vars** : constantes locales (domaines, chemins).
- **options** : `debug`, `stealth`, `session`, `timeout_ms`, `retries`.
- **steps** : le *dictionnaire d'actions* (navigate, click, fill, type, http.request, extract,
  wait, if, for_each, …). Chaque Act déclare quelles actions il supporte ; un Blueprint qui demande
  une action non supportée par son Act échoue à la validation, avec un message clair.
- **outputs** : la forme des données retournées, via interpolation `{{ }}`.

Le format est défini une fois pour toutes dans [`contracts/blueprint.schema.json`](contracts/blueprint.schema.json).
Des exemples exécutables (dérivés de vrais projets) sont dans [`examples/`](examples/).

### Exemple — Act I (Vector) : emploi du temps par API
Voir [`examples/vector/ukit-planning-week.blueprint.json`](examples/vector/ukit-planning-week.blueprint.json).

```json
{
  "aetherius": "1.0",
  "name": "ukit.planning.week",
  "act": "vector",
  "inputs": {
    "group":  { "type": "string", "required": true },
    "monday": { "type": "string", "format": "date", "required": true }
  },
  "vars": { "domain": "https://ade-web.exemple.fr" },
  "steps": [
    {
      "id": "week",
      "action": "http.request",
      "method": "POST",
      "url": "{{ vars.domain }}/calendar/data",
      "headers": {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json"
      },
      "form": {
        "start": "{{ inputs.monday }}",
        "end": "{{ inputs.monday | add_days(7) }}",
        "resType": "103",
        "calView": "agendaWeek",
        "federationIds[]": "{{ inputs.group }}",
        "colourScheme": "3"
      },
      "expect": { "status": 200 },
      "extract": {
        "events": {
          "from": "json", "path": "$[*]",
          "where": "item.eventCategory != 'Vacances'",
          "fields": {
            "id": "$.id", "start": "$.start", "end": "$.end",
            "category": "$.eventCategory", "color": "$.backgroundColor",
            "description": "$.description"
          }
        }
      }
    }
  ],
  "outputs": { "events": "{{ steps.week.events }}" }
}
```
Les constantes autrefois codées en dur (`resType`, `colourScheme`) sont explicites, le filtrage
`Vacances` et le parsing sont déclaratifs, et le groupe/la date sont des `inputs` réutilisables.

### Exemple — Act II (Continuum) : login CAS + scraping
Voir [`examples/continuum/ukit-scolarite-login.blueprint.json`](examples/continuum/ukit-scolarite-login.blueprint.json).

```json
{
  "aetherius": "1.0",
  "name": "ukit.scolarite.cold",
  "act": "continuum",
  "secrets": ["cas_user", "cas_pass"],
  "options": { "session": { "profile": "scolarite", "persist": true }, "debug": false },
  "steps": [
    { "action": "navigate",  "url": "https://cas.exemple.fr/login" },
    { "action": "fill",      "selector": "#username", "value": "{{ secrets.cas_user }}" },
    { "action": "fill",      "selector": "#password", "value": "{{ secrets.cas_pass }}" },
    { "action": "click",     "selector": "input[name=submit]" },
    { "action": "wait_for",  "selector": ".ent-dashboard", "timeout_ms": 15000,
      "on_timeout": "fail:LOGIN_FAILED" },
    { "action": "emit",      "event": "LOGIN_SUCCESS" },
    { "action": "navigate",  "url": "https://ent.exemple.fr/dossier" },
    { "action": "extract",   "outputs": {
        "firstName":     { "selector": ".identity .firstname", "as": "text" },
        "studentNumber": { "selector": "#num-etudiant", "as": "text" },
        "ine":           { "selector": "#ine", "as": "text" },
        "email":         { "selector": ".mail", "as": "text" }
    }},
    { "action": "navigate",  "url": "https://webmail.exemple.fr" },
    { "action": "extract",   "outputs": { "unread": { "selector": ".unread-count", "as": "number" } } }
  ]
}
```
Les sélecteurs sont désormais des **données** (plus du JS injecté codé en dur), le flux de login est
déclaratif, et les événements (`LOGIN_SUCCESS`, …) restent disponibles pour suivre la progression.

### Exemple — Act III (Oracle) : upload avec discrétion
Voir [`examples/oracle/tiktok-upload.blueprint.json`](examples/oracle/tiktok-upload.blueprint.json).

```json
{
  "aetherius": "1.0",
  "name": "tiktok.upload",
  "act": "oracle",
  "inputs": {
    "video":   { "type": "path",   "required": true },
    "caption": { "type": "string", "required": true }
  },
  "options": {
    "session": { "profile": "tiktok", "persist": true },
    "stealth": {
      "mouse": "gestures", "keyboard": "human", "scroll": "eased",
      "timing": { "distraction": 0.1 }, "fingerprint": "chrome-desktop"
    },
    "debug": false
  },
  "vision": { "model": "tiktok-studio-ui@1" },
  "steps": [
    { "action": "navigate", "url": "https://www.tiktok.com/tiktokstudio/upload?lang=fr" },
    { "action": "wait",     "min_ms": 3500, "max_ms": 6000 },
    { "action": "upload",   "target": { "vision": "upload dropzone" }, "file": "{{ inputs.video }}" },
    { "action": "type",     "target": { "vision": "caption textarea" }, "text": "{{ inputs.caption }}" },
    { "action": "wait",     "min_ms": 2000, "max_ms": 4500 },
    { "action": "click",    "target": { "vision": "Post button" } },
    { "action": "wait_for", "target": { "vision": "publish success toast" }, "timeout_ms": 35000 }
  ]
}
```

<p align="center"><sub>▚▞▚ ✦ ▞▚▞</sub></p>

## La Console Aetherius : tout gérer depuis le terminal

Aetherius n'est pas qu'une bibliothèque : c'est aussi une **Console interactive dans le terminal**
(construite avec Textual), le centre de contrôle de l'outil. On la lance simplement :

```bash
aetherius            # ouvre la Console
```

> **État actuel** : la Console est navigable de bout en bout. Library, Runs et Catalog sont
> pleinement fonctionnels pour Act I (Vector) et Act II (Continuum, avec l'extra `[browser]`) ; le
> Blueprint Studio, le Recorder et Sessions/Settings (daemon) affichent honnêtement leur jalon en
> attente tant que builder/recorder/stealth/daemon ne sont pas implémentés. Détails :
> [docs/console.md](docs/console.md).

Depuis la Console, sans écrire de JSON à la main :
- **Créer et éditer des Blueprints** via le **Blueprint Studio** (voir plus bas).
- **Lancer des runs** et suivre en direct leurs événements, logs et artefacts.
- **Explorer et comprendre** les 4 Acts et les modèles de vision disponibles (fiches explicatives).
- **Gérer les profils/sessions** persistants et lancer un warmup.
- **Piloter le daemon** (démarrer/arrêter) et la configuration.
- **Parcourir la bibliothèque** de Blueprints (dupliquer, éditer, supprimer).

### Créer un Blueprint : trois voies

1. **Le Blueprint Studio (guidé, rapide, sans JSON)** — dans la Console. Sélection de l'Act (avec
   son explication), ajout des steps via des formulaires, **aperçu JSON live** validé contre le
   schéma en temps réel. L'option la plus rapide pour la majorité des cas.
2. **Le Recorder (par démonstration)** — pour les tâches d'automatisation navigateur : l'action est
   réalisée dans un navigateur visible, Aetherius capture et recrache un Blueprint propre, avec
   **synthèse de sélecteurs robustes** (privilégie `data-testid`/aria/texte avant les chemins CSS
   fragiles). Idéal quand la démonstration directe est plus simple que la description.
3. **JSON à la main** — pour les power users qui veulent le contrôle total.

La logique de construction vit dans un module `builder/` *headless* : la Console n'en est que
l'habillage, et le daemon peut l'exposer pour construire des Blueprints programmatiquement.

## La discrétion (stealth), en option modulaire

La discrétion n'est **pas** liée à un Act : c'est une couche transverse activée par
`options.stealth`, applicable à tout Act qui pilote un navigateur (II, III, IV). Désactivée par
défaut (no-op).

Techniques disponibles (issues et généralisées du système *BioMouse* éprouvé) :
- **Souris humaine** : rejeu d'un geste humain *réellement enregistré*, transformé
  géométriquement (mise à l'échelle + rotation) pour atteindre n'importe quelle cible. Matching du
  meilleur geste par distance et angle, timing inter-points préservé à la microseconde. Clics
  off-center (30–70 % de l'élément), micro-pauses avant/pendant le clic.
- **Clavier humain** : vitesse variable par session, fautes de frappe suivies de corrections,
  délais accrus sur les espaces et caractères spéciaux.
- **Scroll humain** : courbe d'easing ease-out cubique (départ rapide, fin douce).
- **Timing humain** : délais aléatoires, pauses « distraction » occasionnelles, parking du curseur
  pendant les attentes longues.
- **Fingerprint** : masquage `navigator.webdriver`, `chrome.runtime`, `plugins`, `permissions` ;
  profils de fingerprint cohérents (UA, viewport, timezone, WebGL, canvas).
- **Profils persistants + warmup** : réutilisation d'un profil navigateur pour construire un
  historique authentique (cookies, cache) avant l'automatisation.

Activation :
```json
"options": { "stealth": { "mouse": "gestures", "keyboard": "human", "fingerprint": "chrome-desktop" } }
```
`"stealth": "off"` (défaut) ou `"stealth": "nom-de-preset"` sont aussi acceptés.

**IA pour la discrétion ?** Approche hybride retenue : le rejeu géométrique de gestes est le moteur
par défaut (léger, éprouvé, score reCAPTCHA élevé) — **pas besoin d'IA**. Deux upgrades ML
*optionnels* sont prévus derrière la même interface : un modèle génératif de mouvements (pour ne pas
se limiter à une bibliothèque finie de gestes) et un modèle de fingerprints cohérents. À activer
seulement si un cas d'usage le justifie.

## Le mode Debug

`options.debug: true` :
- **Acts navigateur (II/III/IV)** : fenêtre visible, overlay du curseur, surlignage des cibles,
  ralenti (slow-mo). Idéal pour comprendre pourquoi un step échoue.
- **Acts sans navigateur (I)** : logs terminal structurés (requêtes, réponses, extractions).
- Tous les Acts émettent des **événements** consommables (progression, artefacts : screenshots,
  HAR, snapshots DOM) écrits dans un répertoire de run.

## Le Gesture Recorder

En complément, un *gesture recorder* capture des traces de souris humaines réelles pour enrichir la
bibliothèque de gestes du système de discrétion. (Le Blueprint recorder, lui, est décrit plus haut
dans « Créer un Blueprint : trois voies ».)

<p align="center"><sub>▚▞▚ ✦ ▞▚▞</sub></p>

## Interopérabilité multi-langage

Le cœur est en Python ; il est exposé à tous les langages via un **daemon local**.

```
┌─────────────┐   Blueprint + inputs + secrets    ┌──────────────────────────┐
│  App        │ ────────────────────────────────► │  Aetherius Daemon        │
│ (TS/Python) │        HTTP  +  WebSocket          │  (FastAPI)               │
│  SDK mince  │ ◄──────────────────────────────── │  Runtime → Act I..IV     │
└─────────────┘   résultat + flux d'événements     └──────────────────────────┘
```

- **Daemon** : `aetherius serve` (local, 127.0.0.1, token optionnel).
  - `POST /v1/runs` → `run_id` ; `GET /v1/runs/{id}` → statut + résultat.
  - `WS /v1/runs/{id}/events` → flux d'événements (debug/progression).
  - `POST /v1/blueprints/validate`, `GET /v1/schema`, `POST /v1/recorder/sessions`.
- **SDK TypeScript** `@aetherius/client` : peut spawn le daemon, `client.run(blueprint, { inputs,
  secrets })`, stream d'événements typé.
- **SDK Python** : idem, plus l'import in-process direct (`import aetherius`, sans daemon).
- **Contrats** ([`contracts/`](contracts/)) : JSON Schema du Blueprint + OpenAPI du daemon = source
  de vérité ; les types des SDK en sont générés.

### Exécuter un Blueprint depuis le code applicatif

La Console sert à *créer et gérer* les Blueprints. L'**exécution**, elle, se fait directement depuis
le code applicatif, en chargeant un Blueprint **existant** — la Console n'est jamais requise au runtime.

Python (in-process, sans daemon) :
```python
from aetherius import Aetherius

client = Aetherius()
result = client.run(
    "blueprints/ukit-planning-week.blueprint.json",
    inputs={"group": "TP-A1", "monday": "2026-09-07"},
)
print(result.outputs["events"])
```

TypeScript (via le daemon local, spawné automatiquement) :
```ts
import { Aetherius } from "@aetherius/client";

const client = new Aetherius();
const result = await client.run("blueprints/ukit-planning-week.blueprint.json", {
  inputs: { group: "TP-A1", monday: "2026-09-07" },
});
console.log(result.outputs.events);
```

<p align="center"><sub>▚▞▚ ✦ ▞▚▞</sub></p>

## Architecture du dépôt

```
src/aetherius/
  core/        blueprint (models/loader/validator/template), actions (le dictionnaire),
               runtime (engine/context/selector/result), extraction, events, errors, driver
  acts/        vector (I), continuum (II), oracle (III), phantom (IV)
  stealth/     policy, humanizer (mouse/keyboard/scroll/timing), gestures, fingerprint,
               session (store/warmup), ml (optionnel)
  recorder/    blueprint_recorder, gesture_recorder, capture, selector_synth
  builder/     construction headless de Blueprint (factory, catalog, templates)
  console/     interface terminale globale (Textual) : Blueprint Studio, runs, catalogue,
               sessions, settings — la porte d'entrée de l'outil
  models/      registry + cache des assets ML runtime
  server/      daemon FastAPI (routes/jobs/schemas)
  config/      settings
contracts/     blueprint.schema.json, openapi.yaml, events.schema.json  (source de vérité)
sdks/          typescript (@aetherius/client), python
examples/      Blueprints de démonstration
training/      entraînement des modèles Oracle (hors runtime)
legacy_examples/  code de référence des projets d'origine (UKit, TikTok) + carte de provenance
```

Principe : chaque fichier de logique reste sous ~300 lignes ; typage strict (pydantic) ; erreurs
typées (jamais avalées) ; les Acts sont des drivers interchangeables derrière une interface commune.

## Installation (cible)

```bash
pip install aetherius            # cœur + Act I (Vector) + daemon + Console
pip install aetherius[browser]   # + Act II (Continuum)
pip install aetherius[vision]    # + Act III (Oracle)
pip install aetherius[agent]     # + Act IV (Phantom)
pip install aetherius[all]
```

Puis pour lancer la Console :
```bash
aetherius            # centre de contrôle interactif dans le terminal
```

## Développement

Pour travailler sur Aetherius (et pas seulement le consommer). Prérequis : Python 3.11+ et, pour le
SDK TypeScript, Node 20+.

```bash
git clone <repo> && cd Aetherius
make install-dev          # installe le paquet en editable + les outils de dev
```

Le `Makefile` est le point d'entrée unique — les mêmes cibles servent en local et en CI :

```bash
make check                # avant de commit : format + lint (ruff) + types (mypy) + tests (pytest)
make test                 # tests seuls, avec couverture
make check-all            # tout le dépôt : Python + SDK TypeScript
make help                 # liste des cibles
```

Conventions de contribution (discipline de test, invariants, structure des tests) :
[`CONTRIBUTING.md`](CONTRIBUTING.md) et [`docs/testing.md`](docs/testing.md).

<p align="center"><sub>▚▞▚ ✦ ▞▚▞</sub></p>

## État d'avancement

- [x] Vision, concept des 4 Acts, format Blueprint, architecture.
- [x] Squelette : arborescence + stubs + contrats + exemples.
- [x] **Act I — Vector** : moteur HTTP/API complet. `Aetherius().run(blueprint, inputs=...)` fonctionnel. Couverture : http.request (form/JSON/params/headers), extraction JSONPath avec `where` et mapping de champs, extraction HTML CSS/XPath, authentification (NoAuth/Bearer/Basic/Cookie/CAS form-login), retries/backoff (tenacity), moteur de templates Jinja2 (`{{ inputs.x | add_days(7) }}`), bus d'événements, hiérarchie d'erreurs typées. 69 tests, mypy strict, lint propre.
- [x] **Console (Textual)** : navigation complète (`aetherius` ou `aetherius console`) — Library,
  Runs et Catalog fonctionnels pour Act I (parcours des Blueprints, exécution avec formulaire
  d'inputs/secrets et flux d'événements en direct, catalogue des 4 Acts). CLI scriptable
  (`aetherius run|validate`). Sessions, Settings et Recorder affichent honnêtement leur jalon en
  attente ; voir [docs/console.md](docs/console.md).
- [x] **Act II — Continuum** : automatisation d'un vrai navigateur (Playwright, API synchrone).
  Actions navigateur (navigate/back/forward/reload, click/fill/type/press/select/hover/scroll/
  upload/drag), `wait_for` avec échec nommé (`on_timeout: "fail:CODE"`), extraction DOM typée
  (text/number/html/attr/count), `evaluate` (JS injecté), `screenshot` (artefact), sessions
  persistantes (profils réutilisés) et mode debug (fenêtre visible + slow-mo). Actions utilitaires
  partagées avec Vector via un mixin (zéro duplication). Extra `[browser]` chargé à la demande ;
  `import aetherius` reste léger. Tests unitaires (page factice, CI de base) + intégration vrai
  Chromium (job CI dédié). Discrétion : couture prête, implémentation dans un jalon distinct.
- [ ] Système de discrétion (humanizer + gestures + fingerprint + session).
- [ ] Recorder (blueprint + gestes).
- [ ] Builder headless (Blueprint Studio).
- [ ] Daemon + SDK TypeScript.
- [ ] Act III — Oracle (vision + entraînement).
- [ ] Act IV — Phantom (agent).

## Sources de référence

Ce README et [`legacy_examples/README.md`](legacy_examples/README.md) constituent la documentation
de référence complète du projet : vision, 4 Acts, format Blueprint, architecture. Les fichiers de
[`legacy_examples/`](legacy_examples/) (carte de provenance) sont les cas d'usage réels à l'origine
de chaque décision de conception.

---

<p align="center"><sub>❧ ▚▞▚ &nbsp;✦&nbsp; per nubes, ad aethera &nbsp;✦&nbsp; ▚▞▚ ❦</sub></p>
