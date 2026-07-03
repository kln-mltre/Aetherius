# Entraînement des modèles Oracle (Act III)

Hors runtime. Ce dossier héberge les datasets, scripts et checkpoints d'entraînement des petits
détecteurs de vision utilisés par Act III (Oracle). Les modèles exportés (ONNX) sont consommés à
l'inférence par [`src/aetherius/models/registry.py`](../src/aetherius/models/registry.py) et
référencés dans les Blueprints via `vision.model` (ex. `"tiktok-studio-ui@1"`).

## Conventions

- Un modèle = un cas d'usage (une UI cible), entraîné sur des screenshots annotés de cette UI.
- Pipeline suggéré : capture de screenshots → annotation → entraînement (ultralytics) → export ONNX
  → publication dans le registry avec une version (`nom@version`).
- Les assets lourds (`datasets/`, `checkpoints/`, `runs/`) sont gitignored.

Le détail du pipeline sera documenté au moment de l'implémentation d'Act III.
