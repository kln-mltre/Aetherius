# Architecture

Point de vérité principal : le [README](../README.md) à la racine. Ce dossier `docs/` en détaille
les parties au fil de l'implémentation.

## Couches

1. **Contrats** (`contracts/`) — source de vérité langage-agnostique : `blueprint.schema.json`,
   `openapi.yaml`, `events.schema.json`. Tout le reste s'y conforme.
2. **Cœur** (`src/aetherius/core/`) — indépendant du moteur : modèle de Blueprint, dictionnaire
   d'actions, runtime, extraction, bus d'événements, erreurs typées, protocole `ActDriver`.
3. **Acts** (`src/aetherius/acts/`) — quatre drivers interchangeables (Vector, Continuum, Oracle,
   Phantom) derrière l'interface commune, avec un modèle de *capabilities*.
4. **Discrétion** (`src/aetherius/stealth/`) — couche transverse injectée dans les Acts navigateur.
5. **Outils** — `recorder/` (génération de Blueprints/gestes), `builder/` (construction headless),
   `console/` (TUI Textual), `models/` (assets ML runtime).
6. **Gateway** (`src/aetherius/server/`) — daemon FastAPI + SDKs (`sdks/`).

## Invariants

- Un fichier de logique reste sous ~300 lignes.
- Typage strict (pydantic v2) ; les erreurs sont typées et jamais avalées.
- `import aetherius` reste léger : aucune dépendance lourde importée au niveau module.
- Le dictionnaire d'actions (`core/actions/registry.py`) est l'unique source ; le catalogue du
  builder en est une projection (pas de duplication).
