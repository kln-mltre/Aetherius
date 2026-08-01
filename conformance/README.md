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

Un fichier JSON par cas, sous `cases/<famille>/`. Le corpus ne contient aujourd'hui que la famille
`validation` (accepté / refusé, et avec quelle erreur) : rien ne s'exécute encore côté embarqué.
Les cas d'exécution arrivent avec les jalons 3-B et 3-C.

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

Les attentes sont **par moteur**, et c'est le cœur du dispositif : les deux ne peuvent pas être
d'accord sur tout. Le moteur embarqué déclare un sous-ensemble strict des capacités (`upload`,
`drag`, `screenshot`, `notify`, Acts III/IV), donc un Blueprint parfaitement valide côté Python est
légitimement refusé sur appareil. Le corpus est l'endroit où cette frontière est écrite noir sur
blanc, cas par cas — pas dans deux tables de capacités qu'il faudrait comparer à la main.

- `outcome` : `accepted` ou `rejected`.
- `error` : le nom de la classe d'erreur attendue (`BlueprintLoadError`, `BlueprintSchemaError`,
  `BlueprintValidationError`). Les deux moteurs portent la même hiérarchie.
- `message_contains` : sous-chaînes exigées dans le message. Les formulations diffèrent d'un moteur
  à l'autre — c'est voulu, chaque moteur parle de ce qu'il sait —, d'où des attentes séparées.

## Ajouter un cas

1. Écrire le fichier sous `cases/validation/`, en nommant le **comportement** figé, pas le code
   traversé.
2. Renseigner les deux moteurs. Si les attentes divergent, la `description` doit dire **pourquoi** :
   une divergence non expliquée est indiscernable d'un bug.
3. `make conformance`. Aucun exécuteur n'a besoin d'être touché : les deux découvrent les fichiers.

## Les exécuteurs

| Moteur | Exécuteur |
|--------|-----------|
| Python | [`tests/conformance/`](../tests/conformance/) — rejoué aussi par `make test`. |
| Embarqué | [`sdks/engine/test/conformance.test.js`](../sdks/engine/test/conformance.test.js) — rejoué aussi par `npm test`. |

Les deux chargent le même répertoire et appliquent la même comparaison. Un exécuteur qui
« passerait » un cas qu'il ne sait pas lire serait un faux vert : chacun vérifie que le corpus n'est
pas vide et que chaque cas nomme bien son moteur.
