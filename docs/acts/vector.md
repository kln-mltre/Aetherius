# Act I — Vector (HTTP/API)

**Statut : implémenté et opérationnel** (`make check` vert, 69 tests).

Le plus léger. Client HTTP robuste (`httpx` + `tenacity`) : requêtes GET/POST, encodage form/JSON,
en-têtes, retries/backoff, pagination, auth (cookie, bearer, basic, form-login type CAS), extraction
déclarative JSON (JSONPath), HTML (CSS/XPath) et texte (le corps décodé).

Cas fondateur : les services `axios` de UKit (`PlanningApiService.ts`). Les constantes magiques
(`resType`, `colourScheme`) deviennent des `inputs`/`vars` explicites.

Modules : [`src/aetherius/acts/vector/`](../../src/aetherius/acts/vector/) —
`driver.py`, `client.py`, `auth.py`.

**Act I a deux moteurs.** Depuis le jalon 3-C, le moteur embarqué TypeScript
([`sdks/engine/src/acts/vector/`](../../sdks/engine/src/acts/vector/)) exécute les mêmes Blueprints
sur `fetch`, directement sur l'appareil de l'utilisateur. Les encodages, la politique de reprises et
la sémantique de `expect` y sont reproduits à l'octet près, et le corpus de conformance rejoue des
runs entiers sur les deux. Ce qui diffère (cookies, redirections, `options.stealth` ignorée) est
écrit dans [docs/embedded.md](../embedded.md#act-i--vector-sur-fetch).

Exemple : [`examples/vector/ukit-planning-week.blueprint.json`](../../examples/vector/ukit-planning-week.blueprint.json).

**Recorder** : on peut générer un Blueprint Vector **par démonstration** — le recorder observe les
appels réseau du navigateur et pique les champs JSON à extraire. Voir
[docs/recorder.md](../recorder.md#vector-recorder-act-i--réseau).

## Actions supportées

| Action | Description |
|--------|-------------|
| `http.request` | Requête HTTP (GET/POST/…). Champs : `method`, `url`, `headers`, `form`, `json`, `params`, `expect.status`, `extract`. |
| `set` | Stocke une valeur dans le contexte du run. |
| `assert` | Vérifie une condition rendue ; lève `StatusAssertionError` si fausse. |
| `emit` | Émet un événement nommé sur le bus. |
| `wait` | Pause en millisecondes (rate limiting déclaratif). |
| `if` | Exécute la branche `then` ou `else` selon `condition` (steps imbriqués). |
| `repeat` | Exécute `steps` un nombre fixe de fois (`times`, interpolable). |
| `for_each` | Exécute `steps` une fois par élément de `items`, variable de boucle via `as`. |
| `optional` | Exécute `steps` ; à la première défaillance, saute le reste du bloc et laisse le run finir en `partial`. Pour une lecture d'enrichissement dont l'absence est acceptable — voir [blueprint-schema.md](../blueprint-schema.md#lecture-facultative). |
| `notify` | Envoie une alerte (webhook, Discord, Telegram, ntfy). Champs : `channel`, `message`, `title`, `level`, `target`, `url`, `config` — voir [docs/notifications.md](../notifications.md). |
| `extract` | Déclaré mais en attente en step autonome (l'extraction vit dans `http.request`). |

Tout step accepte en plus la garde **`when`** (sauté si l'expression rend faux, statut `skipped`).
Sémantique détaillée et exemples : [docs/blueprint-schema.md](../blueprint-schema.md#garde-when).

## Flux conditionnel et itération

Le cas fondateur — n'alerter que si une condition extraite est vraie — s'écrit avec `when` :

```json
{ "id": "alert_done", "action": "emit", "when": "{{ steps.fetch.completed | first }}", "message": "TODO_DONE" }
```

`if`/`repeat`/`for_each`/`optional` sont interprétés par le moteur (jamais par le driver) et peuvent
s'imbriquer librement ; la validation descend dans les branches. Exemples exécutables zéro
config : [`jsonplaceholder-todo-alert`](../../examples/vector/jsonplaceholder-todo-alert.blueprint.json)
(garde `when`), [`jsonplaceholder-flow`](../../examples/vector/jsonplaceholder-flow.blueprint.json)
(`if` + `for_each`) et [`optional-bonus-read`](../../examples/vector/optional-bonus-read.blueprint.json)
(un bloc facultatif qui cède, et le run `partial` qui rend quand même ses sorties).

## Extraction

Le champ `extract` d'un step `http.request` accepte un dict de specs :

```json
"extract": {
  "events": {
    "from": "json",
    "path": "$[*]",
    "where": "item.eventCategory != 'Vacances'",
    "fields": {
      "id": "$.id",
      "start": "$.start",
      "category": "$.eventCategory"
    }
  }
}
```

- `from: "json"` → JSONPath via `jsonpath-ng`
- `from: "html"` → CSS/XPath via `parsel`
- `from: "text"` → le **corps décodé**, tel quel (jalon 3-I)
- `where` : expression de comparaison évaluée par AST-walk (seules les comparaisons, la logique booléenne et l'accès aux attributs de `item` sont autorisés ; appels, indexation et **attributs magiques** (`__class__`, `__globals__`, … tout nom en `__`) sont rejetés, fermant l'évasion de sandbox)
- `fields` : mapping nom → JSONPath relatif à chaque item matché

La construction de ces specs vit dans `core/extraction/dispatch.py` (`dispatch_extract`), partagée
avec le corpus de conformance. Le moteur embarqué reproduit le même dialecte sur un sous-ensemble
plus étroit (XPath en moins, JSONPath restreint) : voir
[docs/embedded.md](../embedded.md#expressions-et-extraction).

### `from: "text"` — les formats à lignes

Une réponse qui n'est ni du JSON ni du HTML est de la donnée aussi : iCalendar (RFC 5545), CSV,
vCard, `text/plain`. La forme `text` rend le corps entier, décodé :

```json
"extract": { "ics": { "from": "text" } }
```

Trois décisions, et chacune ferme une question qu'on ne veut plus rouvrir :

- **Le corps n'est jamais publié tout seul.** `http.request` continue de ne rendre que `status_code`
  et `headers` ; sans extraction nommée, la charge utile ne traîne ni dans les journaux, ni dans les
  événements, ni dans la mémoire du run. C'est l'extraction qui dit **ce qu'on garde**.
- **Il n'y a pas de `from: "regex"`.** Filtrer un texte reste applicatif : une seconde grammaire
  d'expressions régulières entre Python et JavaScript diverge tôt ou tard (classes de caractères,
  groupes nommés, quantificateurs), et deux moteurs ne peuvent pas se le permettre. Corollaire visible
  dans l'exemple livré : la garde de forme s'écrit `{{ 'BEGIN:VCALENDAR' in steps.cal.ics }}` — une
  **appartenance**, faute de tranche ou de `startswith` dans le sous-ensemble d'expressions.
- **`path`, `where`, `fields`, `selector`, `attr`, `multiple` sont refusés** avec `from: "text"`, **à
  la validation**, message à l'appui. Les ignorer laisserait un Blueprint croire qu'il filtre.

#### Le décodage suit l'en-tête

`Content-Type: …; charset=…` décide, avec repli UTF-8. Les octets invalides sont **remplacés**, jamais
levés : un corps binaire signifie qu'on s'est trompé de source, et ce n'est pas au moteur de le
deviner. Un BOM est **conservé** (le codec Python ne le retire pas).

| Étiquette | Codec |
|---|---|
| `iso-8859-1`, `iso8859-1`, `iso_8859-1`, `latin-1`, `latin1`, `l1` | Latin-1 strict — **pas** l'alias WHATWG vers cp1252 |
| `windows-1252`, `cp1252`, `win-1252` | cp1252 (les cinq octets indéfinis rendent `U+FFFD`) |
| toute autre étiquette, ou aucune | UTF-8 |

La table est **bornée et partagée** : le moteur embarqué porte la même
([`extraction/charset.ts`](../../sdks/engine/src/extraction/charset.ts)), plutôt que chacun
déléguant à sa plateforme. Accepter ici les centaines de codecs de Python aurait produit exactement
la divergence silencieuse que le corpus de conformance existe pour empêcher — la première source mal
étiquetée l'aurait découverte à notre place, sur un téléphone. L'élargir se fait des deux côtés à la
fois. Le cas `run/18-text-body-and-charset` fige les quatre situations (bien étiqueté, mal étiqueté,
sans `charset`, corps vide).

> Les dialectes `json` et `html`, eux, continuent de lire le corps en UTF-8 avec remplacement : leur
> décodage n'a pas changé, et le corriger serait un autre sujet.

Exemple exécutable :
[`examples/vector/ical-planning-text.blueprint.json`](../../examples/vector/ical-planning-text.blueprint.json)
(export iCal anonyme d'ADE, zéro configuration).

## Authentification

Configurée programmatiquement via `acts/vector/auth.py` :

| Stratégie | Description |
|-----------|-------------|
| `NoAuth` | Défaut, pas d'auth |
| `BearerAuth(token)` | Header `Authorization: Bearer ...` |
| `BasicAuth(user, pwd)` | HTTP Basic via `httpx.BasicAuth` |
| `CookieAuth(cookies)` | Injection de cookies dans le client |
| `CasFormLogin(url, user, pwd)` | GET login page → extrait champs cachés (parsel) → POST credentials → cookies capturés |

Les cookies capturés (par une stratégie ou par un `Set-Cookie` de réponse) sont **réémis sur les
steps suivants** du même run : le client construit sa requête à la main, il attache donc lui-même le
jar avant l'auth. Un en-tête `Cookie` explicite du Blueprint garde la priorité.

## Template engine

`{{ }}` Jinja2 `SandboxedEnvironment` + `StrictUndefined`. Filtres custom :

- `add_days(n)` — ajoute n jours à une date ISO 8601
- `sub_days(n)` — soustrait n jours
- `format_date(fmt)` — reformate avec `strftime`

Les expressions bare `{{ steps.week.events }}` retournent l'objet Python brut (pas sa
représentation string), ce qui préserve les listes et dicts dans le pipeline `outputs`.

## Tester Act I manuellement

```bash
# 1. Installer en mode éditable
make install-dev

# 2. Lancer la suite de tests
make test

# 3. Essai Python in-process (requiert une vraie API ADE ou un mock)
python3 - <<'EOF'
from aetherius import Aetherius
result = Aetherius().run(
    "examples/vector/ukit-planning-week.blueprint.json",
    inputs={"group": "MON_GROUPE", "monday": "2026-09-07"},
)
print(result.status)
print(result.outputs)
EOF
```

Voir aussi `tests/integration/test_vector_run.py` pour un exemple complet avec `httpx.MockTransport`.

### Sondes du jalon 3-I (`from: "text"`)

Jouées sur des sources réelles, et **des deux côtés** — le moteur Python puis le moteur embarqué
sous Node —, parce que la seule question qui compte ici est « les deux décodent-ils pareil ».

| Sonde | Résultat |
|-------|----------|
| `examples/vector/ical-planning-text` (export ADE anonyme, `text/calendar;charset=UTF-8`) | `success` des deux côtés, `caracteres: 21461` **identiques**, `accents: true` — 21 592 octets pour 21 461 caractères : les accents sont bien passés par le décodeur, pas à côté |
| `examples/mobile/ical-large-body-probe` (jours fériés français, ~80 Ko) | `success` des deux côtés, `caracteres: 80712` identiques, `Noël` présent |
| **Conçue pour échouer** : `examples/mobile/ical-error-page-probe` — le même export **sans paramètres**, qui répond 500 avec une page HTML déclarée `ISO-8859-1` | `failed` au step `shape`, message `ICAL_INVALID`, step `DIAGNOSTIC` jamais atteint, **et le même échec mot pour mot sur les deux moteurs**. Sans la garde de forme, ce run aurait « réussi » en rendant un calendrier vide |

Les trois ont ensuite été rejouées **sur un iPhone** (le pont d'octets de React Native n'existe nulle
part ailleurs) : mêmes valeurs au caractère près, même échec au même step. Détail :
[docs/embedded.md](../embedded.md#sur-appareil).

Une aspérité relevée au passage, antérieure au jalon et laissée telle quelle : l'action `assert`
signale son échec via `StatusAssertionError`, donc le message porte un préfixe `Expected HTTP 1,
got 0 — <assert>` avant la vraie raison, et la façade mobile classe l'échec en famille `rejected`
avec `retryable: true` — juste sur le fond (la source a répondu, mais pas comme le Blueprint
l'exigeait), discutable sur l'invitation à réessayer quand c'est une garde de forme qui a mordu.
C'est identique sur les deux moteurs, et le changer toucherait le contrat d'erreur d'une action qui
n'est pas le sujet de ce jalon.
