# Le format Blueprint

Spécification faisant foi : [`contracts/blueprint.schema.json`](../contracts/blueprint.schema.json).
Exemples exécutables : [`examples/`](../examples/).

## Enveloppe

| Champ | Type | Rôle |
|-------|------|------|
| `aetherius` | string | Version du format (ex. `"1.0"`). |
| `name` | string | Identifiant pointé, ex. `domaine.tache`. |
| `act` | enum | `conduit` \| `marionette` \| `oracle` \| `phantom`. |
| `inputs` | object | Paramètres typés (réutilisabilité). |
| `secrets` | string[] | Noms des secrets injectés au runtime, jamais stockés. |
| `vars` | object | Constantes locales. |
| `options` | object | `debug`, `stealth`, `session`, `timeout_ms`, `retries`. |
| `steps` | array | Le dictionnaire d'actions (ordonné). |
| `goal` / `constraints` | string / string[] | Alternative haut-niveau pour Phantom. |
| `outputs` | object | Forme des données retournées via `{{ }}`. |

## Interpolation

La syntaxe `{{ ... }}` résout, au runtime, `inputs.*`, `secrets.*`, `vars.*`, `env.*` et les sorties
des steps précédents (`steps.<id>.<champ>`). Des filtres sûrs sont disponibles (ex. `add_days`).

## Validation

Deux niveaux : (1) schéma JSON (structure), (2) validation sémantique (`core/blueprint/validator.py`)
qui vérifie que chaque `action` est supportée par l'`act` choisi (modèle de capabilities) et propose
un Act supérieur si besoin.
