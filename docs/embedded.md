# Le moteur embarqué

Aetherius a **deux moteurs**. Celui de `src/aetherius/`, en Python, exécute les quatre Acts et tout
ce qui demande une machine. Celui de [`sdks/engine/`](../sdks/engine), en TypeScript, rejoue les
**mêmes Blueprints** directement sur l'appareil de l'utilisateur — pour les applications mobiles, où
héberger un daemon reviendrait à faire sortir toutes les requêtes d'une seule IP et à faire transiter
les identifiants de chacun par une machine tierce.

Le cadrage, les décisions d'architecture et les sept jalons sont dans
[docs/phase-3/](phase-3/README.md). Ce document décrit le **socle livré au jalon 3-A** : ce qui
existe, comment ça marche, et où sont les limites.

> **État.** On peut charger, valider et **refuser** un Blueprint. Rien ne s'exécute encore : le
> runtime et l'Act I arrivent au jalon 3-C, l'Act II au jalon 3-D.

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

Le harnais lui-même est testé (`tests/conformance/test_harness.py`) : un exécuteur qui rapporterait
tous les cas comme passants transformerait une suite verte en affirmation fausse.

### Parité sur le corpus livré

Au-delà du corpus de conformance, les **29 Blueprints d'`examples/`** ont été passés aux deux
moteurs et leurs verdicts comparés : **22 identiques, 7 divergents**, et chaque divergence est l'une
de celles que le socle déclare — quatre Blueprints Oracle/Phantom, une composition dont un step
escalade vers `oracle`, une capture d'écran, une notification. Aucune divergence inattendue.

Un cas mérite d'être connu : `examples/plugins/demo-notify.blueprint.json` est refusé par les deux
moteurs, mais **pour deux raisons différentes** — le moteur Python parce que le plugin de démo n'est
pas installé, le moteur embarqué parce qu'il n'a pas de système de plugins. Cet accord est
accidentel : installer le plugin le ferait diverger. C'est la limite « pas de plugins » ci-dessus,
vue depuis le corpus.
