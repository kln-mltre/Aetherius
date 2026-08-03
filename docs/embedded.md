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
> d'erreur exploitable — voir [La surface applicative](#la-surface-applicative).

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

### Sessions, cookies et mode debug

`options.session.persist` décide de la nature de la vue, et le choix se voit par l'utilisateur :

| `persist` | Vue | Ce que ça coûte |
|-----------|-----|-----------------|
| absent / `false` | `incognito`, **libérée à la fin de chaque run** | départ propre à chaque run, ré-authentification à chaque lancement |
| `true` | magasin de la plateforme (`sharedCookiesEnabled`, `thirdPartyCookiesEnabled`), et **la vue est gardée entre les runs** | pas de re-login, mais une WebView cachée reste vivante jusqu'au changement d'options ou au démontage du composant |

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
que le mode debug ouvre côté Python. Hors debug, la vue est garée hors écran avec un viewport fixe
(1024 × 768) : hors écran plutôt que `display: none`, parce qu'une vue sans boîte ne met rien en
page et que **tous** les éléments seraient alors invisibles.

Un détail de mise en œuvre qui n'en est pas un : c'est le **conteneur** qui est garé hors écran, pas
la vue. `react-native-webview` rend `<View style={[{flex: 1, overflow: 'hidden'}, containerStyle]}>`
autour de la vue native ; positionner la vue *interne* la laisse rognée à néant dans ce conteneur —
une WKWebView sans aire de rendu, ce qui est précisément la façon dont iOS finit par tuer le
processus de contenu web. La vue garde donc `flex: 1` et c'est `containerStyle` qui cache. Le signal
`onContentProcessDidTerminate` est écouté par ailleurs : le document ne revient pas tout seul, donc
les appels en vol échouent en le disant, au lieu d'attendre une page morte jusqu'à leur échéance.

Le **user-agent** est configurable (`options.stealth.user_agent`) : c'est la seule bribe de
discrétion retenue par la phase, et elle est porteuse — un portail sert souvent un DOM différent aux
UA mobiles.

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
| Oublier une ré-exportation dans `index.ts` | `npm test` (react-native) : « the package's public surface is one door ». |
| Garer un `confirm` alors qu'aucune surface n'écoute | `npm test` (react-native) : « nobody listening means unattended » — le run attend au lieu de refuser tout de suite. |
| Ne pas relayer l'échec de chargement de la WebView à l'hôte | `npm test` (react-native) : « a view that cannot load the document fails the run as unreachable » — hors ligne, l'Act II retombe sur `engine` au lieu d'`unavailable`. |
| Faire échouer une opération qui perd son document au lieu de la rejouer | `npm test` (react-native) : « an operation survives the navigation a redirect causes » — plus rien ne peut attendre après un login. |
| Remettre `TemplateError` dans la famille `data` | `npm test` (engine) : un secret absent redevient « la page a changé ». |
| Rendre le silence de la page en `ActionError` au lieu du code nommé | `npm test` (react-native) : « a page that never answers produces the failure the Blueprint named » — un login refusé redevient « erreur interne ». |
| Détruire la vue à la fin d'un run `persist: true` | `npm test` (react-native) : « a persistent session keeps its view » — la session ne franchit plus la frontière du run. |
| Exiger l'agent pour décider qu'un `navigate` est un rechargement | `npm test` (react-native) : « a kept view is reloaded, not handed the URL it already shows » — le second run d'une session persistante attend un document qui ne vient jamais. |

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
