# Le moteur embarqué

Aetherius a **deux moteurs**. Celui de `src/aetherius/`, en Python, exécute les quatre Acts et tout
ce qui demande une machine. Celui de [`sdks/engine/`](../sdks/engine), en TypeScript, rejoue les
**mêmes Blueprints** directement sur l'appareil de l'utilisateur — pour les applications mobiles, où
héberger un daemon reviendrait à faire sortir toutes les requêtes d'une seule IP et à faire transiter
les identifiants de chacun par une machine tierce.

Le cadrage, les décisions d'architecture et les sept jalons sont dans
[docs/phase-3/](phase-3/README.md). Ce document décrit ce qui est **livré** : ce qui existe, comment
ça marche, et où sont les limites.

> **État.** On peut charger, valider et **refuser** un Blueprint (jalon 3-A), et les deux
> mini-langages sont là — rendu d'expressions et extraction (jalon 3-B). Aucun step ne s'exécute
> encore : le runtime et l'Act I arrivent au jalon 3-C, l'Act II au jalon 3-D.

## Les trois paquets

| Paquet | Rôle |
|--------|------|
| [`@aetherius/engine`](../sdks/engine) | Le moteur, **neutre plateforme** : il ne connaît ni React Native, ni Node. Modèle de Blueprint, validation, erreurs, événements, et à terme l'Act I sur `fetch`. |
| [`@aetherius/react-native`](../sdks/react-native) | Ce que le précédent ne peut pas porter sans dépendre d'une plateforme : l'Act II sur WebView, le trousseau, la façade applicative. |
| [`@aetherius/client`](../sdks/client) | **Rien à voir** : il *pilote* le daemon Python à distance. Piloter un moteur et *être* un moteur sont deux métiers. |

Les deux premiers restent `private` tant que rien ne s'exécute.

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
| JSONPath hors sous-ensemble (`[?…]`, unions, `` `len` ``) | à l'extraction (`ExtractionError`) | Un parseur plus strict que `jsonpath-ng` refuserait à la validation des Blueprints corrects. Un faux refus est pire qu'un échec propre. |
| Filtre ou test inconnu | au rendu (`TemplateError`, le message nomme le jeu supporté) | |
| Date hors `YYYY-MM-DD` | au rendu (`TemplateError`) | |

XPath est la seule capacité d'extraction absente : hors navigateur, il demande un moteur à lui seul,
et l'exemple livré `books-restock-notify` utilise `normalize-space(//p[contains(@class, …)])`, une
expression XPath 1.0 complète avec fonctions. Reproduire lxml serait disproportionné face à l'usage.

## Les événements

Le moteur émet exactement les types de `contracts/events.schema.json`, pour qu'une même UI consomme
les deux moteurs. L'énumération est exposée **en valeur** (`RUN_EVENT_TYPES`) et non seulement en
type : c'est ce qui permet à un test de la comparer au contrat. Le SDK `@aetherius/client` portait
précisément cette dérive — deux types manquants depuis le jalon 2-E — faute d'une telle garde ; les
deux paquets l'ont désormais.

Le bus ([`events/bus.ts`](../sdks/engine/src/events/bus.ts)) diffuse en ordre d'émission, de façon
synchrone, et **avale l'exception d'un sink** en la journalisant : le bug d'un consommateur n'est
jamais l'échec d'un run. Le logger est injectable, pour qu'une application le route vers le sien.

## Limites connues

- **JSON seulement, pas de YAML.** Le moteur Python lit les deux ; embarquer un parseur YAML pour
  lire des fichiers que l'outillage écrit toujours en JSON serait un mauvais échange.
- **Pas de système de fichiers.** `parseBlueprint` prend du texte, pas un chemin : la livraison des
  Blueprints (ressource embarquée, téléchargement, cache) appartient à l'application, et fait
  l'objet du jalon 3-F.
- **Pas de plugins.** Une action de plugin est acceptée par le moteur Python sur tous les Acts ;
  côté embarqué elle est refusée comme action inconnue.
- **Les options hors périmètre sont ignorées, pas refusées.** `options.proxy`, `options.stealth` et
  `options.agent` restent valides au schéma — le moteur embarqué les accepte et n'en fait rien. Le
  choix est délibéré (décision 8 de la phase) : refuser un Blueprint parfaitement bon parce qu'il
  porte une option destinée à l'autre moteur casserait la promesse « le même Blueprint des deux
  côtés ». La contrepartie est à connaître : un Blueprint qui compte sur `options.proxy` sortira par
  la connexion de l'appareil, sans avertissement. C'est cohérent avec la raison d'être de la phase —
  sur mobile chaque utilisateur part de sa propre connexion, le proxy n'a plus d'objet — mais cela
  reste un silence, à lever si un cas d'usage le justifie.
- **Tout est asynchrone.** Seule divergence structurelle assumée avec le moteur Python, qui est
  synchrone de bout en bout : sur appareil, rien ne peut bloquer la boucle JS. La sémantique
  observable — ordre des steps, événements émis, forme du `Result` — reste identique.
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

## Tester

```bash
make check-all      # passe Python + workspace npm (build, typage, tests des trois paquets)
make conformance    # le corpus rejoue sur les deux moteurs
make contracts      # regenere contracts/actions.json apres une evolution du registre
```

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

Le harnais lui-même est testé (`tests/conformance/test_harness.py`) : un exécuteur qui rapporterait
tous les cas comme passants transformerait une suite verte en affirmation fausse.

### Parité sur le corpus livré

Au-delà du corpus de conformance, les **29 Blueprints d'`examples/`** ont été passés aux deux
moteurs et leurs verdicts comparés : **22 identiques, 7 divergents**, et chaque divergence est l'une
de celles que le socle déclare — quatre Blueprints Oracle/Phantom, une composition dont un step
escalade vers `oracle`, une capture d'écran, une notification (ce dernier Blueprint touche depuis
3-B **deux** limites, et la marche s'arrête au premier refus : l'extraction XPath). Aucune
divergence inattendue.

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
