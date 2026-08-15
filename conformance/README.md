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
| `run` | `cases/run/` | Ce Blueprint **joué en entier** produit-il les mêmes sorties, les mêmes `StepResult` et la même séquence d'événements ? |

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

### `requires` : quand un cas a besoin d'un navigateur

Un cas peut déclarer `"requires": "browser"` (jalon 3-D). Cela veut dire deux choses différentes de
chaque côté, et c'est bien le sujet :

- **côté Python**, Playwright et un vrai Chromium. Le cas se **skippe proprement** sans l'extra
  `[browser]`, comme tout test marqué `browser` ; le job de CI qui rejoue `make conformance`
  installe l'extra précisément pour que la comparaison ait lieu ;
- **côté embarqué**, une WebView. `@aetherius/engine` est neutre plateforme et n'en a pas : son
  exécuteur **délègue** ces cas, et c'est celui de `@aetherius/react-native` qui les joue, sur un
  hôte adossé à jsdom.

Les deux exécuteurs JavaScript se **recouvrent** au lieu de se partager le corpus — celui de
`@aetherius/react-native` rejoue *tout* — pour qu'aucun cas ne puisse tomber entre les deux à cause
d'une étiquette oubliée. Et chacun échoue si plus aucun cas ne déclare `requires: browser` : une
suite qui skipperait toute la moitié Act II ressemblerait exactement à une suite qui passe.

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

### `run`

Le cas joue un Blueprint **complet** contre un **serveur de fixtures local**, démarré par chaque
harnais sur un port éphémère de la boucle locale. Aucun réseau public : un corpus qui appellerait un
endpoint réel échouerait pour des raisons étrangères à l'accord des deux moteurs.

Le champ `server` décrit les routes, indexées par `"MÉTHODE /chemin"` (la query n'entre pas dans la
clé) ; le harnais passe l'URL de base au Blueprint dans l'entrée **`base_url`**, et `inputs` ajoute
le reste.

| Champ de route | Effet |
|----------------|-------|
| `status` | Code de statut (200 par défaut). |
| `headers` | En-têtes de réponse (un `Set-Cookie`, un `Location`, …). |
| `body` | Corps littéral ; `Content-Type: text/plain` par défaut. |
| `charset` | Encodage des octets de `body` : `utf-8` (défaut) ou `iso-8859-1`. Une étiquette inconnue **fait échouer le harnais** au lieu de retomber sur UTF-8 — un cas qui servirait silencieusement de l'UTF-8 passerait en ne prouvant rien. |
| `json` | Corps sérialisé en JSON compact ; `Content-Type: application/json` par défaut. |
| `html` | Corps littéral servi en `text/html` — ce qu'un navigateur exige pour parser un document au lieu d'en montrer la source. |
| `echo` | Répond par une description JSON de la requête reçue : `method`, `path`, `query`, `body`, `headers`. |

`echo` est l'outil de parité le plus utile du corpus : le **Blueprint** extrait lui-même le corps, la
query ou un en-tête, donc ce sont les deux moteurs qui sont comparés — le harnais n'a aucune idée de
la façon dont un formulaire devrait être encodé, et c'est bien ainsi.

`charset`, lui, sert la seule question qu'un corpus en JSON ne peut pas poser autrement : le corps
qui part sur le réseau n'est plus celui qu'on lit dans le fichier de cas. C'est ce qui permet de
servir une réponse **mal étiquetée** — des octets UTF-8 annoncés en `iso-8859-1` — et d'exiger des
deux moteurs le **même** mojibake, plutôt que de faire confiance à chacun pour deviner.

La valeur comparée est un **résumé normalisé** du run. Les identifiants de run et les durées en sont
absents : ils diffèrent par nature, et les comparer rendrait chaque cas instable.

```json
{
  "name": "run-vector-request-and-extract",
  "kind": "run",
  "server": { "GET /users": { "json": [{ "id": 1 }] } },
  "blueprint": { "…": "utilise {{ inputs.base_url }}/users" },
  "expect": {
    "python": {
      "outcome": "rendered",
      "value": {
        "status": "success",
        "outputs": { "count": 1 },
        "steps": [{ "step_id": "fetch", "action": "http.request", "status": "success" }],
        "events": [{ "type": "progress", "step_id": null }]
      }
    },
    "embedded": { "…": "idem" }
  }
}
```

Un run **échoué** reste un résultat : l'`outcome` demeure `rendered`, `value.status` vaut `failed`,
et le message d'échec alimente `message_contains` — ce qui permet de figer *comment* un Blueprint
échoue sans dépendre d'une URL à port éphémère. Une exception qui s'échappe du run (une
`TemplateError` dans les `outputs`, par exemple) donne, elle, l'`outcome` `error`.

## Ajouter un cas

1. Écrire le fichier sous `cases/<famille>/`, en nommant le **comportement** figé, pas le code
   traversé.
2. Renseigner les deux moteurs. Si les attentes divergent, la `description` doit dire **pourquoi** :
   une divergence non expliquée est indiscernable d'un bug.
3. `make conformance`. Aucun exécuteur n'a besoin d'être touché : les deux découvrent les fichiers.

Ajouter un **`kind`**, en revanche, demande de toucher les deux exécuteurs — et c'est voulu : une
nouvelle question ne doit pas pouvoir n'être posée qu'à un seul moteur.

## Les exécuteurs

| Moteur | Exécuteur | Serveur de fixtures (`run`) |
|--------|-----------|------------------------------|
| Python | [`tests/conformance/`](../tests/conformance/) — rejoué aussi par `make test`. | [`tests/conformance/server.py`](../tests/conformance/server.py) |
| Embarqué | [`sdks/engine/test/conformance.test.js`](../sdks/engine/test/conformance.test.js) — rejoué aussi par `npm test`. Délègue les cas `requires: browser`. | [`sdks/engine/test/fixture-server.mjs`](../sdks/engine/test/fixture-server.mjs) |
| Embarqué + Act II | [`sdks/react-native/test/conformance.test.js`](../sdks/react-native/test/conformance.test.js) — rejoue le corpus **entier**, driver WebView enregistré sur un hôte jsdom. | idem (le harnais du moteur est importé, pas recopié) |

Tous chargent le même répertoire et appliquent la même comparaison — le troisième **importe** le
harnais du second plutôt que d'en dupliquer la logique. Un exécuteur qui « passerait » un cas qu'il
ne sait pas lire serait un faux vert : chacun vérifie que le corpus n'est pas vide, que chaque cas
nomme bien son moteur, qu'il reste des cas `requires: browser`, et un `kind` inconnu échoue au lieu
de passer.
