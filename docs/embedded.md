# Le moteur embarqué

Aetherius a **deux moteurs**. Celui de `src/aetherius/`, en Python, exécute les quatre Acts et tout
ce qui demande une machine. Celui de [`sdks/engine/`](../sdks/engine), en TypeScript, rejoue les
**mêmes Blueprints** directement sur l'appareil de l'utilisateur — pour les applications mobiles, où
héberger un daemon reviendrait à faire sortir toutes les requêtes d'une seule IP et à faire transiter
les identifiants de chacun par une machine tierce.

Le cadrage, les décisions d'architecture et les sept jalons sont dans
[docs/phase-3/](phase-3/README.md). Ce document décrit ce qui est **livré** : ce qui existe, comment
ça marche, et où sont les limites.

> **État.** Les Blueprints `act: "vector"` **et** `act: "continuum"` s'exécutent réellement — le
> premier depuis le jalon 3-C (runtime asynchrone, flux, garde `when`, requêtes HTTP sur `fetch`),
> le second depuis le jalon 3-D (WebView cachée, agent JavaScript injecté, RPC corrélée,
> auto-attente, extraction DOM, sessions). Depuis le jalon 3-E, une application les consomme par une
> **façade** : secrets par le trousseau de l'OS, `confirm` en modal natif, annulation, et un modèle
> d'erreur exploitable — voir [La surface applicative](#la-surface-applicative). Depuis le jalon
> 3-F, ces Blueprints ne sont plus figés dans le binaire : un **registre** les résout entre un socle
> embarqué et une surcouche distante vérifiée, donc un site qui change se répare sans republier —
> voir [La livraison des Blueprints](#la-livraison-des-blueprints).

## Les trois paquets

| Paquet | Rôle |
|--------|------|
| [`@aetherius/engine`](../sdks/engine) | Le moteur, **neutre plateforme** : il ne connaît ni React Native, ni Node. Modèle de Blueprint, validation, erreurs, événements, runtime et l'Act I sur `fetch`. |
| [`@aetherius/react-native`](../sdks/react-native) | Ce que le précédent ne peut pas porter sans dépendre d'une plateforme : l'Act II sur WebView, le trousseau, le modal de `confirm`, et la façade `Aetherius`. C'est la **seule porte d'entrée** d'une application : le modèle d'erreur du moteur y est ré-exporté. |
| [`@aetherius/client`](../sdks/client) | **Rien à voir** : il *pilote* le daemon Python à distance. Piloter un moteur et *être* un moteur sont deux métiers. |

Chacun sort de `private` avec sa première capacité utilisateur : `@aetherius/engine` au jalon 3-C,
`@aetherius/react-native` au jalon 3-D.

## Deux moteurs, un contrat

Le risque d'une seconde implémentation n'est pas qu'elle soit fausse : c'est qu'elle dérive
lentement, et qu'on ne s'en aperçoive qu'en production. Trois gardes le rendent difficile.

### 1. Le contrat généré `contracts/actions.json`

Le registre d'actions Python (`src/aetherius/core/actions/`) est la source unique du vocabulaire.
Le catalogue du builder en était la seule projection ; `contracts/actions.json` en est une seconde,
lisible par n'importe quel langage : pour chaque action son résumé et ses paramètres, plus la table
`ACT_CAPABILITIES`, la liste des actions de flux et **la carte des champs qui portent des steps
imbriqués** (`if` → `then`/`else`, `repeat`/`for_each` → `steps`) — sans quoi les deux moteurs
marcheraient sur deux arbres différents.

```bash
make contracts     # regenere le fichier depuis le registre vivant
```

Le fichier est **généré, jamais édité à la main**. `tests/contracts/test_actions_contract.py`
échoue si le fichier committé s'écarte du registre — même motif que la garde du schéma. Les actions
apportées par un **plugin** en sont volontairement absentes : elles dépendent de ce qui est installé
sur la machine, un contrat ne le peut pas.

Le moteur TypeScript ne lit pas le dépôt (un téléphone n'a pas de checkout) : le contrat est
**inliné dans le paquet** à la compilation, avec le validateur de schéma.

### 2. La table des capacités embarquées

Déclarée par le moteur lui-même, dans
[`capabilities.ts`](../sdks/engine/src/blueprint/capabilities.ts), parce que c'est une affirmation
sur *cette plateforme*, pas une projection du registre. L'invariant, gardé par un test : c'est un
**sous-ensemble strict** d'`ACT_CAPABILITIES`. Un Blueprint accepté par le moteur embarqué est
toujours accepté par le moteur Python ; l'inverse est faux, et c'est voulu.

| Périmètre | Détail |
|-----------|--------|
| Acts | `vector`, `continuum`. Oracle et Phantom restent au moteur Python. |
| Vector | `http.request`, `extract`, `set`, `assert`, `emit`, `wait`, `if`, `repeat`, `for_each`, `confirm`. |
| Continuum | le jeu Vector + `navigate`, `back`, `forward`, `reload`, `click`, `fill`, `type`, `press`, `select`, `hover`, `scroll`, `evaluate`, `wait_for`. |
| Hors périmètre | `upload`, `drag`, `screenshot` (pas d'équivalent honnête en WebView), `notify` (l'application a déjà ses notifications), `read` et les Acts cognitifs. |

### 3. Le corpus de conformance

Le vrai livrable du jalon. Un répertoire de cas — un Blueprint, et ce que **chaque** moteur doit en
faire — rejoué par les deux. Il ne teste pas du code : il fige ce que « le même Blueprint » veut
dire, y compris là où les deux moteurs divergent légitimement.

```bash
make conformance
```

Format des cas et procédure d'ajout : [`conformance/README.md`](../conformance/README.md).

## Charger et valider

La validation se fait **en deux temps**, comme en Python — parce qu'un message qui dit *à quel
niveau* le document est invalide vaut mieux qu'un message qui dit qu'il l'est.

```ts
import { parseBlueprint, validateForAct } from "@aetherius/engine";

const blueprint = parseBlueprint(text, "planning.blueprint.json"); // structurel
validateForAct(blueprint);                                        // semantique
```

| Étape | Erreur | Ce qu'elle dit |
|-------|--------|----------------|
| Parsing | `BlueprintLoadError` | Ce ne sont pas des octets de Blueprint. |
| Schéma + règles de modèle | `BlueprintSchemaError` | Le document ne respecte pas `contracts/blueprint.schema.json`. |
| Sémantique par act | `BlueprintValidationError` | Le document est bien formé mais ne peut pas tourner ainsi. |

### Le schéma est précompilé, pas interprété

Le moteur JS mobile (Hermes) ne supporte ni `eval` ni `new Function`, et un validateur JSON Schema
généraliste construit ses fonctions de validation exactement comme ça. La compilation devient donc
une **étape de build** : [`scripts/compile-schema.mjs`](../sdks/engine/scripts/compile-schema.mjs)
fait produire à Ajv du code autonome, et ce qui est livré est du JavaScript ordinaire. C'est aussi
la bonne posture pour un moteur qui exécutera demain de la donnée téléchargée (jalon 3-F).

Le script émet trois modules sous `src/generated/` (git-ignorés, régénérés par `npm run build`) :
le validateur, le contrat d'actions inliné, et les empreintes SHA-256 des deux contrats. Un test
compare ces empreintes aux fichiers de `contracts/` : un artefact périmé se voit.

Deux détails de mise en œuvre méritent d'être connus avant qu'on les « corrige » par erreur :

- **Ajv est une dépendance de build, pas d'exécution.** Sa sortie autonome référence un helper de
  son runtime (`ucs2length`) par un `require()` — inutilisable dans un module ES, et une raison de
  traîner Ajv dans l'application pour quinze lignes. Le script l'**inline**, et **échoue
  bruyamment** si un helper inconnu apparaît, plutôt que d'émettre un module qui casserait sur
  l'appareil. Si le schéma gagne un jour un mot-clé qui en demande un autre, le build le dira.
- **`strictRequired` est désactivé** à la compilation : `anyOf: [{required: [steps]}, {required:
  [goal]}]` est un idiome légitime que le mode strict d'Ajv refuserait. Toutes les autres
  vérifications strictes restent actives.

### La règle que le schéma ne peut pas porter

`contracts/blueprint.schema.json` exige `steps` **ou** `goal` par un `anyOf` — qu'un `steps: []`
satisfait, la clé étant présente. Côté Python c'est le modèle pydantic qui la refuse. Le moteur
embarqué n'a pas de pydantic : la règle est reproduite explicitement dans
[`loader.ts`](../sdks/engine/src/blueprint/loader.ts), et c'est le cas de conformance
`model-empty-steps` qui garantit que les deux restent d'accord.

### Trois refus, trois messages

Le point de conception le plus important du socle. Une capacité absente peut l'être pour trois
raisons, et les confondre enverrait l'auteur corriger ce qui n'est pas cassé.

```
act='vector', action 'click'
  → action 'click' is not supported by act='vector'
    (requires act='continuum' or higher — set it on the blueprint or on this step)

act='continuum', action 'upload'
  → action 'upload' is supported by act='continuum' but not by the embedded engine
    (a WebView exposes no file chooser): run this Blueprint on the Python engine

act='oracle'
  → Act 'oracle' is not supported by the embedded engine (the Blueprint declares it):
    Acts III/IV stay on the Python engine. Embedded acts: vector, continuum.
```

Le premier est un problème d'`act` et se corrige dans le Blueprint. Le deuxième dit que le
Blueprint est **juste** : il appartient simplement à l'autre moteur. Le troisième vise l'act, pas
l'action — c'est ce qui évite de partir chercher quelle action pose problème.

L'act d'origine d'une action (« requires act='continuum' ») est **dérivé** de la table des
capacités du contrat — le premier act de la chaîne d'escalade qui la porte — et non redéclaré :
`_CAPABILITY_ORIGIN`, côté Python, n'a pas de jumeau à maintenir.

### La marche dans les branches

Comme en Python, la validation descend dans `then`/`else`/`steps`, un step peut escalader l'act
(`step.act`, composition multi-Act) et ses steps imbriqués en héritent. Un refus dans une branche
nomme son chemin :

```
Step 'shot': action 'screenshot' is not supported by act='vector' (…) (at steps[1].then[1]).
```

## Expressions et extraction

Un Blueprint repose sur deux mini-langages : le **rendu d'expressions** `{{ }}` et l'**extraction
déclarative**. Le moteur Python les tient de Jinja2, `jsonpath-ng` et `parsel`. Aucun des trois n'est
transposable tel quel : le moteur JS mobile refuse `eval` et `new Function`, et toute bibliothèque
compatible Jinja2 compile ses templates exactement comme ça.

Le moteur embarqué porte donc son propre **analyseur lexical + parseur à précédence +
interpréteur d'AST** ([`expr/`](../sdks/engine/src/expr)) — **une seule brique** au service de
**trois** usages : le rendu ([`template.ts`](../sdks/engine/src/template.ts)), la vérité `isTruthy`
de `when`/`assert`, et le prédicat `where` de l'extraction. Les dupliquer serait la garantie qu'ils
divergeront. Bénéfice collatéral, qui compte pour le jalon 3-F où les Blueprints arriveront du
réseau : l'interpréteur n'a **rien** à offrir à un attaquant — ni fonctions natives, ni prototypes,
ni globales —, donc aucune liste blanche à maintenir.

### Le sous-ensemble d'expressions

| Catégorie | Supporté |
|-----------|----------|
| Accès | `a.b`, `a['b']`, `a[0]`, index négatif |
| Littéraux | chaînes, nombres, `true`/`True`, `false`/`False`, `none`/`None`, listes, objets |
| Opérateurs | `+ - * / // % ~`, `== != < <= > >=`, `in`, `not in`, `is`, `is not`, `and`, `or`, `not` |
| Conditionnel | `a if cond else b` (paresseux), test `is defined` / `is not defined` |
| Filtres | `add_days`, `sub_days`, `format_date`, `default`, `first`, `float`, `int`, `join`, `last`, `length`, `lower`, `string`, `trim`, `upper` |

Trois points de sémantique méritent d'être connus avant qu'on les « corrige » par erreur :

- **La règle de l'expression nue.** Quand une chaîne est *exactement* une expression
  (`"{{ steps.week.events }}"`), le moteur rend l'**objet brut** : une liste reste une liste. Dès
  qu'il y a du texte autour, le résultat est une chaîne. Ne pas reproduire cette distinction ne
  casserait rien bruyamment — tous les `outputs` qui rendent une collection continueraient de
  réussir, avec une chaîne à la place des données.
- **`StrictUndefined` est un choix.** Une variable absente **lève** ; elle ne rend pas une chaîne
  vide. C'est ce qui transforme une faute de frappe dans un Blueprint en erreur immédiate plutôt
  qu'en donnée manquante à l'autre bout de la chaîne. Le marqueur reste toutefois *paresseux* :
  le produire est silencieux, l'utiliser lève — sans quoi `is defined` et la branche `else` d'un
  ternaire seraient impossibles.
- **Deux véracités cohabitent.** *À l'intérieur* d'une expression, `and`/`or`/`not` et le ternaire
  utilisent la véracité **native de Python** (chaîne vide, liste vide, `0`, `None` sont faux) —
  c'est ce que Jinja évalue. *Autour*, `when` et `assert` appliquent la règle d'Aetherius
  (`isTruthy`) : la valeur est convertie en chaîne, minusculée, comparée à `true`/`1`/`yes`. Donc
  le nombre `2` est vrai dans une expression et **faux** dans un `when`. La bizarrerie est
  volontaire et figée par un cas de conformance obligatoire : un portage « intelligent » vers la
  véracité de JavaScript ferait diverger `when` sur des cas réels.

Les valeurs interpolées dans une chaîne sont sérialisées comme `str()` le fait côté Python :
`True`, `None`, `[1, 2]`, `{'a': 1}`. Un booléen déposé dans un corps de formulaire part identique
des deux côtés.

### Le sous-ensemble JSONPath

`$`, `.nom`, `.'nom cité'` / `."nom cité"` / `['nom']`, `.*` / `[*]`, `[n]` (indices négatifs
compris), tranches `[a:b:c]`, descente récursive **par nom** `..nom`, et les chemins relatifs
employés par `fields`. Une extraction rend **toujours une liste** de correspondances, même quand le
chemin n'en trouve qu'une — c'est pour cela que les Blueprints livrés écrivent `| first`.

`..*` en est volontairement absent : c'est la seule construction où `jsonpath-ng` ne fait pas ce
qu'on croit — il ne descend **pas** dans les éléments d'une liste, donc `$..*` sur `{"c": [2, 3]}`
rend la liste sans ses items. Plutôt que de reproduire cette forme au juger pour une construction
qu'aucun Blueprint n'utilise, le moteur la refuse par son nom.

Deux comportements contre-intuitifs sont en revanche **reproduits**, parce qu'ils décident du
résultat sur des documents réels : `[*]` et `.*` ne sont pas le même opérateur (`[*]` est une
tranche complète, `.*` un accès de champ — donc `$[*]` sur un objet rend l'objet lui-même, quand
`$.*` rend ses valeurs, et `$.*` sur une liste ne rend rien) ; et un opérateur de liste appliqué à
un non-liste traite celui-ci comme une liste d'un élément, `null` mis à part. Un indice numérique,
lui, peut **lever** — la vérification `len(valeur) > indice` précède l'indexation.

### L'extraction HTML, sans DOM

Vector extrait d'une réponse `fetch` : il n'y a pas de DOM à interroger, donc le moteur parse
lui-même. Plutôt qu'un parseur maison, il s'appuie sur la pile `htmlparser2` / `domutils` /
`css-select` — du JavaScript pur, **sans `eval` ni `new Function`**, ce qui la rend utilisable sous
Hermes. Ce sont les premières dépendances d'exécution du paquet, et un test
([`no-dynamic-code.test.js`](../sdks/engine/test/no-dynamic-code.test.js)) rescanne à chaque
exécution le closure résolu depuis le lockfile : une montée de version qui introduirait de la
génération de code se verrait au build, pas sur l'appareil.

Deux comportements de `parsel` sont reproduits parce que des Blueprints en dépendent, et qu'aucun
des deux n'est du CSS standard :

- `::text` sélectionne les nœuds texte **enfants directs** de l'élément, chacun un résultat séparé —
  `<h1>Bonjour <b>x</b> monde</h1>::text` rend deux chaînes, pas une seule concaténée ;
- sans pseudo-élément ni `attr`, une correspondance rend son **HTML sérialisé** (ce que
  `Selector.getall()` renvoie). `::attr(nom)` et le champ `attr` lisent un attribut ; un attribut
  absent rend la chaîne vide, et `multiple: false` rend la première valeur ou `null`.

### Le corps en texte, et son décodage

`from: "text"` (jalon 3-I) rend le corps décodé, tel quel — la forme qui rend atteignables les
formats à lignes (iCalendar, CSV, `text/plain`). Le dialecte n'a rien à configurer ; ce qui mérite
d'être connu, c'est **d'où viennent les octets** et **qui décide de l'encodage**.

**Le moteur ne se repose pas sur la plateforme pour décoder.** `TextDecoder` est **absent de React
Native** et complet (ICU) sous Node : s'en servir ferait tomber d'accord la CI et diverger le
téléphone — précisément le défaut que le corpus existe pour attraper. Le paquet porte donc ses
décodeurs ([`extraction/charset.ts`](../sdks/engine/src/extraction/charset.ts)) : un décodeur UTF-8
écrit à la main (l'algorithme WHATWG, qui rend un `U+FFFD` par *sous-partie maximale* — soit
exactement ce que fait `errors="replace"` de CPython) et une table mono-octet. Toujours **aucune
dépendance ajoutée**, et le même argument que le base64 de `BasicAuth` : les trois solutions de
plateforme marcheraient *la plupart du temps*, ce qui est la pire propriété possible.

La **table d'étiquettes est bornée et partagée** avec le moteur Python — latin-1 (strict, pas
l'alias WHATWG vers cp1252), cp1252, et UTF-8 pour tout le reste, `us-ascii` compris. Élargir se
fait des deux côtés à la fois ; laisser un moteur connaître plus de codecs que l'autre aurait été
une divergence à retardement. Détail des règles :
[docs/acts/vector.md](acts/vector.md#le-décodage-suit-len-tête).

**Les octets ne sont lus que quand ils servent.** Un corps ne se lit qu'une fois, donc le driver
décide **avant** d'envoyer la requête : il scanne le bloc `extract` — statiquement, puisque les
specs ne sont jamais rendues, le même argument qui autorise `portability.ts` à refuser XPath à la
validation — et n'appelle `response.arrayBuffer()` que si un `from: "text"` est déclaré. Deux
conséquences voulues :

- une requête sans extraction texte emprunte **exactement** le chemin d'avant (`response.text()`), et
  ne paie pas, sur l'appareil, le trajet blob → base64 → pont natif par lequel React Native fait
  passer des octets ;
- `body` reste **toujours** la lecture UTF-8, y compris en mode octets : `expect`, l'extraction JSON
  et l'extraction HTML voient la même chaîne dans les deux modes. Seul le dialecte texte relit les
  octets à travers le charset déclaré.

Un hôte dont la réponse n'expose pas `arrayBuffer()` obtient une **`ActionError` qui le nomme**, pas
un décodage UTF-8 fait dans son dos — et surtout pas une `NetworkError`, qui enverrait quelqu'un
déboguer sa connexion. Le `fetch` de React Native, lui, l'expose (réponse en blob,
`FileReader.readAsArrayBuffer`), ce que la campagne sur appareil vérifie plutôt que de le supposer.

### Le prédicat `where`

Côté Python, c'est du code exécuté derrière une liste blanche d'AST. Côté embarqué la sûreté est
acquise par construction, mais la **grammaire est restreinte au même jeu** — comparaisons, logique
booléenne, `not`, noms, attributs, littéraux — pour que les deux moteurs refusent les mêmes
prédicats : appels, filtres, indexation, ternaires, littéraux de liste et attributs `__` sont
rejetés des deux côtés, avant toute évaluation.

Une sémantique surprend et n'est pas un bug : une comparaison sur un **champ absent lève**, elle ne
filtre pas l'élément en silence (côté Python l'item est enveloppé dans un `SimpleNamespace`, donc
c'est une `AttributeError`).

### Ce qui échoue, et quand

| Limite | Quand | Pourquoi ce moment-là |
|--------|-------|-----------------------|
| `selector_type: "xpath"` dans un `extract` | **à la validation** (`BlueprintValidationError`) | `selector_type` est une enum du schéma : le refus est statique, sans risque de faux positif. Un Blueprint qui ne peut pas tourner doit le dire **avant** de démarrer, jamais au milieu d'un run. |
| `from: "text"` avec un `path` (ou `where`, `fields`, `selector`, `attr`, `multiple`) | **à la validation** (`BlueprintValidationError`) | Règle du **contrat**, pas de ce moteur : les deux refusent, avec le même motif. Un texte se rend entier ; laisser passer la clé ferait croire à un filtrage qui n'a pas lieu. |
| Réponse dont l'hôte ne sait pas rendre les octets, avec un `from: "text"` | à l'exécution (`ActionError`) | Dépend de l'objet `Response` d'un `fetch` que l'application peut avoir remplacé : rien à vérifier statiquement. Le message nomme `arrayBuffer()`. |
| JSONPath hors sous-ensemble (`[?…]`, unions, `` `len` ``) | à l'extraction (`ExtractionError`) | Un parseur plus strict que `jsonpath-ng` refuserait à la validation des Blueprints corrects. Un faux refus est pire qu'un échec propre. |
| Filtre ou test inconnu | au rendu (`TemplateError`, le message nomme le jeu supporté) | |
| Date hors `YYYY-MM-DD` | au rendu (`TemplateError`) | |

XPath est la seule capacité d'extraction absente : hors navigateur, il demande un moteur à lui seul,
et l'exemple livré `books-restock-notify` utilise `normalize-space(//p[contains(@class, …)])`, une
expression XPath 1.0 complète avec fonctions. Reproduire lxml serait disproportionné face à l'usage.

## Exécuter un Blueprint

```ts
import { RunEngine, parseBlueprint } from "@aetherius/engine";

const blueprint = parseBlueprint(text, "planning.blueprint.json");
const result = await new RunEngine().run(blueprint, {
  inputs: { group: "TP-A1" },
  secrets: { cas_pass: "…" },
  sinks: [{ onEvent: (event) => console.log(event.type, event.step_id) }],
});
```

Le pipeline est celui du moteur Python (`core/runtime/`), avec `await` devant : valider, résoudre
les entrées et les secrets, lier le driver racine, dérouler les steps, démonter, rendre les
`outputs`, retourner un `Result`. Ce qui est **observable** — l'ordre des steps, les événements
émis, la forme du `Result` — est le contrat, et le corpus de conformance le compare cas par cas.

Quelques points de sémantique qui décident du résultat :

- **`when` saute le step** : statut `skipped`, événement `step_skipped` à la place de la paire
  `step_started`/`step_finished`, et l'événement publie l'expression **brute** — jamais sa valeur
  rendue, qui peut dériver d'un secret.
- **Les steps imbriqués portent leur chemin** dans les événements et les `StepResult`
  (`walk.each[1].announce`), mais publient leurs sorties sous leur **identifiant nu**
  (`{{ steps.announce.… }}`). L'asymétrie vient du moteur Python et se lit dans un cas de
  conformance plutôt que dans deux implémentations.
- **`repeat` et `for_each` sont des boucles séquentielles `await`.** La tentation de les
  paralléliser « puisqu'on est en asynchrone » est écartée : l'ordre est observable dans le flux
  d'événements, et des itérations qui partagent une session cesseraient d'être reproductibles.
- **Deux chemins d'échec.** Une `AetheriusError` est un échec de run propre, tracé dans le `Result`
  (`status: "failed"`, message dans `error`, aucun `outputs` publié) ; toute autre exception est
  enveloppée dans une `RunError` et **relancée** — un bug du moteur ne doit pas se déguiser en run
  qui « n'a pas marché ».
- **Les `outputs` sont rendus après coup, hors du rattrapage d'erreur** : une `TemplateError` dans
  un `outputs` remonte à l'appelant au lieu d'être maquillée en run échoué. C'est aussi le
  comportement Python.

Le driver d'un act est résolu par un **registre** (`registerDriver`), là où le moteur Python nomme
ses quatre drivers dans un `match`. La raison est la frontière des paquets : le driver Continuum a
besoin d'une WebView, il vit donc dans `@aetherius/react-native` et **s'enregistre à l'import**. Une
application qui n'importe pas ce paquet voit son Blueprint `continuum` accepté à la validation et
refusé au démarrage par un message qui nomme le paquet à importer — pas par un `undefined`.

### Le run non surveillé

Appeler `RunEngine` directement, sans passerelle d'approbation, donne un run **non surveillé** :
`confirm` applique sa politique `on_timeout` immédiatement, et elle **refuse par défaut**. C'est
exactement le chemin que prend le moteur Python pour un run de bibliothèque, et c'est la posture
sûre — un run que personne ne regarde ne fait rien de sensible. `approve` laisse passer, `fail:CODE`
échoue avec son code.

La surface humaine — un modal natif — arrive avec la façade
([ci-dessous](#confirm-en-modal-natif)) ; ce paragraphe décrit ce qu'on obtient sans elle.

## Act I — Vector sur `fetch`

Un seul besoin de plateforme : `fetch`. C'est ce qui rend l'Act I exécutable partout — un téléphone,
Node, un test qui injecte le sien (`RunOptions.fetch`).

```
http.request → params/form/json encodes → auth → cookies → fetch (timeout, reprises) → expect → extract
```

### L'encodage est le risque de divergence silencieuse

Un corps de formulaire qui diffère d'un caractère ne lève rien : la requête part, le serveur répond
autre chose, et le Blueprint a l'air de marcher partout sauf là où ça compte. Les encodeurs
reproduisent donc httpx à l'octet près, et un cas de conformance les compare sur une route qui
**renvoie la requête reçue** — ce sont les deux moteurs qui sont comparés, pas le harnais.

| Point | Règle reproduite |
|-------|------------------|
| Primitives d'un `form`/`params` | `httpx._utils.primitive_value_to_str` : `true`/`false` pour les booléens, chaîne vide pour `None`, `str()` sinon. **Ce n'est pas** la règle du moteur de templates (`True`/`None`) — les deux cohabitent des deux côtés. |
| Échappement | `quote_plus` : espace → `+`, `~` conservé, `*` → `%2A`. `URLSearchParams` fait l'inverse sur ces deux caractères : il n'est pas utilisé. |
| Valeur de liste | La clé est répétée (`ids=1&ids=2`). |
| `params` | **Remplace** la query de l'URL, ne la fusionne pas ; le fragment survit. Contre-intuitif, et c'est httpx. |
| Corps `json` | Séparateurs compacts, non-ASCII conservé — soit exactement `JSON.stringify`. |
| `Content-Type` | Posé par défaut selon le corps, mais l'en-tête explicite du Blueprint **gagne** (`setdefault`, insensible à la casse). |
| `json` + `form` | Refusés ensemble, **après rendu** : un `json` qui rend `null` vaut absent et ne provoque pas le conflit. |

### Reprises et délais

`retries.max: 0` désactive toute reprise ; sinon le client fait `max + 1` tentatives et attend
`none` = 0 s, `linear` = 1 s, `exponential` = `2^(n-1)` borné à [1, 30] s — la formule de tenacity,
**sans jitter**. En ajouter « parce que c'est mieux » ferait rejouer le même Blueprint sur deux
horaires différents selon le moteur.

Seuls les échecs de **transport** et les **délais dépassés** sont rejoués, jamais un code de statut :
un 500 est une réponse, et c'est `expect` qui décide ce qu'on en fait. Des reprises épuisées
remontent la **dernière** erreur (`TimeoutError` ou `NetworkError`), pas une erreur d'enveloppe —
c'est ce que fait le moteur Python (`reraise=True`), et l'appelant n'a pas à savoir combien de
tentatives ont eu lieu.

`fetch` n'a pas de délai propre : il est construit avec `AbortController`, et la fenêtre couvre la
lecture du corps, comme celle de httpx. Un hôte sans `AbortController` n'a **pas** de délai plutôt
qu'un délai qui ne se déclenche jamais.

### Cookies, redirections et sessions

C'est la contrainte la plus structurante du jalon, et elle tient à trois faits de plateforme :

1. **`Set-Cookie` n'est en général pas lisible depuis JavaScript.** Un navigateur l'interdit ; une
   WebView React Native ne le promet pas. `fetch` sous Node l'expose, lui, via
   `Headers.getSetCookie()`.
2. **Le magasin de cookies appartient à la plateforme.** Sur appareil, l'OS garde les cookies pour
   tout le processus et les attache lui-même : une session survit sans l'aide du moteur — et ne peut
   pas être isolée par run.
3. **Node n'a aucun magasin.** Personne n'attache rien.

**Stratégie retenue : un jar opportuniste.** Le client capture ce que l'hôte laisse lire, et ne
renvoie que ce qu'il a capturé lui-même. Sur appareil il reste vide et la plateforme fait le travail
— donc aucun cookie n'est envoyé deux fois ; sous Node il **est** la session, ce qui rend un login
de formulaire testable en CI et pas seulement sur le téléphone de quelqu'un.

Ce qui en découle, et qu'il faut connaître :

- **Le jar ne scope ni par domaine, ni par chemin, ni par expiration.** Il tient les cookies d'un run
  pour ce run. Un Blueprint qui parle à deux hôtes sans rapport dans le même run enverrait les
  cookies du premier au second. Acceptable tant qu'Act I veut dire « une API », et une bonne raison
  de ne pas promouvoir ce jar en magasin généraliste.
- **`Set-Cookie` n'est lu que par l'accesseur structuré.** `headers.get("set-cookie")` renvoie
  plusieurs cookies joints par des virgules, et un attribut `Expires` en contient une aussi : les
  découper est une devinette, et se tromper là veut dire envoyer la session de quelqu'un d'autre.
- **Les redirections sont suivies d'office** (`redirect: "follow"` ; `manual` n'existe pas dans un
  `fetch` React Native). Les réponses intermédiaires sont invisibles : un enchaînement de tickets
  fonctionne, mais **en aveugle** — on constate le résultat, on ne pilote pas les étapes.
- **`options.session` n'a pas d'effet côté Vector**, exactement comme côté Python. Sur appareil,
  l'isolation d'un run vis-à-vis du magasin de la plateforme n'est pas offerte ; elle sera un choix
  explicite de la WebView au jalon 3-D.

### Authentification

Les cinq stratégies du moteur Python sont là — `NoAuth`, `BearerAuth`, `BasicAuth`, `CookieAuth`,
`CasFormLogin` —, y compris le fait que ce soit une surface **programmatique** : aucun champ de
Blueprint ne sélectionne une stratégie, ni ici ni là-bas (voir
[docs/acts/vector.md](acts/vector.md#authentification)). On construit un `VectorClient` avec celle
qu'on veut.

Deux sont touchées par la plateforme. `CookieAuth` ne peut pas écrire le magasin de l'OS : elle
amorce le jar du moteur, et les cookies voyagent dans un en-tête `Cookie` explicite. `CasFormLogin`
lit les champs cachés de la page de login avec la **pile d'extraction déjà là** (aucun parseur
supplémentaire), puis poste les identifiants ; la suite se joue en aveugle, redirections comprises.
Une page de login qui répond en erreur lève une erreur **typée**, là où le moteur Python laisse
échapper une erreur httpx enveloppée en `RunError`.

### Budget de dépendances

**Aucune dépendance d'exécution ajoutée par ce jalon.** Chaque paquet alourdit le binaire d'une
application mobile, donc :

- `fetch`, `AbortController`, `setTimeout` sont des globales de l'hôte, lues **à travers
  `globalThis`** — une référence au niveau module ferait échouer le *chargement* du paquet sur un
  hôte sans `fetch`, au lieu d'échouer au seul step qui en a besoin, avec un message qui le dit ;
- le **base64** de `BasicAuth` est écrit à la main (une trentaine de lignes) : `btoa` n'est pas
  garanti sous Hermes, `Buffer` est un module Node, `TextEncoder` est optionnel en React Native.
  Les trois marcheraient *la plupart du temps*, ce qui est la pire propriété possible pour un
  encodeur d'identifiants ;
- les types de `fetch` sont **déclarés structurellement** (`src/http.ts`) plutôt qu'empruntés à
  `lib: ["DOM"]` ou à `@types/node`. C'est aussi ce qui rend le client injectable en test.

## Act II — Continuum sur WebView

C'est le jalon qui remplace les **WebView cachées écrites à la main** : là où une application pilote
aujourd'hui un portail avec des gabarits de chaîne JavaScript — non typés, invérifiables par le
compilateur, avec des sélecteurs positionnels au milieu du code applicatif —, elle décrit un
Blueprint.

```tsx
import { RunEngine, parseBlueprint } from "@aetherius/engine";
import { AetheriusWebView } from "@aetherius/react-native"; // l'import enregistre le driver

// Une fois, haut dans l'arbre : la WebView vit avec l'application, pas avec un run.
<AetheriusWebView />

const result = await new RunEngine().run(parseBlueprint(text, "scolarite.json"), {
  secrets: { cas_user, cas_pass },
});
```

Le paquet ne connaît qu'une chose de React Native : le composant. Tout le reste — driver, RPC,
agent — est piloté à travers l'interface [`WebViewHost`](../sdks/react-native/src/webview/host.ts),
ce qui rend l'Act II testable hors simulateur : le corpus de conformance le rejoue contre un hôte
adossé à jsdom.

`react`, `react-native` et `react-native-webview` sont des **peer dependencies** : le paquet déclare
structurellement la surface qu'il utilise (`webview/react-native-webview.d.ts`) au lieu d'emprunter
leurs types, et n'embarque aucun runtime React. Le corollaire compte pour l'application : un paquet
lié depuis un workspace résout ses peers depuis le `node_modules` du workspace, où npm les installe
quoi qu'en dise `peerDependenciesMeta.optional` — deux copies de React, deux dispatchers de hooks, et
un `Invalid hook call` qui accuse le composant. La configuration Metro de l'application de
démonstration **reroote** la résolution de ces paquets sur l'application ; c'est la recette
habituelle des monorepos React Native, et elle est écrite dans
[`examples/mobile/demo/metro.config.js`](../examples/mobile/demo/metro.config.js).

### Le protocole de l'agent injecté

Le vrai livrable du jalon n'est pas « du JavaScript qu'on injecte », c'est un **protocole** :
un vocabulaire d'opérations fermé, des paramètres **encodés en JSON**, des réponses **corrélées** par
identifiant, des délais tenus par l'appelant.

```
app  -> page : window.__aetherius.handle("<un littéral JSON>");
page -> app  : { aeth: 1, gen, id, ok: true,  value }
               { aeth: 1, gen, id, ok: false, error: { name, message, code? } }
               { aeth: 1, gen, id, seq, total, part }     réponse découpée
               { aeth: 1, gen, ready: true, url }         agent présent sur un document neuf
```

Deux règles portent l'ensemble, et aucune n'est négociable :

1. **Aucun paramètre n'est jamais interpolé dans la source d'un script.** Les paramètres traversent
   en JSON, que la page **parse** ; elle ne **compile** jamais une valeur. C'est ce qui rend
   impossible *par construction* la classe de bug la plus courante des WebView artisanales — un mot
   de passe contenant une apostrophe qui casse le script, ou pire. Un test le prouve avec une valeur
   contenant `'`, `"`, `` ` ``, `\`, `</script><script>…` et un saut de ligne : la valeur arrive
   intacte, et la source injectée reste un **gabarit constant** dont la seule partie variable est un
   littéral JSON bien formé.
2. **Chaque réponse porte la génération du document dont elle vient.** Une navigation détruit le
   contexte de la page ; une réponse qui arrive après n'appartient plus à personne et doit être
   **jetée**, jamais remise à l'appel qui se trouve attendre. Déduire l'état « page prête » d'un
   simple événement de chargement produit des courses non reproductibles.

**L'unique exception, et elle a sa propre méthode** pour qu'on ne la généralise pas par accident :
`evaluate`, dont le `script` *est* du code par contrat
([`evaluate.ts`](../sdks/react-native/src/webview/evaluate.ts)). Son `arg`, lui, traverse en JSON
comme tout le reste. La règle fonction-ou-expression est celle de Playwright : `"() => …"` est
appelée avec l'`arg`, `"document.title"` est évaluée ; `undefined` devient `null`, comme
`page.evaluate` rend `None` côté Python.

L'agent est écrit en modules TypeScript ([`webview/agent/`](../sdks/react-native/src/webview/agent))
et **assemblé au build** en une chaîne unique injectable (esbuild, dépendance de *build* — même
posture qu'Ajv pour le schéma). Le bundle porte l'empreinte de ses sources : un artefact périmé se
voit en test, au lieu de produire des pannes qui ressemblent à un problème de navigateur.

### L'auto-attente, écrite une fois

Un pilote de navigateur mature attend qu'un élément existe, soit visible et soit stable avant
d'agir. Une WebView n'offre rien de tel — d'où, dans les implémentations artisanales, le même motif
recopié une fois par script, avec son délai en dur. Ici il est écrit **une fois**
([`waiting.ts`](../sdks/react-native/src/webview/agent/waiting.ts)) :

> tenter immédiatement ; sinon observer le document jusqu'à l'échéance ; à l'échéance, produire un
> échec **explicite** plutôt que rester bloqué.

L'observation est un `MutationObserver` **et** un sondage (100 ms), et le second n'est pas une
ceinture de sécurité : un `MutationObserver` ne se déclenche pas quand un élément devient visible
parce qu'une feuille de style a fini de charger. S'en remettre aux seules mutations bloquerait
exactement sur les pages qui ont besoin d'attendre.

Avant d'agir, la cible doit être **rattachée, visible, activée et stable** (deux rectangles
identiques à une frame d'intervalle). L'échéance est le `timeout_ms` du step, sinon
`options.timeout_ms`, sinon 30 000 ms — la valeur du contexte Playwright côté Python.

**Zéro correspondance est un « pas *encore* »**, et c'est ce qui fait la différence entre attendre et
ne pas attendre : un portail qui rend son formulaire quelques centaines de millisecondes après le
chargement est le cas normal, Playwright attend, donc le moteur Python attend, donc celui-ci attend.
**Plusieurs** correspondances, en revanche, sont une erreur que l'attente ne résoudra jamais : le
mode strict la refuse tout de suite. L'asymétrie est délibérée — une version antérieure levait sur
zéro comme sur plusieurs, ce qui court-circuitait l'attente et faisait échouer un `click` en 6 ms
(défaut trouvé par les sondes du jalon 3-E).

### Locators et mode strict

CSS d'abord, XPath ensuite (`document.evaluate`, présent dans une WebView réelle — contrairement à
l'extraction hors DOM de Vector, où XPath est refusé), texte enfin. Le préfixe `xpath=` que le
moteur Python ajoute est accepté ici aussi.

Le **mode strict** est reproduit à la lettre, et il n'est pas uniforme — l'asymétrie est délibérée
des deux côtés :

| Surface | Règle | Pourquoi |
|---------|-------|----------|
| Actions (`click`, `fill`, `type`, `press`, `select`, `hover`, `scroll`) | plusieurs correspondances = **erreur immédiate** ; zéro = on **attend** | agir sur une cible ambiguë est une faute à signaler, pas à masquer par un clic sur le mauvais bouton — mais une cible absente est peut-être en train d'arriver |
| `wait_for` | **première** correspondance | attendre concerne la *présence* ; plusieurs correspondances y sont normales |
| `extract` (`text`/`number`/`html`/`attr`) | **première** correspondance | lire n'est pas ambigu (`bridge.py` utilise `.first`) |
| `extract` `as: count` | compte **toutes** les correspondances | zéro est une réponse, pas un échec |

Le locator par texte est le moins précis des trois, et c'est pour cela qu'il vient en dernier :
il approche `get_by_text` (espaces normalisés, sous-chaîne insensible à la casse, boutons appariés
par leur `value`, correspondances les plus profondes seulement) sans reproduire sa traversée du
Shadow DOM.

### Le vocabulaire `as:` est un contrat de données

`text`, `number`, `html`, `attr`, `count`, `list`, plus `each`/`fields` pour les enregistrements —
identiques à ceux de l'Act II Python, détails compris, parce qu'un écart ici ne casse pas un run :
il produit une **donnée fausse**. Le nombre est extrait par expression régulière avec la virgule
décimale convertie en point, le texte est détouré, `count` ne prend pas la première correspondance,
et les sélecteurs de `fields` se résolvent **dans** leur conteneur.

Une reproduction se prend facilement pour un bug : dans un bloc `extract`, `selector_type` ne bascule
que vers XPath — tout le reste est lu en CSS, y compris `"text"`, parce que c'est ce que fait
`_resolve` côté Python. Les sélecteurs de conteneur et de champ d'un enregistrement y sont toujours
en CSS, ici comme là-bas.

Deux différences de *moment*, pas d'issue :

- une lecture simple **attend** que son élément soit rattaché (Playwright attend aussi, avant de
  lire) ; un `each` sans conteneur rend `[]` **tout de suite**, exactement comme
  `page.locator(each).all()` ;
- un champ absent **dans** un conteneur échoue immédiatement, là où Playwright épuiserait son délai.
  L'issue est la même erreur ; le message nomme le champ, et le run ne s'arrête pas trente secondes
  pour l'apprendre.

### Le cycle de vie de navigation

C'est le piège majeur du jalon, et il est traité par un état explicite : **prêt = l'agent s'est
annoncé sur la génération courante**. Rien d'autre ne compte comme prêt.

- La navigation appartient à l'**hôte** (`navigate`, `back`, `forward`, `reload` changent la vue),
  pas à l'agent. Injecter `window.location.href` — la façon artisanale — met deux autorités sur le
  même état, et le perdant est celui qui lit quand le document est remplacé sous lui.
- L'agent est **réinstallé à chaque fin de chargement**, avec une génération que l'hôte assigne (un
  document neuf ne se souvient de rien, il ne peut pas compter la sienne). C'est le **seul** entier
  jamais interpolé dans la source d'installation, et il ne peut par construction pas venir d'un
  Blueprint. Une navigation par fragment, qui ne recharge rien, déclenche une réinjection
  **idempotente**.
- Une opération en vol au moment d'une navigation est **résolue ou rejouée**, jamais laissée à son
  délai — un timeout enverrait chercher une page lente au lieu d'une navigation. Un `click` qui a
  *causé* la navigation réussit (c'est son résultat) ; une lecture qui a perdu sa page est
  **réémise sur le nouveau document**, dans la limite du délai du step. C'est obligatoire, et c'est
  un appareil réel qui l'a montré : un login POSTe et le portail répond **302**, donc la vue charge
  deux fois. Échouer entre les deux voulait dire qu'aucun Blueprint ne pouvait attendre quoi que ce
  soit **après un login** — c'est-à-dire l'essentiel de ce que l'Act II sert à faire. Playwright
  traverse une chaîne de redirections ; ce moteur aussi désormais. Seul un document perdu est
  rejoué : toute autre erreur veut dire ce qu'elle dit, et réémettre un sélecteur périmé ne ferait
  que consommer le budget.
- Après un `click`, un `press` ou un `select`, la page reçoit une fenêtre **bornée** (250 ms) pour
  *commencer* à naviguer. Si une navigation démarre, on attend le nouveau document ; sinon on
  continue. La fenêtre borne une décision, pas un chargement : attendre le chargement est le travail
  d'auto-attente de l'opération suivante.
- Un **échec de chargement annoncé par la vue** l'emporte sur tout le reste, et il est lu **avant**
  la génération. Ci-dessous : c'est le défaut qui a coûté deux jalons à être vu.

### Une source injoignable atteint `unavailable` (corrigé en 0.5.3)

Le modèle d'erreur du jalon 3-E promet qu'une WebView qui n'arrive pas à charger son document le dit,
et que le run échoue en `NetworkError` — donc `unavailable`, la seule famille qu'une application
réessaie. Le câblage existait depuis 3-E. Il n'a jamais fonctionné sur un appareil, et personne ne
l'a vu pendant deux jalons parce qu'**aucun double ne produisait la séquence d'une plateforme**.

Mesuré sur iPhone le 2026-08-09, en portant la session universitaire d'une application réelle
([UKit](../docs-ukit/README.md), jalon 6-F). Reproduction : pointer le `navigate` d'un Blueprint
`continuum` sur une adresse injoignable. Attendu : `unavailable`, et un bouton Réessayer. Obtenu : la
navigation **réussit**, et c'est l'attente suivante qui échoue — en `blocked` avec le code du
Blueprint quand il en a un, en `data` sinon.

**Deux causes indépendantes produisent ce même symptôme**, et c'est pourquoi il a fallu deux passes
sur l'appareil pour le clore. La première est dans ce moteur et elle est corrigée ; la seconde est
dans la bibliothèque de vue et elle décide de la façon dont on sonde.

#### 1. Le verdict était effacé, puis ignoré

La cause n'était pas le câblage. `react-native-webview` tire `onError` **puis `onLoadEnd`** pour la
*même* navigation en échec, dans le même tick ([`WebViewShared.tsx`][rnw-shared]) :

```
onLoadStart  ->  loadError = undefined
onError      ->  loadError = "Could not connect to the server."   <- le verdict
onLoadEnd    ->  loadError = undefined    <- il est efface ici
                 generation += 1, l'agent est injecte
l'agent s'annonce depuis la page d'erreur de la plateforme
awaitGenerationAfter : generation > previous && agentPresent  ->  succes
```

Deux erreurs, et il fallait les deux : un événement de fin de chargement était pris pour la **preuve
qu'un document s'est chargé**, et la boucle d'attente testait la génération **avant** le verdict —
alors que les deux sont vrais au même tour, puisqu'ils sont posés dans le même tick. Le correctif est
donc l'inverse exact : `onDocumentLoaded` n'efface plus rien, et `awaitGenerationAfter` lit le
verdict en premier. Un document qui s'annonce après un échec de chargement est la page d'erreur du
navigateur, pas celle qu'on a demandée.

[rnw-shared]: https://github.com/react-native-webview/react-native-webview/blob/master/src/WebViewShared.tsx

Trois choses à ne pas « corriger » plus tard, parce qu'elles ont l'air gratuites :

- **Le verdict est effacé par la commande de navigation, pas seulement par `onLoadStarted`.**
  `page.load()` est asynchrone : le signal de la vue arrive après le premier tour de la boucle
  d'attente, qui lirait donc le verdict de la tentative *précédente*. Une reprise échouait
  instantanément, en héritant d'un échec qu'elle n'avait pas rencontré — ce qui mordait exactement
  sur le bouton Réessayer que ce correctif existe pour rendre possible.
- **Après un échec, la même URL est *chargée*, pas *rechargée*.** Une WKWebView dont la navigation
  provisoire a échoué ne porte aucun document, et `reload()` sur elle ne fait rien du tout. Le
  contrat de `PageControl.load` exige donc de charger **même si la vue affiche déjà cette URL** ; le
  composant honore ça en changeant la `key` de la vue, parce que redonner à React la valeur qu'il a
  déjà ne re-rend rien.
- **`awaitReady` teste toujours `agentPresent` en premier.** Le verdict réseau est borné à la
  navigation qu'on a *demandée*. Une navigation de fond qui échoue — un client web qui tente une
  redirection morte — laisse le document courant intact sur iOS ; échouer là ferait régresser des
  runs qui marchent.

#### 2. Certains échecs n'arrivent jamais jusqu'ici, et c'est la vue qui décide

Le correctif ci-dessus était en place, gardé par trois tests, et la première sonde sur l'appareil a
quand même rendu `PAGE_ABSENTE`. Le correctif n'était pas en cause : **l'hôte n'avait rien reçu.**

`react-native-webview` filtre deux familles d'erreur avant d'appeler `onError`
([`RNCWebViewImpl.m`][rnw-ios]) — `NSURLErrorCancelled`, et **`WebKitErrorDomain` 101 / 102**. Le
102 (« Frame load interrupted ») est le bon geste : il arrive sur une redirection et n'est pas un
échec. Le **101** (« cannot show URL ») l'est moins : c'est ce que WebKit rend pour un **port
bloqué**, et la sonde visait `127.0.0.1:1` — le port 1 est sur la liste des ports que tous les
moteurs de rendu refusent. La vue savait, la bibliothèque a avalé, l'hôte est resté aveugle, la page
d'erreur s'est chargée et l'agent s'y est annoncé.

[rnw-ios]: https://github.com/react-native-webview/react-native-webview/blob/master/apple/RNCWebViewImpl.m

Le signe avant-coureur était sous les yeux : côté Python, la même adresse donnait
`net::ERR_UNSAFE_PORT` et non `ERR_CONNECTION_REFUSED`. « Port interdit » et « connexion refusée »
sont deux choses, et une seule des deux traverse la vue.

**D'où la règle de sondage, qui n'est pas un détail de confort : sonder avec un port qui _refuse_,
pas avec un port _bloqué_.** La sonde livrée vise donc `127.0.0.1:4` — privilégié (rien ne s'y lie
sans root, et l'OS ne l'attribue jamais en port éphémère), sur aucune liste de blocage, donc un vrai
`ECONNREFUSED` sur les deux moteurs.

Ce qu'il reste, et qui est une **limite, pas un défaut** : quand la plateforme ou la bibliothèque de
vue ne rapporte pas un échec, ce moteur ne peut pas l'inventer. Le périmètre est étroit et il n'est
pas celui de la production — un portail en panne rend `NSURLErrorDomain` (-1001, -1004, -1009), que
la bibliothèque laisse passer ; ce qui est avalé, ce sont un port bloqué et un schéma non supporté,
c'est-à-dire des Blueprints à corriger, pas des services à réessayer.

Un dernier geste traite le second symptôme, celui que la campagne d'origine avait observé sans
l'élucider : un nom qui ne résout pas ne produisait ni document ni `onError` avant l'échéance du
step, et retombait donc en `engine`. À l'échéance, un chargement que la vue a annoncé et n'a jamais
terminé devient un `TimeoutError` — sous-classe de `NetworkError`, donc `unavailable`. La vue disait
qu'elle travaillait dessus ; ce n'est pas un bug du moteur. L'`ActionError` reste pour le seul cas
qui la mérite : un document **chargé** dont aucun agent ne s'est annoncé.

Le moteur Python avait le **même angle mort**, et c'est en écrivant ce correctif qu'on l'a trouvé :
`page.goto` vers une adresse injoignable levait une `playwright.Error` brute, que le runtime
enveloppait en `RunError`. Une source en panne n'était donc `unavailable` d'**aucun** des deux côtés.
`navigate`, `back`, `forward` et `reload` typent désormais un échec de transport (`net::ERR_*`) en
`NetworkError` — voir [docs/acts/continuum.md](acts/continuum.md). Le `TimeoutError` de Playwright
garde son chemin : une page lente n'est pas une page injoignable.

Trois gardes, parce qu'une seule ne suffisait pas à voir le défaut :

| Garde | Ce qu'elle fige |
|-------|-----------------|
| `sdks/react-native/test/rpc.test.js` | la séquence de l'appareil, jouée à la main sur l'hôte : `onLoadFailed` **puis** une génération qui s'annonce. Plus la reprise, le `load` après échec, et le chargement qui ne revient jamais. Ces tests **ne peuvent pas** attraper la cause 2 : elle est en amont d'eux, dans ce que la vue consent à dire |
| Le double jsdom (`test/dom-host.mjs`) | il émet désormais `onLoadFailed` avant `onDocumentLoaded`, comme la plateforme. Sans ça le corpus ne pouvait rien voir — c'est précisément pourquoi il n'a rien vu pendant deux jalons |
| `conformance/cases/run/17-unreachable-source.json` | **les deux moteurs** échouent au step `navigate`, et le step suivant ne démarre pas. C'est la séquence qui divergeait, donc c'est la bonne garde |

Les trois ont été **vues échouer** par mutation du correctif : réintroduire l'effacement dans
`onDocumentLoaded`, réinverser l'ordre des tests, retirer l'effacement par la commande.

### Sessions, cookies et mode debug

`options.session.persist` décide de la nature de la vue, et le choix se voit par l'utilisateur :

| `persist` | Vue | Ce que ça coûte |
|-----------|-----|-----------------|
| absent / `false` | `incognito`, **libérée à la fin de chaque run** | départ propre à chaque run, ré-authentification à chaque lancement |
| `true` | magasin persistant du navigateur, et **la vue est gardée entre les runs** | pas de re-login, mais une WebView cachée reste vivante jusqu'au changement d'options ou au démontage du composant |

### Le pont de cookies natifs est une option à part, et il est cher

`options.session.share_native_cookies` — **faux par défaut**, et le défaut est le sujet.

Il ne sert **pas** à partager entre deux vues navigateur : sans `incognito`, `WKWebView` emploie le
magasin par défaut, qui vaut pour tout le processus. Une vue de navigateur intégré voit donc déjà la
session qu'un run vient d'ouvrir, sans rien demander. Il relie le magasin **natif** — celui qu'un
`http.request` d'Act I remplit — à la vue navigateur, ce dont seul un Blueprint qui mêle les deux Actes
a besoin.

**Il coûte un gel visible.** Le pont recopie *tous* les cookies de l'application — pas ceux de l'URL
visée, tous — un par un, chacun avec un aller-retour, **sur la file principale**
(`RNCWebViewImpl.m`). Le coût est donc proportionnel à ce que l'application a accumulé depuis son
installation, et il grandit avec l'usage.

Il était lié à `persist` jusqu'à cette version, ce qui faisait payer ce gel à quiconque voulait
seulement garder sa session. Un Blueprint qui compte sur le pont doit désormais le déclarer.

**Une session persistante garde sa vue**, et c'est une correction venue d'un appareil : détruire la
vue à la fin du run en recrée une au run suivant, et un **cookie de session** — celui qu'un login
pose, sans `Expires` — ne franchit pas cette frontière de façon fiable : il vit avec le contexte de
navigation, pas sur disque. `persist: true` doit donc garder la vue, sinon l'option promet ce que la
plateforme ne livre pas. Le coût est explicite et assumé : une WebView cachée survit au run. Avec
`persist: false` — le défaut — tout est libéré à chaque fois.

Corollaire à connaître : même avec `persist: true`, un cookie de session **meurt avec le processus**.
Tuer l'application ferme la session, et c'est la sémantique HTTP, pas une limite du moteur — seul un
cookie daté par le serveur survit à un redémarrage.

Ces options sont liées à la **création** de la vue sur les deux plateformes : en changer signifie
recréer la WebView, pas modifier une propriété. Le composant le fait en changeant sa `key` — la
seule méthode fiable, et celle sur laquelle les implémentations artisanales ont convergé.

**La vue est créée paresseusement**, au premier run `continuum`, **avec l'URL qu'elle doit
charger** — jamais sur un `about:blank` qu'une navigation remplacerait ensuite. Ce n'est pas un
raffinement : monter la vue sur un document blanc puis lui changer sa source **faisait crasher Expo
Go** (SDK 54, RN 0.81, New Architecture), sans message JavaScript, au premier run `continuum`. Le
bénéfice collatéral est réel : un run coûte un chargement au lieu de deux, et il n'y a plus de
document intermédiaire à raisonner. La vue est libérée à la fin du run. Une
application qui ne joue que de l'Act I ne porte donc aucune WebView cachée (ni le processus web natif
qui va avec), et un run obtient exactement *une* création de vue — au lieu d'une au démarrage puis
d'un remontage dès que les options de session du Blueprint sont connues. Corollaire à ne pas
inverser : **l'hôte survit aux runs qu'il sert** (sa vie est celle du composant). `dispose()` libère
la *vue*, il ne retire pas l'hôte ; c'est le `configure()` du run suivant qui la recrée. L'erreur
inverse est invisible au premier run et fatale au second — gardée par un test de régression.

`options.debug: true` **rend la WebView visible**, l'équivalent mobile de la fenêtre de navigateur
que le mode debug ouvre côté Python. Hors debug, la vue garde un viewport fixe (1024 × 768) : jamais
`display: none`, parce qu'une vue sans boîte ne met rien en page et que **tous** les éléments
seraient alors invisibles.

### « Cachée » veut dire cachée à l'utilisateur, pas à la plateforme

C'est la distinction qui gouverne tout ce bloc, et elle a coûté cher à trouver.

Un détail de mise en œuvre qui n'en est pas un : c'est le **conteneur** qui porte la position, pas la
vue. `react-native-webview` rend `<View style={[{flex: 1, overflow: 'hidden'}, containerStyle]}>`
autour de la vue native ; positionner la vue *interne* la laisse rognée à néant dans ce conteneur —
une WKWebView sans aire de rendu, ce qui est précisément la façon dont iOS finit par tuer le
processus de contenu web. La vue garde donc `flex: 1` et c'est `containerStyle` qui décide.

Mais une taille réelle n'est que **le premier** des trois signaux dont WebKit se sert pour décider
qu'une page est cachée. Les deux autres sont d'être **dans les limites de la fenêtre** et de **ne pas
être entièrement transparente**. Une première version gardait la taille et garait le conteneur à
`left: -10000` avec `opacity: 0` : elle satisfaisait le premier et manquait les deux autres. WebKit
traitait alors la page comme mise en arrière-plan et cessait de lui donner de quoi travailler — et
une navigation qui a besoin du JavaScript de la page pour se poursuivre, une cascade SSO ou un
formulaire SAML auto-soumis, **n'avançait tout simplement plus**.

**Mesuré sur un iPhone le 2026-09-05**, sur un portail universitaire atteint par une cascade SSO
complète : le premier `navigate` n'aboutissait jamais, ni à 30 s ni à 60 s, alors qu'un **réessai** —
où la session du service existait déjà et où aucune cascade n'était nécessaire — se posait en 281 ms.
Le même parcours avec la vue rendue visible par `options.debug` passait du premier coup, à chaque
fois. Hors écran et transparente était toute la différence.

Le conteneur reste donc **dans la fenêtre**, à `opacity: 0.01` — assez pour WebKit, imperceptible à
l'œil — et c'est `zIndex: -1` qui le met derrière tout ce que l'application dessine, donc hors de vue.
`pointerEvents: "none"` par précaution : une vue que personne ne voit ne doit pas être une vue que
quelqu'un touche.

Le coût est assumé et vaut d'être dit : sur une application dont le contenu est translucide, un
fantôme à un pour cent de la page est *techniquement* à l'écran. Personne ne l'a jamais vu, et
l'alternative est un moteur qui ne sait pas se connecter.

Le signal `onContentProcessDidTerminate` est écouté par ailleurs : le document ne revient pas tout
seul, donc les appels en vol échouent en le disant, au lieu d'attendre une page morte jusqu'à leur
échéance.

Le **user-agent** est configurable (`options.stealth.user_agent`) : c'est la seule bribe de
discrétion retenue par la phase, et elle est porteuse — un portail sert souvent un DOM différent aux
UA mobiles. Mesuré au jalon 3-G sur la messagerie d'une université : avec un UA Chrome desktop, la
page servie est `/mail#1` et le sélecteur du compteur existe ; avec un UA Safari iOS, c'est
`/modern/`, un DOM entièrement différent où il **n'existe pas**. La clé n'est donc pas un
raffinement, c'est ce qui rend la page atteignable depuis un téléphone.

> La clé était honorée ici depuis le jalon 3-D mais **absente du schéma partagé** : les deux moteurs
> refusaient tout Blueprint qui la déclarait, et aucun ne le disait, puisqu'aucun ne l'utilisait.
> Ajoutée à `contracts/blueprint.schema.json` au jalon 3-G, et honorée aussi par le moteur Python
> (contexte Playwright), sans rien activer d'autre — voir [docs/stealth.md](stealth.md#user_agent-à-part-des-autres).

### Ce que l'Act II embarqué ne fait pas

| Capacité | Traitement | Pourquoi |
|----------|-----------|----------|
| `upload` | **refusée à la validation** | une WebView n'expose pas de sélecteur de fichier |
| `drag` | **refusée à la validation** | pas de séquence de pointeur de confiance |
| `screenshot` | **refusée à la validation** | capturer la vue est l'affaire de l'application hôte, pas du moteur |
| `navigate` → `status` | **la clé n'est pas publiée** | une WebView n'expose aucun code de statut HTTP pour son document principal. Rendre `null` aurait fait passer un `assert` à côté de la vérité — une donnée fausse. La clé absente fait **lever** `{{ steps.nav.status }}` (StrictUndefined), au step qui la lit, en nommant la variable. Figé par le cas de conformance `run-continuum-navigate-status`. |
| nouvelles fenêtres | **interdites** (`setSupportMultipleWindows={false}`) | dans une WebView cachée, ouvrir une fenêtre n'a pas de sens ; le moteur Python, lui, suit les nouveaux onglets |
| `wait_until` de `navigate` | **lu et ignoré** | une WebView signale un seul événement de chargement ; prétendre honorer quatre états serait une promesse intenable |
| l'échéance d'une opération | **tenue par l'appelant**, pas par l'agent | iOS **throttle, et peut suspendre, les minuteurs d'une WKWebView hors écran** — et ce moteur l'y garde délibérément. L'agent annonce son propre dépassement quand il le peut (le message dit *ce qu'il* attendait), mais son horloge est au mieux indicative. Un silence au-delà de l'échéance de l'appelant est donc traité comme l'expiration de l'attente, **avec le code que le Blueprint a nommé** (`on_timeout: "fail:CODE"`). Sans cela un login refusé arrivait en « erreur interne » plutôt qu'en `LOGIN_FAILED` |
| `press` avec une touche à action par défaut | **`Enter` soumet explicitement** | un événement clavier synthétique ne déclenche aucune action par défaut ; `Enter` dans un formulaire appelle donc `requestSubmit()`, ce qu'un navigateur aurait fait |

Deux détails d'implémentation méritent d'être connus avant qu'on les « corrige » par erreur :

- **un clic est à la fois une séquence et un `click()`.** Les `mousedown`/`mouseup` synthétiques
  atteignent les gestionnaires JavaScript mais ne déclenchent pas l'action par défaut d'un `<a>` ou
  d'un bouton de soumission ; `element.click()` déclenche l'action par défaut mais saute la séquence
  que certains frameworks écoutent. Faire les deux est la seule façon honnête de couvrir de vraies
  pages ;
- **écrire `value` ne suffit pas sur un champ contrôlé.** React installe son propre traqueur de
  valeur : écrire la propriété directement le laisse croire que rien n'a changé, et le framework
  restaure l'ancienne valeur au rendu suivant. `fill` passe donc par le *setter* natif du prototype
  avant d'émettre `input`/`change`. C'est la ligne la plus utile du fichier pour les portails que
  vise Aetherius.

## La surface applicative

Jalon 3-E. Les jalons précédents ont fait **tourner** le moteur ; celui-ci décide de **ce qu'une
application voit de lui**. C'est la surface publique du moteur embarqué, celle qu'on ne pourra plus
changer sans casser ses consommateurs.

```tsx
import * as SecureStore from "expo-secure-store";
import {
  Aetherius, AetheriusConfirm, AetheriusWebView, keychainSecrets, describeFailure,
} from "@aetherius/react-native";

const client = new Aetherius({ secrets: keychainSecrets(SecureStore) });

// Une fois, haut dans l'arbre : la WebView et le modal vivent avec l'application, pas avec un run.
<><AetheriusWebView /><AetheriusConfirm /></>

const result = await client.run(blueprint, {
  inputs: { groupe: "TP-A1" },
  onEvent: (event) => setProgress(event),
});
```

**Les mêmes noms que le SDK daemon.** `client.run(blueprint, { inputs, secrets, onEvent })` se lit à
l'identique qu'on pilote un moteur distant ([`@aetherius/client`](../sdks/client)) ou qu'on en
embarque un. Le choix d'architecture ne doit pas se voir dans le code appelant, sinon passer de
l'un à l'autre voudrait dire réécrire l'application. Les deux **canaux de sortie** sont les mêmes
aussi : un `Result` (échec de run tracé dedans) et une exception (Blueprint refusé avant le
démarrage, dépendance absente, bug du moteur).

`run` accepte un Blueprint sous trois formes — un objet déjà chargé, le texte JSON, ou le document
brut d'un `import`. Toutes passent par la validation : elle coûte des microsecondes (le schéma est
précompilé) et supprime la classe de bugs où l'on *croyait* avoir validé.

### Les secrets ne quittent pas l'appareil

C'est la raison d'être de la phase prise à la lettre. Une application universitaire qui scrape l'ENT
de son utilisateur détient ses identifiants CAS ; ils ne doivent aller qu'au CAS de son université.

La résolution est **branchable** : le trousseau de l'OS est l'implémentation par défaut, pas une
dépendance du moteur. Le magasin est **injecté**, jamais importé — le paquet décrit
structurellement ce dont il a besoin (`getItemAsync(key): Promise<string | null>`), même posture que
`fetch` et `react-native-webview`. Zéro dépendance ajoutée au binaire, aucune adhérence à Expo pour
une application React Native nue, et un resolver testable sans trousseau (`staticSecrets`).

```ts
new Aetherius({
  secrets: keychainSecrets(SecureStore, { key: (name) => `ukit.${name}` }),
});
```

Le mapper `key` existe parce qu'une application a **déjà** ses clés : les renommer pour plaire à
Aetherius serait le genre de migration qu'une bibliothèque n'a pas à imposer.

Trois invariants tiennent l'hygiène, et les trois sont testés :

- **seuls les secrets déclarés** par le Blueprint sont demandés au resolver. Un Blueprint ne peut
  pas se servir dans le trousseau de l'application ;
- **une valeur passée à `run` gagne** sur ce que rend le resolver — le même ordre de priorité que
  [docs/secrets.md](secrets.md) côté Python. Un secret introuvable est *omis*, et c'est le rendu qui
  signale l'erreur, au step qui le lit réellement ;
- **aucune valeur ne franchit la frontière du journal.** Le moteur y contribue par construction (un
  événement `step_skipped` publie l'expression `when` **brute**, jamais sa valeur rendue) et la
  façade ajoute un rideau : les valeurs résolues sont masquées dans le `message` et le `data` de
  **chaque** événement, dans `Result.error` et dans le message de `Result.cause`.

Le rideau est nécessaire parce que trois chemins restent ouverts, et aucun n'est théorique : le
message d'un `assert` est **rendu** avant d'être levé, une URL en échec peut porter un secret
interpolé, et le message d'un `confirm` est rendu lui aussi — l'exemple livré demande « envoyer les
identifiants de *tel utilisateur* ? ». Ce dernier cas montre bien où passe la frontière :
**l'humain voit ce qu'il approuve** (le modal lit la demande, pas l'événement), le journal non. La limite est écrite plutôt que découverte : **le masquage se fait par valeur**, donc un
« secret » d'un ou deux caractères masquerait ces caractères partout dans les messages. C'est
visible, et plus honnête qu'un masquage qui cesserait silencieusement de protéger sous un seuil.
`redact: false` le désactive, et n'a de sens qu'au débogage du moteur lui-même.

### `confirm` en modal natif

Côté Python, il a fallu **quatre** surfaces pour poser une question à un humain — un modal de
Console, une invite de terminal, une route du daemon, les boutons d'une notification. Sur un
téléphone il y en a une seule, et elle est évidente. C'est ce qui rend `confirm` plus naturel ici
qu'ailleurs.

La sémantique du jalon 2-E est reprise **exactement** : le run reste vivant et **garé**, son statut
ne change pas (`input_requested` / `input_provided` sont les seuls signes), le délai est
**obligatoire**, et `on_timeout` vaut **refus** par défaut. Ce défaut n'est pas de la prudence
décorative : une application mise en arrière-plan ne répondra jamais, et le comportement sûr doit
être celui qui arrive tout seul.

`<AetheriusConfirm />` est l'habillage par défaut. La **primitive** est le hook, et c'est là que
s'arrête une application qui veut son propre design (feuille du bas, écran dédié, biométrie) :

```tsx
const { request, approve, reject } = useApprovalRequest();
```

**Personne n'écoute = run non surveillé.** Un écran qui n'a monté ni `<AetheriusConfirm />` ni
`useApprovalRequest` ne montrera jamais la question : garer cinq minutes devant lui serait un blocage
sans cause visible. La passerelle applique donc la politique `on_timeout` **tout de suite** — refus
par défaut —, exactement comme un run de bibliothèque côté Python. La décision se prend au moment où
la question est posée, le seul où l'on sait qui écoute.

Trois points de mise en œuvre méritent d'être connus avant qu'on les « corrige » :

- **l'échéance est tenue en heure murale**, pas seulement par un minuteur. Sur un téléphone, une
  application en arrière-plan voit ses minuteurs gelés : au retour, le minuteur se déclenche en
  retard et une décision tapée entre-temps arriverait *après* l'expiration. Comparer l'horloge au
  moment de résoudre est ce qui rend « une décision arrivée après l'expiration est ignorée » vrai
  sur un appareil, et pas seulement en test ;
- **`channel`/`target`/`config`/`level` sont lus et ignorés.** Côté Python ils alertent un canal de
  notification ; ici l'application possède déjà ses notifications (même raison que le refus de
  `notify`), et la surface de décision *est* le modal. Les ignorer plutôt que les refuser garde la
  promesse « le même Blueprint des deux côtés ».

### Le modèle d'erreur

Le point le plus structurant du jalon. Le réflexe répandu, dans les couches de service mobiles, est
de tout rattraper et de rendre une valeur vide : **une source en panne et une réponse légitimement
vide deviennent alors indiscernables**, et un écran « aucun résultat » peut masquer un service
indisponible.

Le moteur lève des erreurs **typées** et ne décide pas à la place de l'application ; il fournit de
quoi distinguer les cas. `describeFailure` est le motif recommandé, et il est **livré** plutôt que
décrit :

```ts
const result = await client.run(blueprint, { onEvent });
const failure = describeFailure(result);          // undefined quand le run a reussi
if (failure?.kind === "unavailable") showRetry();
```

| `kind` | Erreurs source | Ce que l'application en fait |
|--------|----------------|------------------------------|
| `blueprint` | `BlueprintLoadError`, `BlueprintSchemaError`, `BlueprintValidationError` | le Blueprint est faux ou non portable — corriger et livrer, ne pas réessayer |
| `unavailable` | `NetworkError`, `TimeoutError`, `RetryExhaustedError` | **la source est en panne** — réessayer, dire « service indisponible » |
| `rejected` | `StatusAssertionError` | la source a répondu, mais pas comme `expect` l'exigeait |
| `blocked` | `StepTimeoutError` **avec** un code | échec **nommé** par le Blueprint : `LOGIN_FAILED` → « identifiants refusés » |
| `data` | `ExtractionError`, `StepTimeoutError` **sans** code | la page ou la réponse n'est plus celle que le Blueprint décrit — un Blueprint à corriger (jalon 3-F) |
| `config` | `TemplateError` | une donnée d'entrée manque : un secret absent du trousseau, une entrée non fournie |
| `cancelled` | `RunCancelledError` | l'utilisateur est parti : ne rien afficher |
| `unsupported` | `DependencyError` | une pièce de plateforme manque (aucune WebView montée) |
| `engine` | `ActionError`, `RunError`, le reste | un bug — remonter, pas masquer |

Deux décisions se lisent dans ce tableau :

- **le code partage `StepTimeoutError` en deux.** Un Blueprint qui a *nommé* son échec
  (`on_timeout: "fail:LOGIN_FAILED"`) sait ce qui s'est passé et l'application peut l'afficher tel
  quel ; une attente qui expire sans nom veut seulement dire que la page n'est pas celle qu'on
  décrivait — le même diagnostic qu'une extraction qui ne trouve rien ;
- **un sélecteur qui ne résout plus est un `ExtractionError`, pas un `ActionError`.** C'est l'échec
  Act II le plus courant en production, et le classer « bug du moteur » enverrait l'auteur corriger
  ce qui n'est pas cassé. Le corriger a demandé de retyper l'erreur **des deux côtés** (voir les
  sondes du jalon) ;
- **`config` n'est pas `data`**, et c'est la campagne sur appareil qui a tranché : un secret absent
  du trousseau s'affichait « la page a changé ». La page allait très bien — c'est l'appelant qui
  n'avait rien fourni. Les deux appellent des écrans opposés : l'un dit « on s'en occupe », l'autre
  « saisis tes identifiants ».

Et le pendant, qui est la moitié du sujet : **une réponse vide n'est pas une erreur**. Un run
`status: "success"` dont les `outputs` portent une liste vide a réellement trouvé une liste vide, et
`describeFailure` rend `undefined`.

L'Act II y participe : une WebView qui **n'arrive pas à charger** son document (pas de réseau, DNS
en échec, TLS refusé) le signale à l'hôte, et le run échoue sur un `NetworkError` — donc
`unavailable`, la seule famille qu'une application réessaie. Sans ce signal, le run apprendrait
seulement qu'aucun agent ne s'est annoncé et afficherait « erreur interne » à un téléphone
simplement hors ligne. La vue *sait* ; elle le dit.

> Ce paragraphe a décrit une intention pendant deux jalons. Mesuré sur iPhone le 2026-08-09, le
> signal était bien câblé et **jamais consulté** ; corrigé en 0.5.3, avec le récit et les gardes
> dans [Une source injoignable atteint `unavailable`](#une-source-injoignable-atteint-unavailable-corrigé-en-053).

`describeFailure` accepte les **deux canaux** — un `Result` en échec ou une exception levée —
précisément pour qu'une application n'ait pas à savoir lequel a parlé. Pour que la classe survive à
un run, le `Result` du moteur embarqué porte un champ de plus que celui du moteur Python :

> **`Result.cause`** — l'erreur typée derrière `error`. C'est le **seul** ajout à la forme du
> `Result`, et il est là parce qu'`error` est une chaîne des deux côtés : obliger une application à
> analyser de la prose pour savoir si la source est en panne ou si le Blueprint est faux serait
> exactement le défaut que ce jalon combat. Le champ ne survit pas à une sérialisation JSON — c'est
> une valeur de processus, pas un champ de fil — et il est invisible pour le corpus de conformance,
> qui compare le statut, les `outputs`, les `StepResult` et les événements.

### L'annulation

Un besoin réel sur mobile, pas un raffinement : un utilisateur qui quitte un écran, une application
mise en arrière-plan. Sans annulation, **une WebView cachée survit à l'écran qui l'a demandée**.

```ts
client.cancel(runId);          // ou RunOptions.signal, ou client.close()
```

C'est la seule divergence de vocabulaire avec le moteur Python, qui n'a pas d'annulation (il tourne
sur une machine, où un run va au bout). Aucun statut n'est inventé : **un run annulé est un run
`failed` dont la `cause` est une `RunCancelledError`**, que `describeFailure` traduit en
`kind: "cancelled"` — ce qu'une UI traite comme « ne rien afficher », pas comme une panne.

Trois grains d'observation, et il en faut trois : entre deux steps, pendant une attente (`wait`, le
recul des reprises, un `confirm` garé) et pendant une opération en vol (une requête, un appel à la
WebView). N'en tenir qu'un ferait attendre l'annulation jusqu'à trente secondes. Une opération déjà
envoyée à la WebView n'est pas rappelée — c'est impossible — mais son résultat est **abandonné**, et
le démontage qui suit libère la vue. Un step annulé n'est **pas** enregistré comme échoué : un run
que l'appelant a interrompu ne doit pas laisser une traînée de steps marqués en erreur.

### Une WebView, un run Act II à la fois

Il y a **une** vue montée, donc **un** run `continuum` à la fois. Deux runs concurrents
appelleraient chacun `configure()` sur le même hôte — le second remontant la vue sous le premier —
et le premier `teardown()` détruirait la vue que le second pilote encore. La panne est silencieuse,
et elle ressemble à un portail capricieux plutôt qu'à une erreur de programmation.

Le second run est donc **refusé** par une `DependencyError` qui nomme le conflit, avant de toucher à
quoi que ce soit. Refuser plutôt que mettre en file est délibéré : une file cacherait un `confirm`
garé (jusqu'à cinq minutes) tenant l'unique vue derrière un délai inexpliqué. Une application qui
veut sérialiser le fait explicitement. **Les runs `vector` restent concurrents sans limite** : ils
ne partagent rien.

## La livraison des Blueprints

Jalon 3-F, et le gain produit de la phase. Jusqu'ici un Blueprint arrivait par un `import` : il était
**figé dans le binaire**, donc un site qui change cassait l'application jusqu'à une publication sur
les stores — exactement le coût que la Phase 3 existe pour supprimer. Le registre le rend
corrigeable en quelques minutes, pour tous les utilisateurs, sans rien republier.

Ce qui est livré, ce sont le **client** et le **format**, pas une infrastructure : un dépôt de
fichiers statiques derrière un CDN suffit, et c'est un motif déjà éprouvé pour du contenu éditorial
d'application.

```ts
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Aetherius, BlueprintRegistry } from "@aetherius/react-native";

import planning from "./blueprints/planning.blueprint.json";   // le socle, dans le binaire

const registry = new BlueprintRegistry({
  bundled: { "ukit.planning.week": { version: "1", document: planning } },
  manifest: "https://cdn.exemple.fr/aetherius/manifest.json",
  cache: AsyncStorage,          // injecte : sa surface satisfait l'interface telle quelle
});

const { blueprint, origin } = await registry.resolve("ukit.planning.week");
await client.run(blueprint, { inputs });

void registry.refresh();        // asynchrone, hors du chemin critique
```

### Le socle embarqué n'est pas optionnel

Une application doit fonctionner **au premier lancement, hors ligne**, sans avoir jamais contacté le
réseau. Les Blueprints embarqués dans le binaire sont la source de vérité de départ ; le distant est
une **surcouche**. Un registre purement distant transformerait une panne de CDN en application
morte.

Trois conséquences, et ce sont des règles, pas des détails :

- **La résolution ne touche jamais au réseau.** `resolve()` lit le cache local, rien d'autre. Un run
  n'attend pas un CDN pour savoir quoi jouer. `refresh()` est un geste **séparé**, que l'application
  déclenche quand ça l'arrange (au démarrage, au retour au premier plan) et dont elle peut ignorer
  le résultat.
- **`refresh()` ne lève jamais** pour une panne réseau ou un manifeste malformé : elle rend un
  rapport. Une livraison est un confort ; en faire une erreur visible rendrait une application
  dépendante du CDN qu'elle était censée pouvoir ignorer.
- **Le manifeste ne peut que *mettre à jour* ce que l'application livre déjà.** Un nom absent du
  socle est ignoré. C'est ce qui garantit le repli hors ligne **pour chaque Blueprint**, et ce qui
  empêche un manifeste compromis d'ajouter du comportement que personne n'a relu. Ajouter un
  Blueprint reste une livraison d'application — ce qu'il faudrait de toute façon pour lui faire une
  place à l'écran. **Une application qui veut pouvoir *étendre* lève cette troisième règle
  explicitement**, sous un préfixe de noms réservé : voir
  [Étendre : les noms réservés](#étendre--les-noms-réservés). Les deux premières, elles, ne se
  lèvent pas.

### Le manifeste

C'est le **contrat applicatif** que ce jalon définit — le seul contrat ajouté par la phase, et il
n'a rien à voir avec ceux de `contracts/`, qui restent inchangés. Il est servi tel quel par un
hébergement statique.

```json
{
  "manifest": "1",
  "generated_at": "2026-08-04T12:00:00Z",
  "disabled": false,
  "blueprints": {
    "ukit.planning.week": {
      "version": "2",
      "url": "planning.v2.blueprint.json",
      "sha256": "627fa03a4e5922323babc5bd5608d6d165069694c2bc571dc61a4d214f416538",
      "min_engine": "0.4.0",
      "disabled": false
    }
  }
}
```

| Champ | Règle |
|-------|-------|
| `manifest` | version du **format**, pas des Blueprints. `"1"` aujourd'hui ; toute autre valeur fait **ignorer le manifeste entier**. C'est le mécanisme d'évolution : une vieille application ignore un manifeste écrit pour un moteur plus récent au lieu d'en lire la moitié de travers. |
| `generated_at` | horodatage informatif. Il ne décide jamais de rien. |
| `disabled` (racine) | **interrupteur d'arrêt global** : tout revient à l'embarqué. |
| `blueprints` | table indexée par le `name` du Blueprint. Un nom que l'application n'embarque pas est ignoré. |
| `version` | version **du Blueprint**, chaîne numérique pointée (`"2"`, `"1.4"`), ordonnée. Le distant ne gagne que s'il est **strictement supérieur** à la version embarquée. |
| `url` | absolue, ou relative — résolue contre l'URL du manifeste. |
| `sha256` | empreinte hexadécimale minuscule du **texte servi**. |
| `min_engine` | optionnel. L'entrée est ignorée si le moteur installé est plus ancien. |
| `disabled` (entrée) | interrupteur d'arrêt pour ce Blueprint. |

Le parseur est **strict** : une clé inconnue, un type inattendu, une version non numérique ou une
empreinte malformée font refuser le manifeste, et un manifeste refusé ne remplace rien. Ce n'est pas
du purisme : une faute de frappe dans `disabled` ou dans `sha256` ne doit pas pouvoir **désactiver
une garde en silence**.

Le versionnage est volontairement plus pauvre que SemVer — ni pré-release, ni métadonnées : une
comparaison qu'un publieur peut faire de tête vaut mieux qu'une grammaire dont il devine les coins.

### L'ordre de résolution

```
cache distant valide et plus récent que l'embarqué  →  sinon l'embarqué
```

« Valide » veut dire : **toutes** les gardes ci-dessous, rejouées **à chaque lecture** — pas
seulement au téléchargement. Vérifier à l'écriture seulement supposerait qu'un cache local est digne
de confiance ; il ne l'est pas plus qu'un CDN, c'est un fichier sur un appareil. Une entrée qui
échoue une garde est **purgée** au passage : un cache corrompu ou périmé se soigne tout seul au lieu
d'être rejeté à chaque run pour l'éternité.

Le manifeste décrit **l'état voulu** : une entrée qui en disparaît ramène son Blueprint à la version
embarquée, au même titre qu'une entrée `disabled`. L'interprétation la plus sûre d'un manifeste
partiel est ainsi toujours le socle.

### Les trois gardes

Un Blueprint est de la **donnée exécutable**, et il faut le traiter comme tel. Par ordre
d'importance :

1. **Intégrité.** L'empreinte SHA-256 du texte doit être celle qu'annonce le manifeste. Une réponse
   tronquée, un fichier modifié après coup, un cache bricolé : tous échouent là, et **la version en
   place n'est jamais remplacée par un échec**. Le condensat est écrit à la main
   ([`sha256.ts`](../sdks/react-native/src/delivery/sha256.ts)) — même posture que le base64 de
   `BasicAuth` : `crypto.subtle` n'existe pas sous Hermes, et les bibliothèques disponibles
   marcheraient *la plupart du temps*, ce qui est la pire propriété possible pour une garde
   d'intégrité. Il est comparé à `node:crypto` en test, coins compris.
2. **Périmètre.** Un Blueprint distant ne peut pas élargir ce que l'application sait faire. Les
   secrets qu'il a le droit de **déclarer** sont bornés par l'application (`allowedSecrets`), et par
   défaut c'est l'union de ceux que déclare le socle embarqué — c'est-à-dire ce que l'application a
   été construite pour fournir. Sans cette borne, un Blueprint distant compromis pourrait réclamer le
   contenu du trousseau et l'exfiltrer par une simple requête. La façade ne résout déjà que les
   secrets **déclarés** (jalon 3-E), ce qui borne ce qu'un Blueprint peut *lire* ; c'est ici qu'on
   borne ce qu'il peut *déclarer*. Un fichier livré sous un `name` qui n'est pas le sien est refusé
   pour la même raison : sinon le manifeste dirait une chose et l'appareil en jouerait une autre.
3. **Sûreté d'exécution.** Elle est acquise **par construction depuis le jalon 3-B** : l'évaluateur
   d'expressions n'exécute pas de code dynamique et n'expose ni fonctions natives, ni prototypes, ni
   globales — il n'y a donc aucune liste blanche à maintenir. C'est ce qui rend ce jalon défendable,
   et c'est écrit ici pour qu'on n'« optimise » pas un jour l'évaluateur en réintroduisant une
   compilation dynamique. La garde `no-dynamic-code` la tient à chaque exécution des tests.

Et, avant tout cela, la **validation complète** : un Blueprint distant passe par `parseBlueprint` +
`validateForAct`, exactement comme un fichier local. Un document invalide au schéma ou non portable
sur ce moteur (`upload`, `screenshot`, act `oracle`…) est refusé **avant** d'atteindre le cache,
donc il n'atteint jamais un run.

### Étendre : les noms réservés

Jalon 3-H, et un appendice au précédent. La troisième règle — *le manifeste ne peut que mettre à
jour* — est la bonne pour **corriger**. Elle ne tient plus dès qu'il s'agit d'**étendre**, et le cas
est réel : une application universitaire qui veut ajouter le portail d'une nouvelle faculté en cours
d'année paie aujourd'hui une publication sur les stores, alors que tout ce qui distingue cette
faculté est un fichier de données.

Les deux raisons de la règle d'origine ne pèsent pas le même poids pour un nom **nouveau** :

| Raison de la règle | Pour un nom déjà embarqué | Pour un nom nouveau |
|---|---|---|
| Garantir un repli hors ligne | **tient** — l'application doit pouvoir jouer ce Blueprint sans réseau | **sans objet** — il n'existe pas encore pour l'utilisateur, il n'y a rien à quoi retomber |
| Empêcher l'ajout de comportement non relu | **tient** | **tient toujours** — c'est ce que le périmètre borne |

La levée porte donc sur la première ligne seulement, et la seconde reste entière. C'est ce
déséquilibre qui rend le mécanisme défendable ; sans lui, il faudrait le refuser.

```ts
new BlueprintRegistry({
  bundled,
  manifest: "https://…/manifest.json",
  cache: AsyncStorage,
  // Le seul ajout du jalon, et il est entierement cote application.
  allowNew: { prefix: "ukit.portail.", secrets: ["portail_user", "portail_pass"] },
});
```

**Le format de manifeste ne change pas.** C'est le point le plus important : un manifeste écrit pour
ce jalon reste lisible par une application qui ne l'active pas, et elle ignore simplement les entrées
qu'elle n'embarque pas — exactement ce qu'elle faisait déjà.

`allowNew.secrets` est **obligatoire**, et n'a surtout pas pour défaut « l'union des secrets du
socle » comme `allowedSecrets`. Ce défaut-là est raisonnable pour une **mise à jour** — le fichier
remplacé déclarait déjà ces secrets, l'application a été construite pour les fournir — et il ne l'est
pas pour un fichier que personne n'a relu. Obliger à l'écrire, c'est obliger à décider ce qu'un
inconnu aura le droit de demander. Un tableau vide est une réponse valide, et la plus restrictive.

Cinq règles portent le reste :

- **Un préfixe, pas un motif.** Une comparaison de début de chaîne, sans joker ni expression
  régulière. Un motif serait plus expressif et beaucoup plus facile à écrire de travers — et une
  garde qu'on écrit de travers est une garde absente.
- **Le préfixe doit finir par un point, et il est refusé à la construction sinon.** `""` ouvrirait
  tout ; `"ukit"` couvrirait `ukit.planning.semaine`, c'est-à-dire précisément les Blueprints que
  l'application embarque et qu'on ne veut pas voir remplaçables par un nom voisin. Le point parce
  qu'un `name` est un identifiant pointé au contrat ; commencer strict est relaxable plus tard sans
  casser une application existante, l'inverse ne l'est pas.
- **Un nom embarqué garde sa règle.** Si un nom est *à la fois* dans le socle et couvert par le
  préfixe, c'est la règle de 3-F qui s'applique : version strictement supérieure, et le périmètre du
  socle. Le préfixe **ajoute** des portes, il n'en élargit aucune. Un nom nouveau, lui, n'a pas de
  version à battre — il n'a pas de socle, et exiger une comparaison contre une version qui n'existe
  pas reviendrait à en inventer un.
- **Retirer le préfixe désinstalle.** Une entrée arrivée par cette porte et qui n'est plus couverte —
  parce que l'application a changé son préfixe ou retiré `allowNew` — est **purgée** à la lecture
  suivante, sans réseau. Un interrupteur d'arrêt qui laisse en place ce qu'il a laissé entrer n'en
  est pas un.
- **Aucune nouvelle famille d'erreur.** Un nom refusé n'est pas un échec : c'est une entrée
  `ignored` dans le `RefreshReport`, avec sa raison — et la raison distingue « ce nom n'est pas
  couvert » de « cette application n'a pas la capacité », parce qu'un publieur qui ne sait pas
  *pourquoi* son entrée est tombée débugue à l'aveugle.

`min_engine` prend ici tout son sens : un portail publié pour un moteur plus récent est ignoré
**silencieusement** par les applications anciennes, ce qui permet d'en écrire un sans se demander qui
l'exécutera.

Deux conséquences à connaître avant d'activer la capacité. `resolve()` d'un nom couvert mais **pas
encore livré lève**, comme n'importe quel nom inconnu : il n'y a rien à jouer, et répondre autre
chose serait inventer un socle — `list()` est la façon de savoir ce qui est disponible, et il liste
désormais ce qui est arrivé par la porte après ce que le binaire embarque. Et un Blueprint ajouté à
distance **n'a pas de repli hors ligne** avant d'avoir été résolu une fois : c'est la contrepartie
assumée de la levée, sans conséquence pour un portail qu'on n'a jamais joué.

### Le modèle de menace, et ce qu'il ne couvre pas

Écrire ce qui est protégé sans écrire ce qui ne l'est pas donnerait une fausse assurance.

| Menace | Traitement |
|--------|-----------|
| Altération en transit, réponse tronquée, CDN qui sert un vieux fichier | **couverte** — l'empreinte du manifeste, revérifiée à chaque lecture |
| Manifeste malformé, format inconnu, entrée bricolée | **couverte** — parseur strict, refus global, rien n'est remplacé |
| Cache corrompu ou modifié sur l'appareil | **couverte** — l'entrée est rejetée et purgée, l'application retombe sur son socle |
| Blueprint distant réclamant un secret que l'application ne lui a pas ouvert | **couverte** — périmètre des secrets |
| Blueprint distant utilisant une capacité que ce moteur n'a pas | **couverte** — validation par act, avant le cache |
| Blueprint écrit pour un moteur plus récent | **couverte** — `min_engine`, l'entrée est ignorée sans erreur visible |
| Exécution de code arbitraire par une expression | **couverte par construction** — jalon 3-B |
| Blueprint **ajouté** à distance sous un nom que l'application n'a jamais relu | **partiellement couverte.** Il est validé, son intégrité est vérifiée, il ne peut déclarer que les secrets de `allowNew.secrets`, et il n'existe que sous le préfixe réservé — que l'application a explicitement ouvert. Ce qu'il fait de ces secrets et où il envoie ses requêtes n'est **pas** borné, comme pour n'importe quel Blueprint distant depuis 3-F. |
| **Publieur compromis** (clé du dépôt, du CDN, du compte) | **non couverte.** Un manifeste signé par le bon publieur est cru. Un attaquant qui contrôle la publication peut livrer un Blueprint qui envoie **les secrets autorisés** où il veut. Le périmètre limite le rayon de l'incendie (les secrets que l'application a déjà ouverts à ce Blueprint), il ne l'éteint pas. |
| Nombre de portes ouvertes par le préfixe réservé | **assumé.** Un publieur compromis pouvait déjà livrer un Blueprint malveillant sous un nom existant : le jalon 3-H augmente le **nombre de portes**, pas leur solidité. C'est pourquoi la ligne ci-dessus reste la première du tableau, et pourquoi le périmètre de secrets y devient **obligatoire** plutôt que déductible. |
| Confidentialité et authenticité du transport | **déléguées à TLS.** Il n'y a pas de signature d'auteur : ce serait la réponse à la ligne précédente, et elle demanderait une gestion de clés qu'un dépôt de fichiers statiques ne fournit pas. Servir le manifeste en HTTPS n'est donc pas un détail de configuration. |
| Destination des requêtes d'un Blueprint distant | **non bornée.** Une URL de Blueprint peut être un gabarit (`{{ vars.domain }}/…`), donc une liste blanche d'hôtes vérifiée statiquement serait contournable — et une vérification à l'exécution ferait échouer des Blueprints corrects. Mieux vaut une limite écrite qu'une garde qui rassure sans mordre. |

### L'interrupteur d'arrêt

Un mécanisme de déploiement sans mécanisme de retour arrière n'en est pas un. Il y en a donc trois,
selon l'urgence et selon qui décide :

| Geste | Qui | Effet |
|-------|-----|-------|
| `disabled: true` sur une entrée, ou à la racine, ou entrée retirée du manifeste | le publieur | l'embarqué reprend la main **au prochain rafraîchissement** |
| `registry.revert(name?)` | l'application | purge la surcouche **tout de suite**, sans réseau ; effectif au run suivant. Un `refresh()` ultérieur peut ramener une version distante |
| `remote: false` à la construction | l'application | la surcouche est ignorée durablement, sans être détruite : rallumer la livraison la retrouve, hors ligne |

### Le cache

Le magasin est **injecté**, jamais importé — même posture que le trousseau et que `fetch`. La
surface décrite (`getItem`/`setItem`/`removeItem`) est celle d'AsyncStorage, qu'une application
branche donc **sans adaptateur** ; un magasin de fichiers s'y branche en dix lignes, et
`memoryCache()` sert les tests et les applications qui ne veulent rien persister.

Tout tient dans un **document unique**, sous une seule clé. Le coût est connu et assumé : un document
illisible fait perdre la surcouche **entière**, et l'application retombe sur son socle. C'est le sens
du repli, et c'est préférable à un index et des entrées qui peuvent se contredire — un cache à moitié
cohérent serait un état qu'aucun test ne couvre vraiment. Un magasin qui **échoue** (verrouillé,
plein) est traité comme un magasin absent : la correction vaut alors pour le processus en cours, et
rien n'explose.

### Publier une correction

Deux gestes, et le second n'est pas optionnel :

```bash
# 1. corriger le Blueprint, le deposer a cote du manifeste
# 2. republier le manifeste, empreintes recalculees
node examples/mobile/registry/build-manifest.mjs
```

### Le cache HTTP de la plateforme est contourné

Le client ajoute un paramètre d'unicité à chaque requête (`?_aeth=…`) et envoie `Cache-Control:
no-cache`. Ce n'est pas de la superstition : `fetch` passe par **`NSURLCache` sur iOS** et par le
**cache OkHttp sur Android**, tous deux indexés par URL, et un hébergement statique qui ne renvoie
qu'un `Last-Modified` — `python3 -m http.server`, un dépôt brut — leur laisse le droit d'inventer une
**fraîcheur heuristique**. Le manifeste est le **plan de contrôle** de la livraison : une réponse
servie depuis un cache, c'est un interrupteur d'arrêt qui n'arrête rien et une correction qui
n'arrive pas, pendant une durée que personne ne contrôle.

Le défaut a été trouvé **sur un appareil** (voir [plus bas](#la-livraison-sur-appareil)), et son
symptôme ne ressemblait pas à sa cause : serveur coupé, l'application répondait « manifeste lu ».

Le prix est connu et assumé : chaque rafraîchissement traverse le cache de bord d'un CDN. Pour un
document de quelques centaines d'octets dont dépend un retour arrière, c'est le bon échange.

L'empreinte se calcule avec un script parce qu'une empreinte écrite à la main est périmée dès la
première correction — et un manifeste dont l'empreinte ment est exactement ce que l'appareil rejette.
On passerait la soirée à déboguer une garde qui fonctionne. Un test rejoue ce calcul sur le manifeste
d'exemple livré : un manifeste périmé dans le dépôt se voit en CI.

## Porter un cas d'usage réel

Jalon 3-G. Les jalons précédents ont construit le moteur ; celui-ci répond à la seule question qui
restait : **remplace-t-il vraiment le code qu'il prétend remplacer ?** La réponse tient dans cinq
Blueprints ([`examples/mobile/reference/`](../examples/mobile/reference/)) qui portent les cinq
sources d'une application universitaire en production — quatre API tierces et un parcours
authentifiant qui remplace 323 lignes de composant WebView — et dans un guide,
[docs/mobile-migration.md](mobile-migration.md), qui dit comment on passe de l'un à l'autre.

Le jalon ne devait produire **aucun code**. C'est son intérêt : si porter un cas d'usage réel
demande de toucher au moteur, c'est que la phase n'est pas finie. Il a fallu y toucher **huit
fois**, et chaque correctif est un défaut que ni la suite de tests ni le corpus de conformance ne
voyaient, parce qu'aucun Blueprint livré n'écrivait la forme qui le déclenche — ou parce qu'aucun
test ne pouvait produire une page qui répond en retard.

| Trouvé | Correction |
|--------|------------|
| `{{ vars.api }}/{{ inputs.id }}` — une URL construite de deux variables — **levait** sur les deux moteurs : le motif de l'expression nue rebroussait jusqu'au **dernier** `}}` et lisait la chaîne entière comme une expression malformée. Un cas de conformance figeait la bizarrerie comme voulue | Le corps d'une expression nue ne peut plus contenir `}}`. Corrigé **des deux côtés le même jour** — c'est ce qui préserve l'invariant que le cas protégeait —, et le cas dit maintenant l'inverse |
| Un prédicat `where` sur un champ **imbriqué** (`item.type.code != 4`, le filtre exact d'un service réel) **levait** côté Python et **filtrait** côté embarqué : deux moteurs, deux jeux de données, aucun bruit | Le Python enveloppe désormais les dictionnaires **récursivement**. Les listes restent des listes : l'indexation est refusée par les deux grammaires, donc leurs éléments sont de toute façon inatteignables |
| `item.is_active == true` : le litéral en minuscules est un **nom indéfini** en Python brut, alors que l'évaluateur embarqué (et Jinja) l'acceptent | `true`/`false`/`none` sont liés dans la portée du prédicat. Une seule orthographe à apprendre |
| `default('', true)` — le mode booléen de Jinja, qui fait prendre le repli à **toute** valeur fausse — n'était pas implémenté côté embarqué : un `null` restait un `null` | Second argument honoré. Trouvé sur une heure de fermeture nulle quand un lieu est fermé, c'est-à-dire par une donnée réelle et non par un test |
| `options.stealth.user_agent` était documenté ici et implémenté dans le driver WebView, mais **absent du schéma partagé** : les deux moteurs refusaient tout Blueprint qui le déclarait | Ajouté au contrat, et honoré aussi par le moteur Python (contexte Playwright), sans rien activer d'autre |
| `on_timeout: "fail:LOGIN_FAILED"` posait son code sur l'exception côté Python, et **personne ne le lisait** : l'appelant ne pouvait pas distinguer « mot de passe refusé » de « la page a changé » | Le code passe en tête du message porté par le `Result` et l'événement `error`. Côté embarqué il était déjà exposé par `describeFailure(...).code` |
| La grâce que l'appelant accordait à l'agent au-delà de son échéance était un **forfait** de 2 s, alors que la dérive des minuteurs d'une page grandit avec l'attente qu'elle couvre. Sur un client web lourd, **toute** lecture revenait en silence plutôt qu'avec le message précis de l'agent | La grâce suit le budget (`callerDeadlineMs`), et le message d'un silence **nomme les sélecteurs** du step. Trouvé sur appareil uniquement : une page de test répond instantanément et ne produit jamais le cas |

Aucun de ces défauts n'était visible depuis le dépôt : il fallait écrire un Blueprint contre une
source qu'on n'a pas choisie. C'est exactement ce qu'un corpus de fixtures ne peut pas simuler, et
la raison pour laquelle ce jalon existe.

**Ce que le port n'a pas pu descendre dans un Blueprint** est aussi un résultat, écrit dans le guide
et résumé ici : le calcul (distances, tris, agrégats), toute règle qui a besoin de l'heure courante,
un filtre qui doit indexer une liste, et la relecture d'une date reçue dans un format non ISO.
Aucun n'est un manque à combler — chacun demanderait d'ajouter au vocabulaire une capacité qu'il
faudrait ensuite reproduire à l'identique dans les deux moteurs, pour une décision qui appartient à
l'application.

## Les événements

Le moteur émet exactement les types de `contracts/events.schema.json`, pour qu'une même UI consomme
les deux moteurs. L'énumération est exposée **en valeur** (`RUN_EVENT_TYPES`) et non seulement en
type : c'est ce qui permet à un test de la comparer au contrat. Le SDK `@aetherius/client` portait
précisément cette dérive — deux types manquants depuis le jalon 2-E — faute d'une telle garde ; les
deux paquets l'ont désormais.

Le bus ([`events/bus.ts`](../sdks/engine/src/events/bus.ts)) diffuse en ordre d'émission, de façon
synchrone, et **avale l'exception d'un sink** en la journalisant : le bug d'un consommateur n'est
jamais l'échec d'un run. Le logger est injectable, pour qu'une application le route vers le sien.

**Le flux est déjà une interface de progression.** Les événements portent le `step_id`, le niveau et
le message — de quoi afficher où en est un run, étape par étape, sans machine à états applicative.
C'est précisément ce qu'une application réimplémente aujourd'hui à la main. Le hook
`useAetheriusRun(client)` en est le raccourci : il rend `{ running, events, result, failure, run,
cancel }`, annule le run en cours quand l'écran se démonte, et tient en une page — s'il en fallait
plus, ce serait le signe que le flux n'est pas assez expressif.

```tsx
const { running, events, result, failure, run, cancel } = useAetheriusRun(client);
```

## Limites connues

- **JSON seulement, pas de YAML.** Le moteur Python lit les deux ; embarquer un parseur YAML pour
  lire des fichiers que l'outillage écrit toujours en JSON serait un mauvais échange.
- **Pas de système de fichiers.** `parseBlueprint` prend du texte, pas un chemin. La livraison
  (ressource embarquée, téléchargement, cache) passe par le registre du jalon 3-F, dont le magasin
  est lui aussi **injecté** : le moteur ne connaît aucun chemin.
- **La livraison ne met à jour que des Blueprints déjà embarqués, sauf sous un préfixe réservé.** Par
  défaut, un nom absent du socle est ignoré par le manifeste : c'est ce qui garantit le premier
  lancement hors ligne pour chaque Blueprint. Une application peut ouvrir une porte, explicitement et
  bornée (`allowNew`, jalon 3-H) ; ce qui entre par là **n'a pas de repli hors ligne** avant d'avoir
  été résolu une fois, et ne peut déclarer que les secrets qu'elle a écrits. Voir
  [Étendre : les noms réservés](#étendre--les-noms-réservés).
- **Un publieur compromis n'est pas couvert.** Il n'y a pas de signature d'auteur : l'intégrité
  protège le transport et le stockage, pas la source. Voir
  [le modèle de menace](#le-modèle-de-menace-et-ce-quil-ne-couvre-pas).
- **Le cache est un document unique.** Illisible, c'est la surcouche **entière** qui est perdue, et
  l'application repart sur son socle embarqué.
- **Pas de plugins.** Une action de plugin est acceptée par le moteur Python sur tous les Acts ;
  côté embarqué elle est refusée comme action inconnue.
- **Trois encodages de corps, pas plus** — UTF-8, latin-1, cp1252 ; toute autre étiquette de
  `charset` est lue en UTF-8. La table est **volontairement identique** dans les deux moteurs plutôt
  que déléguée à leurs plateformes : Python connaît des centaines de codecs, `TextDecoder` n'existe
  pas sous React Native, et les laisser faire aurait fait diverger la CI et l'appareil sur la
  première source japonaise ou cyrillique. L'élargir est une décision à prendre des deux côtés à la
  fois. Voir [Le corps en texte](#le-corps-en-texte-et-son-décodage).
- **Le verdict réseau est borné à la navigation qu'on a demandée.** Une navigation *de fond* qui
  échoue — un client web qui tente une redirection morte — n'échoue pas le step en cours : sur iOS le
  document courant reste intact, et l'opération suivante travaille dessus. C'est un choix, et il est
  expliqué avec le reste du correctif dans
  [Une source injoignable atteint `unavailable`](#une-source-injoignable-atteint-unavailable-corrigé-en-053).
  Jusqu'en 0.5.2, aucune panne réseau de l'Act II n'atteignait `unavailable` ; ce n'est plus le cas.
- **Une opération émise pendant un enchaînement de navigations se perd.** Mesuré au jalon 3-G sur
  une authentification unifiée à plusieurs sauts suivie d'un client qui pose son propre fragment :
  le host n'apprend pas tous les remplacements de document que la cascade produit, donc il ne rejoue
  pas l'opération comme il le fait pour un `DocumentLostError`, et l'échec arrive en silence. Le
  contournement tient en un `wait` après le clic, et il est **visible dans le Blueprint livré**
  plutôt que caché — parce que ce n'est pas la façon dont ce moteur attend. Détail et démonstration
  [ici](#une-lecture-qui-ne-répond-pas--lhorloge-de-lagent-nest-pas-la-vôtre).
- **Les options hors périmètre sont ignorées, pas refusées.** `options.proxy`, `options.stealth`
  (hors `user_agent`, honoré) et `options.agent` restent valides au schéma — le moteur embarqué les
  accepte et n'en fait rien. Le
  choix est délibéré (décision 8 de la phase) : refuser un Blueprint parfaitement bon parce qu'il
  porte une option destinée à l'autre moteur casserait la promesse « le même Blueprint des deux
  côtés ». La contrepartie est à connaître : un Blueprint qui compte sur `options.proxy` sortira par
  la connexion de l'appareil, sans avertissement. C'est cohérent avec la raison d'être de la phase —
  sur mobile chaque utilisateur part de sa propre connexion, le proxy n'a plus d'objet — mais cela
  reste un silence, à lever si un cas d'usage le justifie.
- **Tout est asynchrone.** Seule divergence structurelle assumée avec le moteur Python, qui est
  synchrone de bout en bout : sur appareil, rien ne peut bloquer la boucle JS. La sémantique
  observable — ordre des steps, événements émis, forme du `Result` — reste identique.
- **Un cookie posé par une *redirection* est perdu hors appareil.** `fetch` suit les redirections
  d'office et cache les réponses intermédiaires : un `Set-Cookie` porté par un 302 n'est jamais
  observable, donc jamais capturé par le jar. Sur un appareil le magasin de la plateforme le garde
  et la session tient ; sous Node, non. Un cookie posé par une réponse **directe** fonctionne des
  deux côtés, et c'est ce que fige le cas de conformance `run-session-cookie-between-steps`.
- **Le jar n'a pas de portée.** Ni domaine, ni chemin, ni expiration : les cookies d'un run valent
  pour ce run. Un Blueprint qui parle à deux hôtes sans rapport enverrait les cookies du premier au
  second.
- **`{{ env.X }}` est vide par défaut.** Le moteur Python expose `os.environ` ; un appareil n'a pas
  d'environnement. La table est celle que l'hôte fournit (`RunOptions.env`), donc une variable
  absente lève, comme n'importe quelle variable indéfinie.
- **Les secrets viennent de l'appelant ou de son resolver.** Pas de `.env`, pas de variables
  d'environnement : le trousseau de l'OS est branché par l'application (`keychainSecrets`), et le
  magasin lui-même est **injecté**. Un secret non fourni est omis, et c'est le rendu qui le signale,
  au step qui le lit.
- **Le masquage des secrets se fait par valeur.** Un « secret » d'un ou deux caractères masquerait
  ces caractères partout dans les messages. Le seuil inverse — cesser de masquer en dessous d'une
  longueur — serait une protection qui s'arrête en silence ; le bruit est préférable.
- **Une seule WebView, donc un seul run `continuum` à la fois.** Le second est refusé par une
  `DependencyError`, jamais mis en file. Les runs `vector` restent concurrents.
- **Les minuteurs sont gelés en arrière-plan sur iOS.** Un `confirm` garé n'expire pas à la seconde
  près quand l'application dort ; l'échéance est donc comparée en heure murale au moment de
  résoudre, de sorte qu'une décision tapée au retour est correctement ignorée si le délai est passé.
- **`Result.cause` est le seul ajout à la forme du `Result`**, et il ne survit pas à une
  sérialisation JSON. Voir [Le modèle d'erreur](#le-modèle-derreur).
- **Une variable de boucle `for_each` doit être un identifiant ASCII.** `str.isidentifier()` accepte
  n'importe quelle lettre Unicode côté Python ; ici la vérification est ASCII, parce que les
  échappements de propriété Unicode (`\p{L}`) ne sont pas garantis par le moteur JS mobile et
  qu'une expression régulière qui ne compile pas emporte le module au chargement. Refuser plus que
  Python est la direction sûre.
- **Ni stealth, ni proxy, ni store, ni scheduler.** Hors périmètre de la phase (décision 8). Seul le
  user-agent configurable survivra, un portail servant souvent un DOM différent aux mobiles.
- **Le sous-ensemble d'expressions et d'extraction** décrit plus haut : XPath, JSONPath hors
  sous-ensemble, filtres hors du jeu fermé, dates hors `YYYY-MM-DD`. Chacune a son cas de
  conformance — une limite qui n'est pas testée n'est pas une limite, c'est une surprise à
  retardement.
- **JSON ne distingue pas `1` de `1.0`.** Un nombre que Python tient pour un flottant s'interpole
  en `1.0` là-bas et en `1` ici. La distinction est perdue au `JSON.parse` ; aucun moteur ne peut
  la retrouver.
- **Une chaîne qui commence *et* finit par une expression est refusée** — `"{{ a }} {{ b }}"`. Le
  motif de l'expression nue va jusqu'au **dernier** `}}` et lit le tout comme une seule expression
  malformée. C'est une bizarrerie du moteur Python, reproduite volontairement : la « corriger » ici
  ferait diverger le même Blueprint d'un moteur à l'autre. Avec du texte devant
  (`"x {{ a }} {{ b }}"`), l'interpolation est normale.
- **Une sortie nommée comme une méthode de dictionnaire diverge — côté Python.** Jinja2 résout un
  **attribut avant une clé** : `{{ steps.lus.items }}` rend la *méthode* `dict.items`, et le filtre
  qui suit échoue sur un objet non itérable. Le moteur embarqué n'a ni prototypes ni méthodes
  natives à offrir (c'est la posture de sécurité du jalon 3-B, et ce qui rendra le jalon 3-F
  acceptable) : il rend la valeur. Reproduire la résolution d'attribut de Python signifierait
  exposer les méthodes natives d'un objet à un Blueprint téléchargé — un prix disproportionné pour
  une bizarrerie qu'on évite en ne nommant pas une sortie `items`, `keys`, `values` ou `get`. La
  forme `steps.lus['items']` fonctionne des deux côtés. Figé par le cas de conformance
  `expr-dict-method-shadows-key`, trouvé en écrivant les cas du jalon 3-D.
- **Act II : `upload`, `drag`, `screenshot`, le `status` de `navigate`, les nouvelles fenêtres et le
  `wait_until` de `navigate`** — voir [le tableau ci-dessus](#ce-que-lact-ii-embarqué-ne-fait-pas).
  Les trois premières sont refusées **à la validation**, avant que le run démarre.
- **Un événement clavier synthétique ne déclenche aucune action par défaut.** `press` dispatche
  `keydown`/`keypress`/`keyup` ; seul `Enter` dans un formulaire est complété par un
  `requestSubmit()` explicite. Une touche dont l'application distante attend le comportement natif
  du navigateur (`Tab` qui déplace le focus, `Escape` qui ferme une boîte de dialogue native) ne
  produira que ses événements.
- **Le locator par texte est une approximation.** Espaces normalisés, sous-chaîne insensible à la
  casse, boutons appariés par leur `value`, correspondances les plus profondes — mais pas la
  traversée du Shadow DOM de `get_by_text`. Un sélecteur CSS reste préférable quand il existe.

## Tester

```bash
make check-all      # passe Python + workspace npm (build, typage, tests des trois paquets)
make conformance    # le corpus rejoue sur les deux moteurs
make test-browser   # dont l'agent inject, joue dans un vrai Chromium
make contracts      # regenere contracts/actions.json apres une evolution du registre
```

Le corpus a **trois** exécuteurs depuis le jalon 3-D, et la raison est la frontière des paquets : un
cas `continuum` a besoin d'une WebView, que le moteur neutre n'a pas. Un cas déclare alors
`"requires": "browser"` — côté Python cela veut dire Playwright et un vrai Chromium (le cas se
skippe proprement sans l'extra `[browser]`, et le job de CI qui rejoue `make conformance` l'installe
justement pour que la comparaison ait lieu) ; côté embarqué, le cas est **délégué** à l'exécuteur de
`@aetherius/react-native`, qui rejoue le corpus **entier** sur un hôte adossé à jsdom. Les deux
exécuteurs se recouvrent au lieu de se partager le corpus : aucun cas ne peut tomber entre les deux
parce que quelqu'un l'aurait mal étiqueté, et chacun échoue si les cas `requires: browser`
disparaissent.

La **livraison** (jalons 3-F et 3-H) n'a, elle, aucun cas de conformance, et c'est délibéré : le
moteur Python n'a pas de couche de livraison — il lit des fichiers sur une machine —, il n'y a donc
aucun « même Blueprint, deux moteurs » à figer. Ce qu'elle a, ce sont ses tests miroir
(`sdks/react-native/test/delivery*.test.js`) et une garde sur le manifeste d'exemple livré, qui
rejoue le calcul d'empreinte sur **chaque** fichier publié.

L'agent injecté est en outre joué dans un **vrai Chromium** piloté depuis les tests Python
(`tests/integration/test_webview_agent.py`, marker `browser`) : la même page est lue deux fois, une
fois par l'agent qui part sur le téléphone, une fois par Playwright, et les réponses doivent
coïncider. C'est la comparaison la plus directe entre les deux implémentations — un double jsdom ne
peut pas la fournir, faute de moteur de rendu.

### Éprouver les gardes

Un socle anti-dérive ne vaut que si on l'a vu échouer. Les manipulations suivantes ont été jouées à
la livraison du jalon, et ont bien échoué ; les rejouer après une évolution du socle est le meilleur
moyen de vérifier que les gardes mordent toujours.

| Manipulation | Ce qui a échoué |
|--------------|-----------------|
| Ajouter `upload` à la table des capacités embarquées (le moteur prétend savoir le faire) | `make conformance` : `not-portable-upload` — « expected the Blueprint to be rejected, got accepted ». Et `npm test` : « `'upload'` is listed as non-portable yet the engine claims to run it ». |
| Retirer `upload` de `NOT_PORTABLE` (le refus perd sa raison) | `make conformance` : le message du refus ne contient plus `file chooser`. |
| Modifier le `summary` d'une action Python sans rejouer `make contracts` | `make test` : `test_committed_contract_matches_the_registry`. |
| Toucher `contracts/blueprint.schema.json` sans reconstruire | `npm test` (engine) : « the inlined artefacts are not stale ». |
| Écrire `new Function("return 1")` dans un fichier du moteur | `npm test` (engine) : « the engine's own output builds no code at runtime ». |
| Faire rendre `"true"` au lieu de `"True"` à `pythonStr` | `make conformance` : `expr-python-str` — « expected value `"flag: True none: None"` ». |
| Utiliser la véracité native de JavaScript dans `isTruthy` | `make conformance` : `truthy-table` (le nombre `2` et la liste `[1]` basculent). |
| Retirer le refus XPath de `portability.ts` | `make conformance` : `not-portable-xpath-extract` — « expected the Blueprint to be rejected, got accepted ». |
| Sérialiser les booléens d'un `form` à la `str()` de Python (`True` au lieu de `true`) | `make conformance` : `run-form-and-query-encoding` — le corps attendu ne correspond plus. |
| Paralléliser `for_each` avec un `Promise.all` | `make conformance` : `run-flow-if-and-for-each` — la séquence d'événements change d'ordre. |
| Interpoler la valeur d'un `fill` dans la source injectée au lieu de la passer en JSON | `npm test` (react-native) : le gabarit constant ne correspond plus, et la valeur hostile n'arrive plus intacte. |
| Faire publier `status: null` à `navigate` | `make conformance` : `run-continuum-navigate-status` — attendu `error`/`TemplateError`, obtenu un run réussi avec une donnée fausse. |
| Ajouter une opération à `OPS` sans l'ajouter à la table d'actions du driver | `npm test` (react-native) : « the operation vocabulary and the action table agree ». |
| Modifier un module de l'agent sans rejouer `npm run build` | `npm test` (react-native) : « the bundled agent is not stale ». |
| Rendre le mode strict permissif (prendre la première correspondance pour agir) | `make test-browser` : l'agent cesse de refuser ce que Playwright refuse sur la même page. |
| Faire lever le locator strict sur **zéro** correspondance | `make test-browser` : « an element that appears late is acted on » — l'agent rate un élément que Playwright clique sur la même page. |
| Résoudre l'attente sur le seul événement de chargement, sans attendre l'annonce de l'agent | `npm test` (react-native) : les cas de navigation lisent l'ancien document. |
| Publier la valeur **rendue** d'un `when` dans l'événement `step_skipped` | `npm test` (react-native) : le secret référencé par la garde se retrouve dans le flux. |
| Rendre `matchStrict` levant sur zéro correspondance (l'action cesse d'auto-attendre) | `npm test` (react-native) : « acting on nothing waits for it » échoue en 6 ms au lieu d'attendre son échéance. |
| Retyper un échec de sélecteur en `ActionError` | `npm test` (engine + react-native) : `describeFailure` le classe `engine`, et un sélecteur périmé va sur l'écran « remonter ce bug ». |
| Laisser le bail de la WebView pris après un `teardown` en échec | `npm test` (react-native) : le second run `continuum` est refusé pour toujours. |
| Faire hériter un nom **ajouté** du périmètre de secrets du socle | `npm test` (react-native) : « the scope of a new name is allowNew.secrets alone » — un portail obtient `cas_pass` parce que le socle le déclarait. |
| Cesser de purger le cache des noms que le préfixe ne couvre plus | `npm test` (react-native) : « dropping allowNew uninstalls what it let in » — l'interrupteur d'arrêt laisse en place ce qu'il avait laissé entrer. |
| Retirer l'exigence de séparateur sur le préfixe | `npm test` (react-native) : « a prefix that would cover the bundle is refused at construction » — `demo` est accepté, et couvre `demo.delivery`. |
| Traiter *tout* nom hors socle dès qu'`allowNew` est déclaré (oublier `covers`) | `npm test` (react-native) : « a name outside the prefix stays out » — le préfixe cesse d'être une borne. |
| Oublier une ré-exportation dans `index.ts` | `npm test` (react-native) : « the package's public surface is one door ». |
| Garer un `confirm` alors qu'aucune surface n'écoute | `npm test` (react-native) : « nobody listening means unattended » — le run attend au lieu de refuser tout de suite. |
| Ne pas relayer l'échec de chargement de la WebView à l'hôte | `npm test` (react-native) : « a view that cannot load the document fails the run as unreachable » — hors ligne, l'Act II retombe sur `engine` au lieu d'`unavailable`. |
| Faire échouer une opération qui perd son document au lieu de la rejouer | `npm test` (react-native) : « an operation survives the navigation a redirect causes » — plus rien ne peut attendre après un login. |
| Remettre `TemplateError` dans la famille `data` | `npm test` (engine) : un secret absent redevient « la page a changé ». |
| Rendre le silence de la page en `ActionError` au lieu du code nommé | `npm test` (react-native) : « a page that never answers produces the failure the Blueprint named » — un login refusé redevient « erreur interne ». |
| Détruire la vue à la fin d'un run `persist: true` | `npm test` (react-native) : « a persistent session keeps its view » — la session ne franchit plus la frontière du run. |
| Exiger l'agent pour décider qu'un `navigate` est un rechargement | `npm test` (react-native) : « a kept view is reloaded, not handed the URL it already shows » — le second run d'une session persistante attend un document qui ne vient jamais. |
| Ne vérifier l'empreinte d'un Blueprint livré qu'au téléchargement, pas à la lecture du cache | `npm test` (react-native) : « a cached entry tampered with after the fact is dropped when it is read ». |
| Laisser un refus (empreinte, schéma, périmètre) effacer la version distante en place | `npm test` (react-native) : les six cas de `delivery-guards` — le repli devient une régression. |
| Accepter dans le manifeste un nom que l'application n'embarque pas | `npm test` (react-native) : « a manifest entry the application does not bundle is ignored » — et le premier lancement hors ligne cesse d'être garanti. |
| Rendre le parseur de manifeste tolérant aux clés inconnues | `npm test` (react-native) : « the parser is strict… » — une faute de frappe dans `disabled` désactiverait l'interrupteur d'arrêt en silence. |
| Faire attendre le réseau à `resolve()` (rafraîchir « au passage ») | `npm test` (react-native) : « resolving never reaches the network » — un run dépendrait d'un CDN. |
| Publier un Blueprint corrigé sans rejouer `build-manifest.mjs` | `npm test` (react-native) : « the example manifest is real » — l'empreinte committée ne correspond plus au fichier. |
| Laisser `ENGINE_VERSION` diverger de `package.json` | `npm test` (engine) : « the engine announces its own package version » — `min_engine` cesserait de vouloir dire quelque chose. |
| Retirer le contournement du cache HTTP d'une requête de livraison | `npm test` (react-native) : « every delivery request defeats the platform HTTP cache » — sur un appareil, l'interrupteur d'arrêt cesse d'arrêter quoi que ce soit. |

Le harnais lui-même est testé (`tests/conformance/test_harness.py`) : un exécuteur qui rapporterait
tous les cas comme passants transformerait une suite verte en affirmation fausse.

### Parité sur le corpus livré

Au-delà du corpus de conformance, **tous les Blueprints d'`examples/`** sont passés aux deux moteurs
et leurs verdicts comparés. Au jalon 3-G : **41 fichiers, 34 identiques, 7 divergents**, et chaque
divergence est l'une de celles que le socle déclare — trois Blueprints Oracle, un Phantom, une
composition dont un step escalade vers `oracle`, une capture d'écran, et une notification (ce
dernier Blueprint touche depuis 3-B **deux** limites, et la marche s'arrête au premier refus :
l'extraction XPath). Aucune divergence inattendue, y compris pour les cinq Blueprints de référence
ajoutés par le jalon, acceptés des deux côtés.

Deux sondes plus dures ont été jouées à la livraison du jalon 3-B, hors suite automatisée :

- **Expressions.** Les **101 chaînes contenant `{{ }}`** de tous les `examples/` ont été rendues sur
  les deux moteurs, chacune contre **trois** contextes (la même variable valant tour à tour une
  date, une liste et un nombre) : **303 rendus, 0 divergence** — 278 valeurs identiques et 25 refus
  identiques, même classe d'erreur.
- **Extraction.** Les specs des exemples ont été rejouées sur les **vraies pages** qu'ils visent
  (`quotes.toscrape.com`, `books.toscrape.com`, `jsonplaceholder`) : entités décodées, espaces réels,
  `where`, `fields`, descente récursive — résultats identiques. Les deux cas **conçus pour échouer**
  (le XPath de `books-restock-notify`, un filtre JSONPath) échouent proprement côté embarqué, avec
  le message qui nomme la limite.
- **JSONPath, différentiel systématique.** Les 44 formes du sous-ensemble déclaré, sur 12 documents
  choisis pour leurs coins (listes imbriquées, clés répétées, conteneurs vides, `null`, scalaires,
  booléens) : **528 évaluations, 0 divergence**, les 12 seuls refus étant la limite déclarée `..*`.

Ces sondes ont trouvé quatre défauts que la suite de tests ne voyait pas — c'est leur raison d'être :

| Trouvé | Correction |
|--------|-----------|
| **Côté Python** : un filtre appliqué à une valeur du mauvais type (`{{ 3 \| first }}`) laissait échapper un `TypeError` brut, là où le moteur embarqué levait l'erreur typée du projet. | `render_value` enveloppe désormais toute exception en `TemplateError` — l'invariant « les erreurs sont typées et jamais avalées » vaut aussi pour celle-là. |
| `..*` ne descend pas dans les éléments d'une liste chez `jsonpath-ng`. | Sorti du sous-ensemble, refusé par son nom. |
| Une tranche à pas négatif avec bornes explicites (`$[3:0:-1]`) rendait `[]`. | `slice.indices()` de CPython reproduit à la lettre. |
| `[*]` et `.*` étaient traités comme le même opérateur, et un opérateur de liste sur un non-liste ne rendait rien. | `[*]` est une tranche, `.*` un accès de champ ; le reste suit `jsonpath-ng`, indexation levante comprise. |

Un cas mérite d'être connu : `examples/plugins/demo-notify.blueprint.json` est refusé par les deux
moteurs, mais **pour deux raisons différentes** — le moteur Python parce que le plugin de démo n'est
pas installé, le moteur embarqué parce qu'il n'a pas de système de plugins. Cet accord est
accidentel : installer le plugin le ferait diverger. C'est la limite « pas de plugins » ci-dessus,
vue depuis le corpus.

### Sondes du jalon 3-C

Le jalon 3-C exécute pour la première fois : les sondes ne comparent donc plus des verdicts mais des
**runs entiers**, jusqu'aux octets envoyés.

- **Parité d'exécution sur les exemples.** Les **12 Blueprints `vector` zéro configuration**
  d'`examples/` ont été *joués* sur les deux moteurs, contre les mêmes vraies sources
  (`jsonplaceholder`, `quotes.toscrape.com`, `api.ipify.org`, `httpbin.org`), et leurs `outputs`,
  `StepResult` et séquences d'événements comparés : **8 identiques, 4 divergents**, chaque
  divergence étant déclarée — l'action de plugin, l'extraction XPath de `books-restock-notify`,
  `http-headers-identity` qui lit les en-têtes d'empreinte que le moteur embarqué n'envoie pas
  (`options.stealth` ignorée), et `session-cookie-probe`, divergent **par construction** (voir
  ci-dessous). Aucune divergence inattendue. Un cas mérite d'être lu correctement :
  `device-ip-check` peut rendre deux valeurs d'IP différentes d'un appel à l'autre — c'est la
  **source** qui varie (NAT d'opérateur), pas les moteurs ; ses steps et sa séquence d'événements
  sont identiques.
- **Session, sur une source réelle.** `httpbin.org` : un `Set-Cookie` posé par une réponse
  **directe** est capturé et renvoyé identiquement des deux côtés. Posé par une **redirection**
  (`/cookies/set`, un 302), il est invisible pour le moteur embarqué hors appareil — d'où
  [`session-cookie-probe`](../examples/mobile/session-cookie-probe.blueprint.json), qui **rapporte
  l'asymétrie au lieu d'échouer** : `carried: true` côté Python et sur un téléphone (le magasin de
  la plateforme porte la session), `carried: false` sous Node. C'est la limite écrite plus haut,
  rendue observable — et c'est aussi pourquoi elle est une sonde et non une démonstration.
- **Conçue pour échouer : hôte injoignable** (`retries.max: 2`, recul `none`). Les deux moteurs
  échouent proprement, sans pile : `Transport error: …`, run `failed`, `outputs` vide, après
  exactement trois tentatives.
- **Conçue pour échouer : 404 réel** sur `quotes.toscrape.com` avec `expect.status: 200`. Les deux
  moteurs rendent le **même message**, extrait de corps compris.

Cette campagne a trouvé un défaut, **côté Python cette fois** :

| Trouvé | Correction |
|--------|-----------|
| **Côté Python** : une session capturée par un step n'atteignait jamais le suivant. `VectorClient` construit sa `httpx.Request` à la main (pour garder la précédence des en-têtes explicite), or httpx n'attache les cookies que dans `build_request`. Conséquence : un `CasFormLogin` se connectait, puis chaque step repartait anonyme — silencieusement. | `_request_httpx` appelle `cookies.set_cookie_header(req)` avant l'auth. Le jar respecte un en-tête `Cookie` explicite, donc le Blueprint garde le dernier mot. Gardé par `tests/unit/acts/vector/test_client.py` **et** par le cas de conformance `run-session-cookie-between-steps`. |

### Sondes du jalon 3-D

Le jalon 3-D pilote un navigateur : les sondes comparent donc l'agent injecté à Playwright **sur la
même page**, puis jouent un vrai portail authentifiant.

- **Parité d'exécution sur les exemples.** Les **11 Blueprints `continuum`** d'`examples/` ont été
  joués sur les deux moteurs contre les mêmes vraies sources (`quotes.toscrape.com`,
  `books.toscrape.com`, le CAS de l'université) : **6 identiques, 5 divergents**, et chaque
  divergence est déclarée ou attribuable au harnais :

  | Blueprint | Divergence | Nature |
  |-----------|-----------|--------|
  | `books-catalog` | refusé côté embarqué | `screenshot`, capacité non portable — refus **avant** le run |
  | `fingerprint-hardening` | échoue côté embarqué | le Blueprint lit un canvas et des signaux d'empreinte : `options.stealth` est ignorée par ce moteur (décision 8), et jsdom n'a pas de canvas |
  | `quotes-js-render` | échoue **dans le double** | jsdom n'exécute volontairement pas les scripts de page ; une sonde en Chromium réel montre l'agent lisant les mêmes 10 citations que Playwright sur `/js` |
  | `bordeaux-cas-login` | **les deux réussissent** | seule la langue de la page diffère : le double n'envoie pas d'`Accept-Language`, un appareil envoie celui du téléphone. Même forme de sortie, `peut_se_deconnecter: 1` des deux côtés |
  | `ukit-scolarite-login` | refusé des deux côtés | gabarit non exécutable (URLs `exemple.fr`, secrets absents) ; les deux échouent, à des steps différents |

- **L'agent contre Playwright, même page, vrai Chromium** (`tests/integration/test_webview_agent.py`) :
  texte détouré, nombre à virgule décimale, `html`, `attr` présent et absent, `count`, `list`,
  `each`/`fields`, élément masqué exclu de la lecture, XPath, locator par texte. Le mode strict de
  l'agent refuse exactement ce que le mode strict de Playwright refuse sur la même page.
- **Sonde réaliste dure : un portail authentifiant réel.** Le CAS de l'Université de Bordeaux, joué
  par le moteur embarqué de bout en bout (identifiants depuis `.env`, jamais dans le Blueprint) :
  `LOGIN_SUCCESS` émis, page authentifiée extraite, run `success`. Le mot de passe contient `'`,
  `!`, `@` et `#` — précisément la valeur qui casse un script écrit sous forme de gabarit de chaîne,
  et elle traverse intacte.
- **Conçue pour échouer : mauvais identifiants** sur le même portail. Échec **propre et nommé** :
  `wait_for` expire, `StepTimeoutError` avec `code: LOGIN_FAILED`, run `failed`, `outputs` vide.
- **Conçue pour échouer : capacité non portable.** `books-catalog` est refusé **à la validation**,
  avec le motif (`capturing the WebView is the host application's business`) — jamais au milieu du
  run.

Cette campagne a coûté une leçon de méthode qui mérite d'être écrite : la première sonde CAS a
rapporté un échec de connexion **du côté de l'agent**, et l'accusation était fausse — le script de
sonde lisait `.env` sans retirer les guillemets qui entourent la valeur, et envoyait donc un mot de
passe faux. Le diagnostic n'a été possible qu'en comparant les **octets postés** par les deux
pilotes : identiques, donc le fautif n'était ni l'un ni l'autre. Une sonde est du code, et un code
de sonde faux accuse du code juste.

### Sondes du jalon 3-E

Le jalon livre un **modèle d'erreur** : les sondes ne comparent donc plus seulement des sorties, mais
la **famille** dans laquelle chaque échec tombe. C'est ce déplacement d'angle qui a trouvé deux
défauts que ni la suite de tests ni les campagnes précédentes ne voyaient — le fond de la question
étant : *l'application saurait-elle quoi afficher ?*

Le Blueprint sondé est [`quotes-login-confirm`](../examples/mobile/quotes-login-confirm.blueprint.json),
joué par la façade sur un hôte adossé à jsdom, contre les **vraies** sources.

| Sonde | Résultat |
|-------|----------|
| Parcours nominal, approuvé au modal | `success`, `decision: "approved"`, `connecte: 1` — mêmes sorties que le moteur Python |
| Refusé au modal | `success`, les quatre steps gardés en `skipped` : le refus par défaut **compose**, il ne casse pas |
| Personne ne répond, modal monté | identique au refus — c'est le comportement qui arrive tout seul |
| **Aucun modal monté** | identique aussi, mais **immédiatement** : personne n'écoute, donc le run est non surveillé plutôt que garé cinq minutes devant un écran muet |
| **CAS réel de l'université**, bons identifiants | `success`, `connecte: 1`, secrets absents du flux |
| **Conçue pour échouer** : CAS réel, mauvais mot de passe | `failed`, `kind: "blocked"`, `code: LOGIN_FAILED` — exactement ce qu'un écran affiche comme « identifiants refusés » |
| **Conçue pour échouer** : hôte injoignable | `failed`, et c'est cette sonde qui a trouvé le premier défaut (ci-dessous) |
| Annulation en cours de run | `failed`, `kind: "cancelled"`, **une** libération de WebView, bail rendu |

Dans les sept cas, aucune valeur de secret n'apparaît dans le flux d'événements ni dans le message
d'échec — y compris pour le CAS, dont le mot de passe contient `'`, `!`, `@` et `#`.

Deux défauts trouvés, tous deux dans le jalon 3-D, tous deux corrigés :

| Trouvé | Correction |
|--------|-----------|
| **L'auto-attente ne s'appliquait pas à une cible absente.** `matchStrict` **levait** sur zéro correspondance, et cette exception court-circuitait le `waitFor` qui l'entourait : un `click`/`fill` sur un élément pas encore rendu échouait en **6 ms** au lieu d'attendre son échéance. Playwright attend, donc le moteur Python attend — un portail qui rend son formulaire 300 ms après le chargement marchait sur le poste et échouait sur le téléphone. C'est exactement ce que l'auto-attente « écrite une fois » existe pour empêcher. | `matchStrict` rend `null` sur zéro (« pas **encore** là », on continue d'attendre) et ne lève que sur l'ambiguïté, que l'attente ne résoudra jamais. L'asymétrie est désormais explicite dans le code et gardée par deux tests, dont un qui vérifie qu'un élément apparu tard **est** cliqué. |
| **Un sélecteur périmé se présentait comme un bug du moteur.** Toute erreur de l'agent devenait un `ActionError`, que `describeFailure` classe `engine` — « à remonter ». Or c'est l'échec Act II le plus courant en production, et sa vraie signification est « la page a changé ». **Côté Python, pire** : une temporisation Playwright (`Locator.fill: Timeout`) s'échappait telle quelle, le moteur l'enveloppait en `RunError` et la **relançait** — le run mourait au lieu d'échouer proprement, et les deux moteurs ne rendaient donc même pas le même *genre* d'issue. | Les échecs de sélecteur portent `ExtractionError` des deux côtés (`kind: "data"`, « un Blueprint à corriger ») : l'agent a un `selectorError` dédié, et le driver Python traduit une temporisation de locator en `StepTimeoutError` typée (`bridge.as_step_timeout`). Un échec **non** temporel garde son propre chemin — traduire tout aurait caché un vrai défaut derrière un message rassurant. |

Le second correctif est le plus instructif du jalon : le modèle d'erreur n'a pas seulement révélé
une mauvaise étiquette, il a révélé que **les deux moteurs ne tombaient pas dans la même catégorie
d'issue** pour le cas le plus banal. Un tableau de classification est une garde comme une autre : il
force à répondre, pour chaque erreur, à la question « quel écran ? », et une erreur sans réponse
raisonnable est une erreur mal typée.

### Sondes du jalon 3-F

Le jalon livre une **chaîne de confiance**, pas une fonctionnalité isolée : les sondes ne jouent donc
pas un Blueprint, elles jouent un **parcours de publication** — un vrai serveur statique
(`python3 -m http.server` sur `examples/mobile/registry/`), les vrais fichiers du dépôt, la vraie
source (`quotes.toscrape.com`), et la façade `Aetherius` pour exécuter ce que le registre a résolu.

| Sonde | Résultat |
|-------|----------|
| Le socle embarqué, le jour où le site change | `failed`, `kind: "rejected"` — « Expected HTTP 200, got 404 ». Un échec **propre et nommé**, pas une donnée vide |
| La correction publiée à distance | `refresh` → `updated v2`, puis run `success` : la citation d'Einstein, `livree_par: "le manifeste distant (v2)"`. **L'application s'est réparée sans être republiée** |
| Le cache survit au processus | registre neuf, **sans réseau** : v2 encore là, run `success` |
| **Conçue pour échouer** : un octet altéré sans régénérer le manifeste | `rejected` — « integrity check failed (expected 627fa03a4e59, got ae3d9d8ac3bd) », et c'est l'embarqué qui tourne |
| **Conçue pour échouer** : cache corrompu | surcouche perdue, run sur l'embarqué, aucune exception |
| Version croisée (`min_engine` > moteur installé) | `ignored` — « needs engine 0.4.0, this one is 0.1.0 », sans erreur visible |
| Interrupteur d'arrêt local (`revert()`) | retour à l'embarqué au run suivant, sans réseau |
| **Parité** : `aetherius run` sur les deux fichiers | le moteur Python rend **les mêmes sorties** pour la v2 et **le même échec** pour la v1 |

L'exfiltration, elle, est éprouvée **en test** plutôt qu'en sonde, parce qu'elle demande d'observer
ce qui n'arrive pas : un manifeste hostile publie un Blueprint qui réclame `cas_pass` et le poste sur
un serveur local ; le registre le refuse, la façade joue l'embarqué, et le serveur de l'attaquant ne
reçoit **rien**.

Ces sondes-là n'ont trouvé aucun défaut, et c'est cohérent avec la nature du jalon : tout s'y décide
sur des octets et des empreintes. Ce qui dépendait d'une plateforme, en revanche, n'a été visible que
sur un téléphone — la campagne sur appareil, elle, a trouvé un défaut structurant (ci-dessous).

### Sondes du jalon 3-G

Les sondes de ce jalon ne visent aucun bac à sable : elles jouent les **vraies sources** d'une
application en production — un CDN, deux API tierces, un serveur d'emplois du temps et
l'authentification unifiée d'une université — avec de vrais identifiants lus depuis `.env`. C'est la
seule façon de savoir si le moteur remplace le code qu'il prétend remplacer.

| Sonde | Résultat |
|-------|----------|
| Les trois Blueprints Act I zéro configuration, joués **des deux côtés** (moteur Python, puis moteur embarqué sous Node) | `success` des deux côtés, et **`outputs`, `StepResult` et séquence d'événements identiques** au JSON canonique. C'est la démonstration de parité demandée par le jalon, sur des données réelles et non sur des fixtures |
| Le parcours authentifiant (CAS → dossier administratif, puis CAS → messagerie), moteur Python | `success` des deux côtés : les cinq champs du dossier, et `non_lus: 788` extrait en **entier** par `as: "number"` — l'expression régulière du code d'origine a disparu |
| **Conçue pour échouer** : mauvais mot de passe sur le CAS réel | `failed`, `LOGIN_FAILED: wait_for timed out for selector '#gwt-uid-41'`. L'échec porte le nom que le Blueprint lui a donné, au step qui l'a rencontré |
| **Conçue pour échouer** : le relais d'emplois du temps de l'application d'origine était en panne | `failed`, « Expected HTTP 200, got 522 », avec l'URL. Un tiers mort produit un échec **nommé**, pas une liste vide — c'est exactement ce que la migration achète |
| La question qui a suivi : *pourquoi ce relais, alors que le service de l'université répond en direct ?* | Parce qu'une page web ne peut pas appeler un autre domaine sans son accord, et que l'application était une WebView. Une requête émise **nativement** ne l'est pas : le Blueprint vise le service directement, et **un serveur à héberger sort de l'architecture** |
| Le user-agent, mesuré plutôt que supposé : la même messagerie, deux UA | Chrome desktop → `/mail#1`, sélecteur présent ; Safari iOS → `/modern/`, sélecteur **absent**. La clé `options.stealth.user_agent` n'est pas un raffinement |
| Les identifiants positionnels du dossier administratif, relus | Ils correspondent toujours — et le Blueprint lit désormais **les libellés voisins** et les `assert`, de sorte qu'un décalage devienne un échec nommé au lieu d'une donnée fausse |

#### Une lecture qui ne répond pas : l'horloge de l'agent n'est pas la vôtre

La sonde la plus instructive du jalon n'a pas été trouvée sur le poste. Sur un téléphone, le
parcours authentifiant écrit **d'un seul tenant** (dossier puis messagerie) échouait toujours au même
endroit, WebView cachée **comme visible** :

```
extract timed out after 30000 ms: the page never reported back
(an off-screen WebView throttles its own timers, so the deadline is the caller's)
```

Ce n'est pas « l'élément est absent » : c'est **l'absence de réponse**. Le `wait_for` qui précède
avait pourtant trouvé le sélecteur. La sonde qui a tranché est la plus bête possible — remplacer le
sélecteur de la lecture par un `#nexistepas` garanti absent : le message n'a **pas changé**. Un
élément absent devrait produire « aucun élément ne correspond » ; il produisait un silence. Ce n'est
donc pas le DOM, c'est la **réponse** qui n'arrive pas à temps.

La cause est une **asymétrie d'horloges** que le moteur documentait sans en tirer les conséquences :
l'agent mesure sa propre échéance avec les minuteurs de la page, qu'un document occupé — ou hors
écran, donc ralenti — fait dériver, pendant que l'appelant compte en temps réel. La grâce que
l'appelant accordait au-delà de l'échéance de l'agent était **fixe** (2 s), alors que la dérive
grandit avec l'attente qu'elle couvre : généreuse pour une opération de 200 ms, insuffisante pour
une attente de 5 s. L'appelant abandonnait donc le premier, systématiquement, sur un client web
lourd.

| Trouvé | Correction |
|--------|------------|
| **Un changement de fragment était pris pour un nouveau document.** Ce client web pose `location.hash` une seconde après son premier rendu ; la vue signale une fin de chargement, le host incrémentait sa génération, et **l'agent se réinstallait par-dessus une opération en vol** — qui ne répondait alors plus jamais. C'est la cause : toute lecture sur cette page échouait, WebView cachée comme visible | Une URL qui ne diffère que par son fragment **garde la génération** (`isFragmentChange`) : l'installation redevient idempotente et l'opération en vol survit. Un rechargement garde la **même** URL, fragment compris, donc il n'est pas confondu avec un changement de fragment et gagne bien une génération neuve |
| La grâce de l'appelant était un forfait de 2 s, alors que la dérive des minuteurs grandit avec l'attente qu'elle couvre : sur un client lourd, une lecture en échec revenait en silence au lieu du « aucun élément ne correspond » de l'agent, ce qui envoie l'auteur chercher un bug du moteur plutôt que son sélecteur | La grâce **suit le budget** qu'elle couvre (`callerDeadlineMs`). Le minuteur ne se déclenche que sur un chemin déjà en échec : l'allonger ne coûte rien au chemin nominal |
| Un silence ne disait **pas sur quoi** l'opération portait. Un `extract` à cinq sorties rapportait une échéance et rien d'autre — diagnostiquer demandait d'éditer le Blueprint et de rejouer, ce qui est littéralement ce qu'a coûté ce port, deux fois | Le message **nomme les sélecteurs** du step (`extract timed out … on "#compteur", ".ligne"`) |

Le diagnostic a demandé quatre passes sur l'appareil, et chacune a déplacé le symptôme : la lecture
échouait, puis l'attente échouait, selon l'instant où le client posait son fragment. La sonde qui a
le plus appris est celle qui ne prouve rien sur la page mais tout sur le canal — un sélecteur
volontairement absent, qui aurait dû produire une réponse et n'en produisait aucune.

**Et ça ne suffisait pas.** Les correctifs ci-dessus sont réels, gardés par des tests, et ils n'ont
pas rendu cette messagerie jouable sur l'appareil. Quatre passes ont éliminé une hypothèse chacune,
sans jamais toucher la cause — jusqu'à celle qui ne demandait rien à la page mais lui demandait **ce
qu'elle était** : cinq `evaluate` immédiats, après une pause fixe.

Ils ont tous répondu, avec exactement les valeurs du poste : `/mail#1`, `Zimbra: Réception (788)`,
1902 nœuds portant un identifiant, et le compteur **présent et lisible**. Autrement dit : agent
vivant, page correcte, élément là. Il ne restait alors qu'une variable — la sonde attendait **15 s
sans rien demander**, là où le Blueprint lançait son attente juste après le clic, c'est-à-dire
pendant la cascade `CAS → preauth → /mail → pose du fragment`.

**Une opération émise pendant un enchaînement de navigations se perd**, et elle se perd en silence :
le host n'apprend pas tous les remplacements de document que cette cascade produit, donc il ne rejoue
pas l'opération comme il le fait pour un `DocumentLostError`. Laisser la page arriver avant de
l'interroger suffit, et c'est ce que fait le Blueprint livré :

```json
{ "action": "click",   "selector": "input[type=submit]" },
{ "action": "wait",    "ms": 15000 },
{ "action": "wait_for", "selector": "#zti__main_Mail__2_textCell", "timeout_ms": 30000,
  "on_timeout": "fail:MESSAGERIE_INDISPONIBLE" }
```

Vérifié sur l'appareil : `success`, `Réception (788)`, `non_lus: 788` — identique au moteur Python.

Il faut dire ce que cette pause est et ce qu'elle n'est pas. Ce n'est **pas** la façon dont ce moteur
attend : l'auto-attente existe précisément pour ne pas semer des délais fixes, et c'est l'argument
central du jalon 3-D. C'est un **contournement d'une limite du moteur**, écrit ici pour qu'on ne le
prenne pas pour un motif à imiter : idéalement le host absorberait cette cascade tout seul, comme il
absorbe une navigation isolée. Le faire demande de reproduire la séquence exacte de signaux qu'une
plateforme mobile émet pendant une redirection multi-sauts — une instrumentation sur appareil qui
sort du périmètre de ce jalon. La limite est donc **nommée, mesurée, et contournée en une ligne
visible** plutôt que masquée.

Trois conséquences côté Blueprint, en plus des correctifs :

- **Une lecture qui suit un `wait_for` porte son propre `timeout_ms`, court** (5 s dans les
  Blueprints livrés). Elle n'a rien à attendre : la présence vient d'être prouvée. Le budget court
  garantit que l'agent réponde **avant** l'échéance de l'appelant, donc qu'un échec soit *lisible*
  au lieu d'être un silence.
- **Un enchaînement d'authentification à plusieurs sauts se laisse arriver avant d'être
  interrogé.** La règle vaut au-delà de ce portail : dès qu'un clic déclenche une redirection en
  cascade suivie d'un client qui pose son propre fragment, la première opération qui suit part dans
  le vide.
- **Le parcours est scindé en deux Blueprints** — l'identité et la messagerie —, ce qui n'est pas un
  contournement : c'est exactement la distinction que l'application d'origine fait entre son
  parcours « froid » et son parcours « chaud ». Chacun ouvre son service, qui rebondit lui-même sur
  l'authentification unifiée. Un Blueprint de référence long à cause d'un enchaînement que
  l'application ne fait jamais d'un bloc n'aurait rien démontré de réel.

La limite qui reste, écrite ici parce qu'elle est structurelle : **sur un appareil, l'agent n'est
pas une horloge fiable**. Le moteur le sait déjà (`NoAnswerError` existe pour ça, et le driver la
renomme en l'échec que le Blueprint a nommé), mais un step **sans** `on_timeout` — une lecture, une
évaluation — n'a pas de nom à porter et retombe donc sur « la page a changé ». C'est le bon défaut
par défaut ; le budget court et la grâce proportionnelle sont ce qui le rend rare, et le message
nomme désormais le sélecteur pour que le rare reste diagnosticable.

Ces sondes ont trouvé **huit défauts** que ni la suite de tests ni le corpus ne voyaient, tous
détaillés avec leur correctif dans [Porter un cas d'usage réel](#porter-un-cas-dusage-réel). Deux
méritent d'être répétés ici, parce qu'ils disent quelque chose sur la méthode :

- une URL construite de **deux variables** ne se rendait pas — la forme la plus banale qui soit,
  qu'aucun Blueprint livré n'utilisait, et qu'un cas de conformance figeait comme un comportement
  voulu ;
- un prédicat sur un champ **imbriqué** rendait des données différentes selon le moteur. Le corpus
  ne l'a pas vu parce qu'aucun cas n'imbriquait : un corpus ne protège que des formes qu'il écrit.

### Sondes du jalon 3-H

Mêmes conditions qu'au jalon 3-F, et pour la même raison : ce jalon ne livre pas une fonctionnalité
isolée mais un **parcours de publication**. Un vrai serveur statique
(`python3 -m http.server` sur `examples/mobile/registry/`), les vrais fichiers du dépôt, la vraie
source (`quotes.toscrape.com`), un cache **sur le disque**, et la façade `Aetherius` pour exécuter ce
que le registre a résolu. L'application de la sonde n'embarque **rien** : le portail n'existe que
s'il est livré.

| Sonde | Résultat |
|-------|----------|
| `resolve()` avant tout rafraîchissement | `BlueprintLoadError` — « it is covered by `'mobile.portail.'` but no manifest has delivered it yet ». `list()` rend `[]` : il n'y a pas de socle, et le message le dit plutôt que de le laisser deviner |
| `refresh()` sur le manifeste qui publie **les deux** | `updated mobile.portail.demo v1` **et** `ignored mobile.autre.demo — not bundled, and outside the reserved prefix 'mobile.portail.'`. Deux lignes du **même** rapport : c'est le contraste qui montre la garde |
| Le portail ajouté, joué par la façade | `origin: "remote"`, run `success`, `livre_par: "le préfixe réservé (jalon 3-H)"` et la citation de Jane Austen. **Un Blueprint que le binaire ne contient pas a tourné sur l'appareil** |
| Le nom hors préfixe, après rafraîchissement | toujours `BlueprintLoadError` — « outside `'mobile.portail.'` ». Le rafraîchissement ne l'a pas rendu résoluble |
| Registre neuf sur le même magasin, **sans réseau** (un `fetch` qui lève) | `remote v1` : le portail a franchi la frontière du processus, sans socle et sans CDN |
| **Interrupteur d'arrêt** : `allowNew` retiré, registre neuf sur le même magasin | le portail est **désinstallé** — `resolve` refuse, `list()` rend `[]`, aucune requête |
| La même porte **rouverte** ensuite, toujours sans réseau | rien à retrouver : la purge est **durable**, pas une mise en veille |
| **Conçue pour échouer** : un portail publié en déclarant `cas_pass`, manifeste régénéré proprement | `rejected` — « declares secrets the application does not allow: cas_pass (allowed: none) ». Le fichier est arrivé entier et signé juste ; c'est le périmètre qui a mordu |
| **Conçue pour échouer** : un octet ajouté au portail **après** la publication du manifeste | `rejected` — « integrity check failed (expected d0421a79f932, got c33b08698214) ». Le journal du serveur montre les **deux** requêtes (`GET /manifest.json?_aeth=…`, `GET /portail-demo.blueprint.json?_aeth=…`) : le fichier est arrivé, c'est la garde qui l'a refusé |
| **Parité** : `aetherius run` sur les deux fichiers publiés | le moteur Python les joue **tous les deux**, et rend les mêmes sorties. Ce qui les sépare n'est pas leur contenu, c'est le nom sous lequel ils sont publiés |

Ces sondes n'ont trouvé aucun défaut, et c'est cohérent avec la nature du jalon : comme en 3-F, tout
s'y décide sur des octets, des noms et des empreintes — il n'y a pas de plateforme dans la boucle.
Les quatre gardes ont en revanche été **vues échouer** par mutation du code (lignes ajoutées au
tableau [Éprouver les gardes](#éprouver-les-gardes)), ce qui est la seule preuve qu'elles mordent :
faire hériter un nom ajouté du périmètre du socle, cesser de purger, retirer l'exigence de
séparateur, oublier `covers`.

### Sondes du correctif 0.5.3 — une source injoignable

La sonde tient dans un fichier, [`unreachable-probe`](../examples/mobile/unreachable-probe.blueprint.json),
et elle est **conçue pour échouer** : c'est son seul emploi. Elle vise le port 1 du loopback de
l'appareil — jamais servi, refusé par les moteurs de rendu — donc elle est déterministe et **remplace
le passage en mode avion** du parcours précédent : rien à changer sur le téléphone.

| Sonde | Résultat |
|-------|----------|
| **Première passe, sonde sur le port 1** | `PAGE_ABSENTE`. Le correctif était en place et gardé ; c'est cet échec qui a désigné la **cause 2** — l'hôte n'avait rien reçu. La sonde qui apprend le plus est celle qui échoue pour une raison qu'on n'avait pas prévue |
| La sonde, sur iPhone, port 4 | `SERVICE INDISPONIBLE`, « Réessayer peut aboutir ». La progression tient en quatre lignes : `[progress]`, `[step_started] nav`, `[error] nav the WebView could not load the document: Could not connect to the server.`, `[done] failed`. **Aucune ligne `DIAGNOSTIC`** : le step suivant n'a jamais démarré |
| Relancée, plusieurs fois de suite | Identique à chaque lancement — la reprise n'hérite de rien et n'attend pas son échéance |
| L'URL remplacée par un nom qui ne résout pas (`.invalid`) | *(non joué sur appareil ; le chemin est gardé par le test d'hôte « a load that starts and never comes back »)* |
| Non-régression : `webview-quotes`, `reference-sso`, `reference-messagerie` | Inchangés, sorties identiques au moteur Python. Ce sont les parcours qui enchaînent le plus de signaux de chargement |
| Non-régression : le CAS réel avec un mauvais mot de passe | Pastille `LOGIN_FAILED`, **pas** « Service indisponible » : le verdict réseau n'est pas devenu gourmand |
| **Parité** : `aetherius run` sur le même fichier | `failed`, « navigate: the source is unreachable (http://127.0.0.1:4/) — Page.goto: net::ERR_CONNECTION_REFUSED », et **un seul `StepResult`** : `nav` |

Deux choses apprises, et elles valent au-delà de ce défaut.

**Un double qui n'émet pas les signaux d'une plateforme ne peut rien garder.** Le corpus jouait ce
chemin depuis deux jalons et le déclarait vert, parce que le double montait une page d'erreur sans
jamais dire qu'un chargement avait échoué — exactement la moitié de la séquence qui contient le bug.
Le double émet désormais `onLoadFailed` avant `onDocumentLoaded`, et le cas de conformance mord.

**Une sonde qui échoue pour une raison qu'on n'avait pas prévue vaut mieux qu'une sonde qui passe.**
La première passe a rendu `PAGE_ABSENTE` alors que le correctif était en place et gardé par trois
tests — et c'est ce qui a désigné la cause 2, qui n'est pas dans ce moteur. Une sonde écrite pour
confirmer un correctif n'aurait rien appris ; celle-ci était écrite pour **éprouver le comportement
réel**, et l'écart entre les deux est tout l'objet de la règle des sondes dures
([CONTRIBUTING](../CONTRIBUTING.md#définition-de--terminé-), point 5).

### Sondes du jalon 3-I

Le jalon ajoute une valeur d'énumération, donc les sondes ne visent pas une fonctionnalité mais une
**égalité** : le même corps, deux moteurs, la même chaîne. Elles sont donc systématiquement jouées
**des deux côtés** — `aetherius run` puis le moteur embarqué sous Node —, sur des sources réelles.

| Sonde | Résultat |
|-------|----------|
| [`ical-planning-text`](../examples/vector/ical-planning-text.blueprint.json) — export iCal anonyme d'ADE, `text/calendar;charset=UTF-8` | `success` des deux côtés, `caracteres: 21461` **identiques**, `accents: true`. 21 592 octets pour 21 461 caractères : les accents sont passés **par** le décodeur, pas à côté |
| [`ical-large-body-probe`](../examples/mobile/ical-large-body-probe.blueprint.json) — ~80 Ko, second serveur | `success` des deux côtés, `caracteres: 80712` identiques |
| **Conçue pour échouer** : [`ical-error-page-probe`](../examples/mobile/ical-error-page-probe.blueprint.json) — le même export **sans paramètres**, qui répond 500 avec une page HTML déclarée `ISO-8859-1` | `failed` au step `shape` (`ICAL_INVALID`), ligne `DIAGNOSTIC` jamais atteinte, **et le même échec mot pour mot des deux côtés**. Sans la garde de forme, ce run aurait « réussi » en rendant un calendrier vide |
| Le corps mal étiqueté, en conformance plutôt qu'en sonde | Aucune source publique française mesurée ne sert d'accents en ISO-8859-1 (la page d'erreur d'ADE le déclare mais reste ASCII) : le cas est donc **servi par les serveurs de fixtures** des deux harnais (`run/18-text-body-and-charset`), qui est le seul endroit où l'on contrôle les octets **et** l'étiquette |

L'aspérité relevée, antérieure au jalon et laissée telle quelle : l'action `assert` signale son échec
via `StatusAssertionError`, donc le message porte un préfixe `Expected HTTP 1, got 0 — <assert>`
avant la vraie raison. Identique sur les deux moteurs ; le changer toucherait le contrat d'erreur
d'une action qui n'est pas le sujet de ce jalon.

### Sur appareil

Le point 5 de [CONTRIBUTING](../CONTRIBUTING.md#définition-de--terminé-) — « le vrai run, pas
seulement les tests » — se joue ici sur un téléphone, via l'application de démonstration
d'[`examples/mobile/`](../examples/mobile/README.md) (Expo + Expo Go, aucun build natif).

**Joué à la livraison du jalon** : iPhone sous iOS, Expo Go **SDK 54**, téléphone en données
cellulaires et poste de développement en Wi-Fi (`expo start --tunnel`, seul mode qui traverse deux
réseaux). Les quatre Blueprints ont tourné, tous `success` :

| Blueprint | Sur l'appareil | Ce que rend le moteur Python |
|-----------|----------------|------------------------------|
| `quotes-watch` | la citation d'Einstein, `quotes_on_page: 10` | identique |
| `jsonplaceholder-flow` | `branch: "then"`, `user_count: 3`, et les événements `walk.each_user[0].announce` → `[1]` → `[2]` dans cet ordre | **séquence identique**, chemins imbriqués compris |
| `device-ip-check` | `92.184.98.145` | `92.184.98.101` depuis le poste |
| `session-cookie-probe` | `carried: true` | `true` aussi — et `false` sous Node |
| `unreachable-probe` *(0.5.3)* | **`failed`** — « Service indisponible », `[error]` sur `nav` | `failed` aussi, `ERR_CONNECTION_REFUSED`, même step. La seule carte du banc dont le succès est un échec |

La dernière ligne est celle qui comptait le plus : elle **vérifie** la stratégie de cookies au lieu
de la supposer. Le magasin de la plateforme porte bien la session à travers la redirection, donc le
jar opportuniste n'a rien à capturer sur appareil et ne double aucun cookie — ce que la conception
affirmait, et qu'aucun test hors appareil ne pouvait montrer.

La séquence d'événements du flux imbriqué est la vérification la plus parlante : mêmes `step_id`,
même ordre, boucle bien séquentielle — une application de progression écrite contre un moteur
fonctionne contre l'autre.

Une nuance, parce qu'elle change ce que la sonde prouve : les deux adresses diffèrent, mais
partagent leur `/24`. Le poste sortait par le **même opérateur** que le téléphone (box cellulaire).
La requête part donc bien de l'appareil — l'application n'a ni daemon ni serveur, le moteur tourne
dans Hermes —, mais la démonstration « deux réseaux vraiment distincts » demanderait un poste sur
une connexion filaire d'un autre opérateur.

**Campagne du jalon 3-I** (mêmes conditions : iPhone, Expo Go SDK 54, tunnel, téléphone en
cellulaire). Elle a une raison d'être précise : la lecture en octets emprunte sur l'appareil un
chemin que Node n'a pas — blob, base64, pont natif — et c'est le seul endroit où il s'observe.

| Carte | Sur l'appareil | Ce que rend le moteur Python |
|-------|----------------|------------------------------|
| `ical-planning-text` (export ADE, `text/calendar;charset=UTF-8`) | `success`, `caracteres: 21461`, `accents: true` | **identique au caractère près** — 21 592 octets pour 21 461 caractères : le pont d'octets et le décodeur UTF-8 embarqué rendent exactement ce que rend CPython |
| `ical-large-body-probe` (~80 Ko, second serveur) | `success`, `caracteres: 80712`, `accents: true` | identique |
| **Conçue pour échouer** : `ical-error-page-probe` | **`failed`** au step `shape` — `[step_started] cal`, `[step_finished] cal`, `[step_started] shape`, `[error] shape … ICAL_INVALID`, `[done] failed`. **Aucune ligne `DIAGNOSTIC`** | `failed` aussi, même step, même message |

La lecture en octets est donc **vérifiée** plutôt que supposée : `response.arrayBuffer()` existe bien
dans le `fetch` de React Native, et un corps de 80 Ko le traverse sans perdre un caractère.

Deux aspérités observées à l'écran, antérieures au jalon et laissées telles quelles parce qu'elles
appartiennent au contrat d'erreur de l'action `assert`, pas à l'extraction : le message porte le
préfixe `Expected HTTP 1, got 0 — <assert>` avant sa vraie raison, et la façade classe l'échec en
famille `rejected` **avec `retryable: true`** (« Réessayer peut aboutir »). Le libellé de la famille
est juste — la source a bien répondu, mais pas comme le Blueprint l'exigeait —, l'invitation à
réessayer l'est moins pour une garde de forme, qui échouera identiquement. Les deux tiennent au fait
qu'`assert` lève une `StatusAssertionError` ; le corriger toucherait une action hors du périmètre de
ce jalon, et les deux moteurs de la même façon.

**Ce qui reste à observer sur un appareil**, et qui est écrit ici plutôt que supposé : le corps de
requête `form`/`json`, les reprises et le délai n'ont été éprouvés que sous Node et en test. Rien ne
laisse penser qu'ils diffèrent — ils ne touchent pas à la plateforme —, mais ils n'ont pas été vus
tourner sur un téléphone. Depuis le jalon 3-E, l'application de démonstration embarque
[`ukit-inf601a5-test`](../examples/vector/ukit-inf601a5-test.blueprint.json) précisément pour cela :
c'est le seul Blueprint du banc qui POSTe un corps `form`, clé répétée `federationIds[]` comprise,
contre un serveur réel.

#### Act II, sur appareil

L'application embarque `webview-quotes` et monte `<AetheriusWebView />` : le parcours à jouer est
navigation → attente du DOM → extraction typée (dont `each`/`fields`) → JS injecté, sur
`quotes.toscrape.com`, à comparer avec `aetherius run examples/mobile/webview-quotes.blueprint.json`.

**Joué à la livraison du jalon** : iPhone sous iOS, Expo Go SDK 54, téléphone en données
cellulaires. `webview-quotes` rend `success` avec exactement les sorties du moteur Python — la
citation d'Einstein, `citations_sur_la_page: 10`, les quatre étiquettes de la première citation, les
dix enregistrements `each`/`fields`, et `auteurs_comptes_par_js: 10` par le JS injecté. **Le mode
debug est vérifié** : le run donne le même résultat WebView visible ou cachée, et la vue affichée
montre bien la page défiler.

Trois crashs natifs ont été traversés pour y arriver, tous consignés dans
[`examples/mobile/README.md`](../examples/mobile/README.md) avec leur symptôme : deux copies de
React, une WebView cachée par le mauvais style, et un montage sur `about:blank`. Aucun ne se
manifestait par un message JavaScript, et c'est **la bissection par une WebView nue** qui a désigné
le vrai coupable après deux correctifs plausibles qui n'étaient pas la cause.

**Ce qui reste à observer sur un appareil**, écrit comme tel plutôt que supposé :

1. **la persistance de session d'un run au suivant** — `options.session.persist: true`, se connecter
   une fois, puis relire l'état : le second run doit trouver la session déjà ouverte, là où
   `persist: false` la redemande à chaque fois ;
2. **le parcours authentifiant réel sur le réseau du téléphone** — la sonde CAS jouée ici depuis un
   poste, rejouée depuis l'appareil.

Les deux sont **outillés** depuis le jalon 3-E : l'application de démonstration porte une bascule
« garder la session » (qui écrase `options.session.persist` au lancement) et une carte
`bordeaux-cas-login` dont les identifiants viennent du trousseau. Le second est **joué** (voir la
campagne ci-dessous).

> **Ce que `persist` achète, et ce qu'il ne peut pas acheter.** La formulation d'origine de ce point
> — « entre deux lancements de l'application » — était trop forte, et une sonde sur appareil l'a
> montré. Un site qui pose un **cookie de session** (`Set-Cookie` sans `Expires` ni `Max-Age`, ce que
> fait `quotes.toscrape.com`) le perd quand le processus meurt : c'est la sémantique HTTP, pas une
> limite du moteur. `persist: true` fait donc vivre la session **d'un run au suivant**, dans la vie
> de l'application ; seul un cookie daté par le serveur survit à un redémarrage, et aucun moteur ne
> peut inventer une date qui n'a pas été envoyée. L'observable honnête est un A/B au sein d'un même
> lancement : `persist: true` → la session tient entre deux runs, `persist: false` → la vue incognito
> repart propre.

#### La surface applicative, sur appareil

L'application de démonstration passe par la façade depuis le jalon 3-E : elle range les identifiants
dans `expo-secure-store`, monte `<AetheriusConfirm />`, affiche la progression issue du flux et
traduit chaque échec par `describeFailure`. Le parcours à jouer est
[`quotes-login-confirm`](../examples/mobile/quotes-login-confirm.blueprint.json), à comparer avec
`aetherius run examples/mobile/quotes-login-confirm.blueprint.json --secret quotes_user=demo
--secret quotes_pass=demo`.

Ce qu'il faut voir, et qui n'a de sens que sur un téléphone :

1. **le modal réel** — approuver fait repartir le run, refuser saute les steps gardés sans faire
   échouer le run ;
2. **l'expiration en arrière-plan** — ne pas répondre, mettre l'application en arrière-plan, revenir :
   la décision doit être un refus, et un tap tardif ne doit rien faire ;
3. **le trousseau entre deux lancements** — saisir une fois, tuer l'application, relancer : le run
   repart sans ressaisie ;
4. **l'annulation** — lancer avec `options.debug`, quitter l'écran : la WebView visible disparaît ;
5. **les trois issues** — succès, `LOGIN_FAILED` sur de mauvais identifiants, et mode avion, qui doit
   donner « service indisponible » et **non** un résultat vide.

**Première campagne sur iPhone** (iOS, Expo Go SDK 54, téléphone en 5G, poste sur le partage de
connexion du téléphone — le Wi-Fi de la résidence isole ses clients et le tunnel ngrok était
indisponible) :

| Blueprint | Observé |
|-----------|---------|
| `webview-quotes`, `quotes-watch`, `jsonplaceholder-flow`, `device-ip-check` | `success`, sorties identiques au moteur Python |
| `ukit-planning` | `success`, la semaine d'événements du vrai serveur ADE — **ferme le point laissé ouvert au jalon 3-C** (le corps `form`, clé répétée comprise, n'avait jamais tourné sur un téléphone) |
| `quotes-login-confirm` | le **modal s'ouvre**, l'approbation repart, et l'événement `input_requested` affiche `Envoyer les identifiants de [secret]` — **la rédaction fonctionne sur appareil** ; le run échouait ensuite (défaut 1 ci-dessous) |
| `bordeaux-cas-login` | échec sur un secret absent du trousseau — révélateur, mais pour la mauvaise raison (défaut 2 ci-dessous) |
| `session-persist-probe` | `connecte: 0` sans session : la ligne de base est bonne, la séquence complète reste à jouer |
| `session-cookie-probe` | `502 Bad Gateway` de `httpbin.org` — **panne du tiers**, pas du moteur. À noter : le modèle d'erreur l'a classé « réponse inattendue », ce qui est exactement juste |

**Seconde passe, après les deux correctifs** — c'est elle qui les valide sur l'appareil, et non en test :

| Blueprint | Observé |
|-----------|---------|
| `quotes-login-confirm` | **`success`**, `decision: "approved"`, `connecte: 1`, `LOGIN_SUCCESS` émis. Le run traverse désormais la redirection du login de bout en bout — **le défaut 1 est vérifié corrigé là où il s'était manifesté** |
| `bordeaux-cas-login` | **`success`** sur le CAS de l'université, depuis la 5G du téléphone : `peut_se_deconnecter: 1` et le message d'accueil authentifié. **Ferme le point laissé ouvert au jalon 3-D** (« le parcours authentifiant réel sur le réseau de l'appareil »), et exerce les secrets du trousseau de bout en bout |
| `session-cookie-probe` | rejoué une fois `httpbin.org` revenu : **`carried: true`**, `SESSION_KEPT` émis. Le magasin de cookies de la plateforme porte bien la session **à travers une redirection**, là où Node rend `false` — l'asymétrie déclarée au jalon 3-C, observée |

Deux défauts trouvés à la première passe, tous deux invisibles hors appareil, tous deux corrigés :

| Trouvé | Correction |
|--------|-----------|
| **Une redirection tuait l'opération suivante.** `quotes-login-confirm` : le `click` soumet le formulaire, le portail répond **302**, donc la vue charge **deux fois**. Le `wait_for` en vol perdait son document et le run mourait sur `the operation lost its document`. Conséquence réelle : **aucun Blueprint ne pouvait attendre quoi que ce soit après un login**. Le double jsdom ne pouvait pas le voir — il suit les redirections lui-même avant d'annoncer le chargement, donc il ne produit jamais deux documents. | Une opération qui perd son document est **rejouée sur le nouveau**, dans la limite du délai du step (`BridgedHost.throughNavigations`). Le cas est distingué par une classe dédiée, `DocumentLostError`, et non par un message : c'est le seul échec dont on peut se remettre. Gardé par deux tests, dont un qui vérifie que le rejeu reste borné par l'échéance. |
| **Un secret absent affichait « la page a changé ».** `TemplateError` partageait la famille `data` avec `ExtractionError`. Or la page allait très bien : c'est le trousseau qui était vide. Les deux appellent des écrans opposés. | Famille `config` à part — « une donnée d'entrée manque ». Et l'application de démonstration **lit le trousseau** avant de lancer : elle dit désormais si les secrets déclarés y sont, au lieu de laisser découvrir l'absence au milieu d'un run. |

Le premier défaut est le plus instructif de la phase : il ne se manifeste que là où une vraie
WebView suit une vraie redirection, et il touchait le parcours le plus banal de l'Act II. Aucun test
hors appareil ne pouvait le produire — c'est exactement ce que le point 5 de CONTRIBUTING existe
pour attraper.

**Troisième passe : les variantes.** Elle a confirmé le refus au modal (run `success`, steps gardés
`skipped`), l'expiration pendant que l'application dort — au retour, le modal a disparu et le run
est déjà reparti en refus, ce que la comparaison d'échéance en heure murale devait produire — et le
mode avion (« service indisponible », `Transport error` dedans). Elle a aussi trouvé **deux
contraintes de plateforme** que rien hors appareil ne pouvait révéler :

| Trouvé | Correction |
|--------|-----------|
| **Un login refusé arrivait en « erreur interne ».** Sur le CAS avec un mauvais mot de passe, `wait_for` expirait mais **l'agent n'a jamais répondu** : iOS *throttle*, et peut suspendre, les minuteurs d'une WKWebView hors écran — et ce moteur l'y garde délibérément. Seule l'échéance de l'appelant s'est déclenchée, en `ActionError`, donc `engine` : « à remonter », pour un mot de passe faux. | **L'appelant est la seule horloge fiable.** Un silence au-delà de son échéance devient l'expiration de l'attente, **avec le code que le Blueprint a nommé** (`fail:LOGIN_FAILED`). Classe dédiée `NoAnswerError` plutôt qu'un message à reconnaître ; l'agent garde la main quand il répond, lui. |
| **`persist: true` ne persistait rien.** Un run se connectait, le suivant repartait anonyme. La vue était détruite à la fin de chaque run, donc recréée — et un **cookie de session** (sans `Expires`, ce que pose un login) ne franchit pas cette frontière : il vit avec le contexte de navigation, pas sur disque. | **Une session persistante garde sa vue.** `dispose()` ne la libère que pour `persist: false`. Le coût est écrit : une WebView cachée survit au run tant que les options ne changent pas. **Et garder la vue a un corollaire que la première tentative a manqué** : elle affiche encore sa dernière page, donc un `navigate` vers cette même page ne changeait rien — aucun chargement ne démarrait, et le run attendait un document jamais annoncé. Le test de `navigate` porte désormais sur l'URL seule (« cette vue y est-elle déjà ? »), et non sur la présence de l'agent, qui est justement absent entre deux runs. |

Deux tests gardent ces comportements, et une procédure de vérification fausse a été corrigée au
passage : demander qu'une session survive à la **mort de l'application** était impossible pour un
cookie de session, quel que soit le moteur.

**Reste à observer sur un appareil**, écrit comme tel — ce sont les *variantes* des parcours déjà
joués, et chacune touche la plateforme :

**Rien ne reste.** La campagne est complète : refus au modal, expiration pendant que l'application
dort, mauvais identifiants sur le CAS (`LOGIN_FAILED` avec sa pastille — ce qui **valide sur
l'appareil** le correctif d'horloge), mode avion, annulation, et l'A/B de persistance de session
(`connecte: 1` avec la bascule, `0` sans).

Deux de ces vérifications ont demandé de corriger le **banc** plutôt que le moteur, et la leçon est
la même les deux fois : le contrôle d'annulation était *recouvert*, par le modal d'abord, par la
WebView du mode debug ensuite. Il est désormais **flottant et rendu après la WebView**, donc
au-dessus d'elle. La persistance, elle, a demandé **deux** correctifs successifs : la vue n'était pas
gardée, puis — une fois gardée — un `navigate` vers la page qu'elle affichait déjà ne déclenchait
aucun chargement, et le run attendait un document qui ne venait jamais.

L'application de démonstration marque chaque carte `vérifié` / `partiel` / `à faire` / `bloqué`, et
la note dit ce qui a déjà été vu — précisément pour qu'on ne s'y perde pas d'une passe à l'autre.

#### La livraison, sur appareil

Le jalon 3-F ajoute une carte **Livraison** et son panneau : l'origine du Blueprint (embarqué ou
distant, avec sa version), une URL de manifeste éditable, **Rafraîchir** et **Revenir à l'embarqué**.
Ce qui ne se vérifie que là : que la correction franchit vraiment la frontière du binaire, et qu'elle
**survit à un redémarrage de l'application** — le cache est un magasin de plateforme, pas une
variable.

La procédure complète (servir le manifeste, publier une correction, la voir prise en compte,
déclencher l'interrupteur d'arrêt) est dans
[`examples/mobile/README.md`](../examples/mobile/README.md#la-livraison-des-blueprints).

**Campagne sur iPhone** (iOS, Expo Go SDK 54, téléphone en 5G, poste sur le partage de connexion du
téléphone, manifeste servi par `python3 -m http.server`). Elle a demandé **deux passes**, la première
ayant trouvé le défaut ci-dessous ; les deux ensemble couvrent le parcours entier.

| Parcours | Observé |
|----------|---------|
| Le socle embarqué, cassé | **« Réponse inattendue »** avec le 404 nommé, `embarque · v1` — pas un résultat vide |
| Rafraîchir puis rejouer | `manifeste lu`, `updated v2`, `distant · v2`, run **`success`** : la citation d'Einstein et `livree_par: "le manifeste distant (v2)"`. **L'application s'est réparée sans être republiée** |
| Tuer l'application, relancer, rejouer **sans rafraîchir** | `distant · v2` dès l'ouverture du panneau, run `success` : le cache a franchi la frontière du processus |
| Revenir à l'embarqué | `embarque · v1` immédiatement, sans réseau, et le run suivant recasse |
| **CDN coupé** (serveur arrêté), Rafraîchir puis rejouer | `manifeste non lu : Network request failed`, panneau toujours `distant · v2`, run **`success`** — une panne de CDN n'est pas une panne d'application |
| **Mode avion** | `manifeste non lu` ; la résolution rend toujours `distant · v2` **sans réseau** ; et le run échoue en **« Service indisponible »** (`Transport error`), parce que la source aussi est injoignable — deux échecs distincts, correctement nommés |
| **Fichier altéré sans régénérer le manifeste** | `rejected · integrity check failed (expected 627fa03a4e59, got ee574e7394af)`, panneau resté `embarque · v1`. Le serveur a bien vu passer **les deux** requêtes (`GET /manifest.json?_aeth=…`, `GET /delivery-quotes.v2.blueprint.json?_aeth=…`) : le fichier est arrivé, c'est la garde qui l'a refusé |
| **Publier une vraie correction** (éditer + `build-manifest.mjs`) | `updated v2`, run `success` avec `livree_par: "corrige en direct depuis le poste"` |
| **Interrupteur d'arrêt distant** (`"disabled": true`) | `ignored · disabled by the manifest`, retour à `embarque · v1`, et le run suivant recasse |

Les traces du serveur valent d'être lues : le paramètre `?_aeth=…` y est visible sur **chaque**
requête, ce qui vérifie sur l'appareil le correctif ci-dessous — et pas seulement en test.

Un défaut trouvé, et il ne pouvait l'être qu'ici :

| Trouvé | Correction |
|--------|-----------|
| **La plateforme servait le manifeste depuis son propre cache HTTP.** Serveur statique coupé, l'application répondait quand même « manifeste lu » ; en mode avion, aucune erreur ; et un fichier modifié n'était jamais retéléchargé — le serveur ne voyait plus passer la moindre requête. `fetch` passe par `NSURLCache` (iOS) et par le cache OkHttp (Android), et un hôte qui ne renvoie qu'un `Last-Modified` les autorise à inventer une **fraîcheur heuristique**. Conséquence réelle : **un interrupteur d'arrêt qui n'arrête rien** pendant plusieurs minutes, et une correction qui n'arrive pas. Sous Node, `fetch` n'a pas de cache — aucun test hors appareil ne pouvait le produire. | Toute requête de livraison **contourne le cache de la plateforme** : paramètre d'unicité (`?_aeth=…`) et en-têtes `Cache-Control: no-cache` / `Pragma`. Les en-têtes seules ne suffisaient pas, ces caches étant indexés par URL. Gardé par un test qui vérifie que deux rafraîchissements ne demandent jamais la même URL. |

**Rien ne reste à observer.** Les neuf parcours ont été joués, correctif compris — c'est la seconde
passe qui valide ce dernier là où il s'était manifesté, et non en test.

Une leçon de méthode, la même qu'aux jalons 3-D et 3-E : le symptôme ne ressemblait pas à sa cause.
« Le serveur est coupé mais l'application dit *manifeste lu* » se lisait comme un bug du rapport ; ce
qui a désigné le vrai coupable, c'est le **journal du serveur statique** — il ne recevait plus rien.
Un banc de vérification doit donc montrer les deux bouts : ce que l'application affiche, et ce que la
source a réellement vu passer.

#### Les Blueprints de référence, sur appareil

Jalon 3-G. Ce sont les **vraies** sources d'une application en production, jouées depuis un iPhone
(Expo Go SDK 54) et comparées ligne à ligne à `aetherius run` sur le poste.

| Blueprint | Observé |
|-----------|---------|
| `ukit-campus-annonces` | `success`, sorties **identiques** au moteur Python |
| `ukit-campus-restaurants` | `success`, sorties **identiques** — dont la catégorie écartée par un `where` sur un champ imbriqué et la date produite par `format_date` |
| `ukit-campus-affluence` | `success`, sorties **identiques** |
| `ukit-celcat-semaine` | `success`, sorties **identiques** — après avoir cessé de passer par le relais de l'application d'origine, qui était d'ailleurs en panne (statut 522, échec **nommé** et non liste vide). Voir ci-dessous |
| `ukit-scolarite-sso` | authentification unifiée traversée et dossier administratif lu sur l'appareil. Un mauvais mot de passe donne `LOGIN_FAILED`, en pastille |
| `ukit-scolarite-messagerie` | `success`, `Réception (788)` et `non_lus: 788` — **identiques** au moteur Python, après quatre passes qui ont fini par nommer la cause (voir plus haut) |

La première passe de cette campagne s'est faite sur un réseau dégradé et **quatre des cinq cartes
ont expiré**, y compris des Blueprints déjà vérifiés aux jalons précédents. Le diagnostic n'a coûté
que trois taps parce que le banc porte des cartes de référence connues : rejouer `device-ip-check`
et une carte ancienne sépare « le téléphone n'a pas de réseau » de « ce Blueprint est cassé ». C'est
la raison d'être des cartes anciennes dans le banc, et il vaut mieux l'écrire que la redécouvrir.

#### Les noms réservés, sur appareil

Jalon 3-H. Le banc gagne **deux cartes**, et elles vont par paire : `Livraison : ajouter sans
republier` (nom couvert par le préfixe) et `Livraison : ce que le préfixe refuse` (nom hors préfixe,
publié dans le **même** manifeste). Aucune des deux n'a de Blueprint dans le binaire — c'est tout le
sujet, et c'est aussi la seule chose que les sondes hors appareil ne peuvent pas montrer : qu'un
Blueprint **absent de l'application** franchit la frontière du processus et survit à sa mort.

Le parcours à jouer est dans
[`examples/mobile/README.md`](../examples/mobile/README.md#le-parcours-du-jalon-3-h--ajouter-et-ce-qui-reste-dehors).

**Campagne sur iPhone** (iOS, Expo Go SDK 54, poste sur le partage de connexion du téléphone,
manifeste servi par `python3 -m http.server`). Une seule passe a suffi.

| Parcours | Observé |
|----------|---------|
| Le portail ajouté, **avant** tout rafraîchissement | « Rien à jouer sous ce nom », panneau `absent`. Un nom sans socle n'a rien à quoi retomber, et l'écran le dit au lieu de rester muet |
| Rafraîchir | `updated v2 · mobile.delivery.quotes`, `updated v1 · mobile.portail.demo`, `ignored · mobile.autre.demo` — **les trois natures du manifeste dans un seul rapport** : une correction, un ajout, un refus |
| Relancer le run | `success` : la citation de Jane Austen et `livre_par: "le préfixe réservé (jalon 3-H)"`. **Un Blueprint absent du binaire a tourné sur le téléphone** |
| La carte hors préfixe, après ce rafraîchissement | « Rien à jouer sous ce nom », panneau `absent`. Le rafraîchissement ne l'a pas rendu résoluble |
| **Tuer l'application** (vignette balayée du sélecteur), rouvrir, rejouer **sans rafraîchir** | `distant · v1` dès l'ouverture du panneau, zone de rapport **vide**, run `success`. Le cache a franchi la frontière du processus **pour un nom que le binaire ne contient pas** — c'est le parcours que ce jalon existe pour prouver, et le seul qu'aucun test hors appareil ne peut produire |
| **Interrupteur d'arrêt** : `allowNew` commenté, application rechargée | `absent — rien de livré sous ce nom`. Le portail est **désinstallé** |
| La capacité **rallumée**, application rechargée, **sans rafraîchir** | toujours `absent`. La purge était **durable**, pas une mise en veille : il a fallu un rafraîchissement pour que `distant · v1` revienne, donc par le réseau et non par un cache qui aurait fait semblant d'oublier |
| Rafraîchissements suivants | `kept` pour les deux versions en place — rien n'est retéléchargé sans raison |

Le **journal du serveur statique** dit la même chose depuis l'autre bout, et c'est là qu'il devient
une preuve plutôt qu'un confort :

| Ce que le téléphone a demandé | Fois |
|---|---|
| `manifest.json` | 11 |
| `portail-demo.blueprint.json` | 2 |
| `delivery-quotes.v2.blueprint.json` | 1 |
| **`hors-perimetre.blueprint.json`** | **0** |

Le Blueprint hors préfixe n'a **jamais été téléchargé** : la garde mord à la lecture du manifeste,
avant la moindre requête — ce que le rapport seul ne pouvait pas distinguer d'un refus après
téléchargement. Onze rafraîchissements pour deux téléchargements du portail confirment de leur côté
que `kept` ne retélécharge rien, et chaque ligne porte un `_aeth=` **distinct** : le contournement du
cache de plateforme trouvé au jalon 3-F tient aussi pour les noms ajoutés.

**Aucun défaut trouvé**, et une leçon de banc plutôt que de moteur : la première tentative de
rafraîchissement a répondu « manifeste non lu » sans que rien ne soit cassé — le serveur statique
n'était simplement pas lancé. C'est encore le journal du serveur qui l'a dit, en ne montrant
**rien** ; le symptôme, lui, ressemblait à un défaut de livraison. Un banc doit montrer les deux
bouts, et c'est vrai jusque dans les faux départs.
