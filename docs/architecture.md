# Architecture

Point de vérité principal : le [README](../README.md) à la racine. Ce dossier `docs/` en détaille
les parties au fil de l'implémentation.

## Couches

1. **Contrats** (`contracts/`) — source de vérité langage-agnostique : `blueprint.schema.json`,
   `openapi.yaml`, `events.schema.json`, et `actions.json` (projection **générée** du dictionnaire
   d'actions, `make contracts`). Tout le reste s'y conforme.
2. **Cœur** (`src/aetherius/core/`) — indépendant du moteur : modèle de Blueprint, dictionnaire
   d'actions, runtime, extraction, bus d'événements, erreurs typées, protocole `ActDriver`.
3. **Acts** (`src/aetherius/acts/`) — quatre drivers interchangeables (Vector, Continuum, Oracle,
   Phantom) derrière l'interface commune, avec un modèle de *capabilities*. Les drivers sont
   **synchrones** (comme le moteur) et importent leur dépendance lourde **paresseusement** dans
   `setup()` : Act II charge Playwright (API synchrone) à ce moment-là, jamais à l'import. Les
   actions Act-agnostiques (`emit`/`wait`/`set`/`assert`) vivent dans `acts/_shared.py`
   (`SharedActionsMixin`), partagées par tous les drivers.
4. **Discrétion** (`src/aetherius/stealth/`) — couche transverse injectée dans les Acts navigateur.
5. **Outils** — `recorder/` (génération de Blueprints/gestes), `builder/` (construction headless),
   `console/` (TUI Textual), `models/` (assets ML runtime).
6. **Gateway** (`src/aetherius/server/`) — daemon FastAPI (HTTP + WebSocket) exposant le moteur à tout
   langage, et les SDKs (`sdks/`). Les runs (bloquants) tournent sur un thread de worker ; les
   événements franchissent la frontière thread → boucle asyncio via le pattern Sink partagé avec la
   Console. Le contrat (`contracts/openapi.yaml` + `events.schema.json`) fait foi. Voir
   [daemon.md](daemon.md).

## Un contrat, deux moteurs

Parce que la source de vérité est un contrat et non une implémentation, une seconde implémentation du
moteur est possible sans dupliquer les décisions. C'est l'objet de la **Phase 3** : `sdks/engine/` et
`sdks/react-native/` portent un moteur TypeScript qui exécute les **mêmes** Blueprints directement
sur un appareil mobile, là où le daemon ne convient pas (les requêtes doivent partir du téléphone de
l'utilisateur, et ses identifiants ne doivent pas transiter par une machine tierce).

Ce moteur couvre les **Acts I et II** ; les Acts cognitifs, la planification et l'outillage restent
l'apanage du moteur Python. Trois gardes, en place depuis le jalon 3-A, empêchent la dérive :
`contracts/actions.json` (projection générée du registre d'actions, consommée par le moteur
TypeScript), la table des capacités embarquées prouvée **sous-ensemble strict** de
`ACT_CAPABILITIES`, et un corpus de conformance rejoué par les deux moteurs (`make conformance`).
Le socle livré est décrit dans [embedded.md](embedded.md) ; cadrage et jalons :
[phase-3/](phase-3/README.md).

## Invariants

- Un fichier de logique reste sous ~300 lignes.
- Typage strict (pydantic v2) ; les erreurs sont typées et jamais avalées.
- `import aetherius` reste léger : aucune dépendance lourde importée au niveau module.
- Le dictionnaire d'actions (`core/actions/registry.py`) est l'unique source ; le catalogue du
  builder (`builder/catalog.py`) en est une projection (pas de duplication). Concrètement, les specs
  déclaratives par action vivent dans `core/actions/{navigation,interaction,data,flow}.py` et sont
  agrégées par le registre ; deux tests anti-drift garantissent la bijection specs ↔ capabilities et
  le dispatch réel specs ↔ drivers (`PENDING_ACTIONS` documente les actions déclarées mais pas encore
  exécutées). Voir [builder.md](builder.md). Les actions et canaux **tiers** se greffent sur les mêmes
  registres par entry-points (`src/aetherius/plugins.py`, Jalon 1.5-E) : voir [plugins.md](plugins.md).
- Les tests co-évoluent avec le code : chaque module de logique a son test miroir dans `tests/`,
  les contrats sont gardés par des tests, et la suite passe sans dépendances lourdes (skips
  propres). Voir [testing.md](testing.md).

## Tests & CI

`make check` enchaîne ruff + mypy + pytest ; `make check-all` ajoute le SDK TypeScript. La CI
(`.github/workflows/ci.yml`) rejoue exactement ces cibles sur Python 3.11/3.12 et compile le SDK
TypeScript. Les tests miroir de `src/` vivent dans `tests/` (unitaires, intégration, contrats) ;
détails et conventions dans [testing.md](testing.md).
