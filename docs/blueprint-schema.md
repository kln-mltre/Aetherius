# Le format Blueprint

Spécification faisant foi : [`contracts/blueprint.schema.json`](../contracts/blueprint.schema.json).
Exemples exécutables : [`examples/`](../examples/).

## Enveloppe

| Champ | Type | Rôle |
|-------|------|------|
| `aetherius` | string | Version du format (ex. `"1.0"`). |
| `name` | string | Identifiant pointé, ex. `domaine.tache`. |
| `act` | enum | `vector` \| `continuum` \| `oracle` \| `phantom`. |
| `inputs` | object | Paramètres typés (réutilisabilité). |
| `secrets` | string[] | Noms des secrets injectés au runtime, jamais stockés. |
| `vars` | object | Constantes locales. |
| `options` | object | `debug`, `stealth`, `session`, `timeout_ms`, `retries`. |
| `steps` | array | Le dictionnaire d'actions (ordonné). |
| `vision` | object | Configuration de cognition pour Oracle/Phantom (voir ci-dessous). |
| `goal` / `constraints` | string / string[] | Alternative haut-niveau pour Phantom. |
| `outputs` | object | Forme des données retournées via `{{ }}`. |

### `vision`

Configure le fournisseur de cognition des Acts cognitifs (le schéma accepte ces sous-champs via
`additionalProperties: true` — aucun changement de contrat) :

- `provider` : le backend — `claude` (défaut, extra `[cognition]`) ou `local` (extra `[vision]`,
  détecteur sur la machine) ;
- `model` : le modèle — id Anthropic (défaut `claude-opus-4-8`) ou nom d'asset local `nom@version`.

Détails et résolution : [docs/cognition.md](cognition.md).

## Interpolation

La syntaxe `{{ ... }}` résout, au runtime, `inputs.*`, `secrets.*`, `vars.*`, `env.*` et les sorties
des steps précédents (`steps.<id>.<champ>`). Des filtres sûrs sont disponibles (ex. `add_days`).

Les `secrets` ne portent qu'un **nom** dans le Blueprint ; leur valeur est résolue au runtime depuis
l'environnement ou un `.env` local (jamais stockée dans le fichier). Voir [docs/secrets.md](secrets.md).

## Garde `when`

Tout step accepte un champ optionnel `when: "<expression>"`. Le moteur rend l'expression **avant**
de dispatcher le step et le **saute** si le résultat est faux — même règle de véracité que
`assert` : vrai si le rendu vaut `true`, `1` ou `yes` (insensible à la casse). Un step sauté
produit un `StepResult` de statut `skipped`, un événement `step_skipped`, et **n'écrit pas** de
sortie : y référer ensuite via `steps.<id>` est une erreur de template.

```json
{ "id": "alert", "action": "emit", "when": "{{ steps.check.in_stock | first }}", "message": "RESTOCK" }
```

## Actions de flux

Trois actions exécutent des **steps imbriqués** ; elles sont interprétées par le moteur (pas par
les drivers), donc disponibles à l'identique sur tous les Acts qui les déclarent :

| Action | Paramètres | Sémantique | Sorties |
|--------|------------|------------|---------|
| `if` | `condition`, `then` (steps), `else` (steps, optionnel) | Rend `condition` et exécute la branche correspondante. | `{"branch": "then"\|"else"\|null}` |
| `repeat` | `times` (entier, interpolable), `steps` | Exécute `steps` n fois (`0` = no-op). | `{"iterations": n}` |
| `for_each` | `items` (expression → liste), `as` (défaut `item`), `steps` | Exécute `steps` une fois par élément, la variable de boucle étant exposée au template le temps de l'itération. | `{"iterations": n}` |

Les sorties des steps vivent dans un espace **plat** (`steps.<id>`) : dans une boucle, chaque
itération écrase la précédente — dans le corps de l'itération, `steps.<id>` vaut la valeur
courante ; après la boucle, celle de la dernière itération. Les identifiants affichés (événements,
résultats) portent le chemin complet (`walk.each_user[2].announce`). Une erreur dans une branche
avorte le run, comme pour un step de premier niveau. La garde `when` s'applique aussi aux actions
de flux (un `when` faux saute le bloc entier).

## Validation

Deux niveaux : (1) schéma JSON (structure), (2) validation sémantique (`core/blueprint/validator.py`)
qui vérifie **récursivement** (branches `then`/`else`/`steps` comprises) que chaque `action` est
supportée par l'`act` choisi (modèle de capabilities) et propose un Act supérieur si besoin.
