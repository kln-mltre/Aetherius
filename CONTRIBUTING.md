# Contribuer à Aetherius

Merci de contribuer. Ce document résume le workflow de développement et les conventions à suivre.
Le cadrage produit est dans le [README](README.md), l'architecture dans
[docs/architecture.md](docs/architecture.md).

## Mise en place

Prérequis : Python 3.11+ et, pour le SDK TypeScript, Node 20+.

```bash
make install-dev          # installe le paquet en editable + les outils de dev
```

## Workflow

Une seule commande fait foi, en local comme en CI :

```bash
make check                # format + lint (ruff) + types (mypy) + tests (pytest)
```

Cibles utiles :

```bash
make test                 # tests seuls, avec couverture
make lint                 # ruff
make typecheck            # mypy (strict)
make check-all            # tout le dépôt : Python + SDK TypeScript
make help                 # liste des cibles
```

Ouvre une branche par changement, garde `make check` vert, et découpe en commits lisibles.

## Principes de code

- Un fichier de logique reste sous ~300 lignes ; au-delà, on découpe en sous-modules.
- Typage strict (pydantic v2) ; les erreurs sont typées et jamais avalées.
- `import aetherius` reste léger : aucune dépendance lourde (Playwright, ONNX, OpenCV, Anthropic)
  importée au niveau module — elles sont chargées à la demande dans les Acts.
- Les contrats (`contracts/`) sont la source de vérité ; le code et les SDK s'y conforment.
- Le dictionnaire d'actions (`core/actions/registry.py`) est l'unique source ; le catalogue du
  builder en est une projection (pas de duplication).
- Commentaires sobres, orientés « pourquoi » ; pas d'emoji dans le code ni les logs. Le formatage et
  le lint sont gérés par ruff (`make format`).

## Tests

- Toute nouvelle logique arrive **avec son test miroir** dans `tests/`. Une contribution n'est prête
  que si `make check` est vert.
- La suite doit passer **sans les extras lourds** : un test qui exige `[browser]`, `[vision]` ou
  `[agent]` se skippe proprement via `pytest.importorskip(...)` et porte le marker correspondant.
- Les contrats sont gardés par `tests/contracts/` : les garder verts quand un contrat évolue.
- Structure, markers, fixtures et couverture sont détaillés dans [docs/testing.md](docs/testing.md).

## Intégration continue

La CI (`.github/workflows/ci.yml`) rejoue exactement les cibles `make` sur Python 3.11 et 3.12 et
compile le SDK TypeScript. Il n'y a pas de logique de test hors du `Makefile` : ce qui passe en local
passe en CI, et inversement.
