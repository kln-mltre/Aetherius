# Entraînement de modèles locaux (Act III — piste optionnelle)

Hors runtime, et **optionnel**. Depuis le cadrage de la Phase 2, Oracle (Act III) grounde ses cibles
par **VLM** (Claude par défaut), **sans entraînement** — voir
[docs/acts/oracle.md](../docs/acts/oracle.md) et [docs/phase-2/README.md](../docs/phase-2/README.md).
Ce dossier n'est donc **pas** requis pour Oracle : il héberge la piste **avancée** où l'on préfère un
**grounder local** (détecteur ONNX / VLM), branché derrière la même interface `Grounder` que le
provider par défaut.

À n'emprunter que si un cas d'usage le justifie (coût, vie privée, zéro appel externe, latence).

## Conventions (si l'on emprunte cette piste)

- Un modèle = un cas d'usage (une UI cible), entraîné sur des screenshots annotés de cette UI.
- Pipeline suggéré : capture de screenshots → annotation → entraînement (ultralytics) → export ONNX
  → publication dans le registry avec une version (`nom@version`).
- Les modèles exportés sont résolus/cachés par
  [`src/aetherius/models/registry.py`](../src/aetherius/models/registry.py) et référencés dans un
  Blueprint via `vision: { provider: "local", model: "nom@version" }`.
- Les assets lourds (`datasets/`, `checkpoints/`, `runs/`) sont gitignored.

Le détail du pipeline sera documenté si/quand le grounder local est implémenté (Jalon 2-B et au-delà).
