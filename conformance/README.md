# Corpus de conformance

Le même Blueprint, les deux moteurs, le même verdict.

Aetherius a deux implémentations : le moteur Python (`src/aetherius/`) et le moteur embarqué
TypeScript (`sdks/engine/`, Phase 3). Les [`contracts/`](../contracts/) disent ce qu'un Blueprint
*est* ; ce corpus dit ce qu'un moteur doit en *faire*. C'est la garde qui empêche les deux de
diverger en silence — une divergence non détectée serait pire qu'un seul moteur.

```bash
make conformance      # rejoue le corpus sur les deux moteurs
```

Il ne teste pas du code : il fige une sémantique. Un cas n'est pas rangé ici parce qu'il couvre une
ligne, mais parce qu'il fixe une décision qu'on ne veut plus avoir à reprendre.

## Format d'un cas

Un fichier JSON par cas, sous `cases/<famille>/`. Un cas déclare son `kind` — `validation` par
défaut, ce qui laisse les cas du jalon 3-A inchangés.

| `kind` | Répertoire | Question figée |
|--------|-----------|----------------|
| `validation` | `cases/validation/` | Ce Blueprint est-il accepté, et sinon avec quelle erreur ? |
| `expression` | `cases/expression/` | Cette valeur rend-elle la même chose des deux côtés ? |
| `extraction` | `cases/extraction/` | Cette extraction produit-elle les mêmes données ? |
| `truthy` | `cases/truthy/` | La règle de vérité de `when`/`assert` est-elle identique ? |

Les attentes sont **par moteur**, et c'est le cœur du dispositif : les deux ne peuvent pas être
d'accord sur tout. Le moteur embarqué déclare un sous-ensemble strict des capacités (`upload`,
`drag`, `screenshot`, `notify`, Acts III/IV, XPath, JSONPath hors sous-ensemble), donc un Blueprint
parfaitement valide côté Python est légitimement refusé sur appareil. Le corpus est l'endroit où
cette frontière est écrite noir sur blanc, cas par cas — pas dans deux tables de capacités qu'il
faudrait comparer à la main.

Champs communs à toutes les attentes :

- `outcome` : `accepted` / `rejected` pour un cas de validation, `rendered` / `error` pour un cas
  d'exécution. Deux vocabulaires distincts, pour qu'un cas ne puisse pas passer avec le mauvais
  `kind`.
- `error` : le nom de la classe d'erreur attendue (`BlueprintLoadError`, `BlueprintSchemaError`,
  `BlueprintValidationError`, `TemplateError`, `ExtractionError`). Les deux moteurs portent la même
  hiérarchie.
- `message_contains` : sous-chaînes exigées dans le message. Les formulations diffèrent d'un moteur
  à l'autre — c'est voulu, chaque moteur parle de ce qu'il sait —, d'où des attentes séparées.
- `value` : la valeur attendue d'un cas d'exécution, comparée en JSON canonique (clés triées).

### `validation`

```json
{
  "name": "not-portable-upload",
  "description": "upload est valide pour continuum, mais une WebView n'expose pas de file chooser.",
  "blueprint": { "aetherius": "1.0", "name": "…", "act": "continuum", "steps": [] },
  "expect": {
    "python":   { "outcome": "accepted" },
    "embedded": {
      "outcome": "rejected",
      "error": "BlueprintValidationError",
      "message_contains": ["upload", "embedded engine"]
    }
  }
}
```

Le Blueprint est fourni de l'une de ces trois façons, exclusives :

| Champ | Usage |
|-------|-------|
| `blueprint` | Le document en clair, dans le fichier de cas. Le défaut. |
| `blueprint_path` | Chemin depuis la racine du dépôt, pour rejouer un vrai `examples/`. |
| `blueprint_text` | Texte brut, pour éprouver l'étape de *parsing* (JSON malformé). |

### `expression`

`value` est rendue contre `context` (le contexte de template : `inputs`, `secrets`, `vars`,
`steps`, …). `value` peut être une chaîne, un tableau ou un objet — la récursion fait partie du
contrat.

```json
{
  "name": "expr-bare-list",
  "kind": "expression",
  "description": "La regle de l'expression nue : une chaine qui est exactement une expression rend l'objet brut.",
  "context": { "steps": { "week": { "events": [1, 2] } } },
  "value": "{{ steps.week.events }}",
  "expect": {
    "python":   { "outcome": "rendered", "value": [1, 2] },
    "embedded": { "outcome": "rendered", "value": [1, 2] }
  }
}
```

### `extraction`

`spec` est un bloc `extract` de step `http.request`, appliqué au texte de `body`. Il traverse le
même chemin de production que le driver (`core/extraction/dispatch.py` d'un côté,
`extraction/index.ts` de l'autre), défauts compris.

```json
{
  "name": "extract-quoted-field",
  "kind": "extraction",
  "body": "{\"headers\": {\"Accept-Language\": \"fr-FR\"}}",
  "spec": { "lang": { "from": "json", "path": "$.headers.'Accept-Language'" } },
  "expect": {
    "python":   { "outcome": "rendered", "value": { "lang": ["fr-FR"] } },
    "embedded": { "outcome": "rendered", "value": { "lang": ["fr-FR"] } }
  }
}
```

### `truthy`

`values` est une table de valeurs ; le résultat est la liste des verdicts. Une seule table
exhaustive vaut mieux que douze fichiers d'une ligne.

## Ajouter un cas

1. Écrire le fichier sous `cases/<famille>/`, en nommant le **comportement** figé, pas le code
   traversé.
2. Renseigner les deux moteurs. Si les attentes divergent, la `description` doit dire **pourquoi** :
   une divergence non expliquée est indiscernable d'un bug.
3. `make conformance`. Aucun exécuteur n'a besoin d'être touché : les deux découvrent les fichiers.

Ajouter un **`kind`**, en revanche, demande de toucher les deux exécuteurs — et c'est voulu : une
nouvelle question ne doit pas pouvoir n'être posée qu'à un seul moteur.

## Les exécuteurs

| Moteur | Exécuteur |
|--------|-----------|
| Python | [`tests/conformance/`](../tests/conformance/) — rejoué aussi par `make test`. |
| Embarqué | [`sdks/engine/test/conformance.test.js`](../sdks/engine/test/conformance.test.js) — rejoué aussi par `npm test`. |

Les deux chargent le même répertoire et appliquent la même comparaison. Un exécuteur qui
« passerait » un cas qu'il ne sait pas lire serait un faux vert : chacun vérifie que le corpus n'est
pas vide, que chaque cas nomme bien son moteur, et un `kind` inconnu échoue au lieu de passer.
