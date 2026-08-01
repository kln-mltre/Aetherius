# Jalon 3-A — Socle TypeScript & parité

**Statut : livré.** Doc de référence : [docs/embedded.md](../embedded.md). Le moteur embarqué sait
charger, valider et **refuser** un Blueprint, à l'identique du moteur Python : validation en deux
temps (schéma Ajv précompilé au build, puis sémantique par act), erreurs typées, bus d'événements,
`ActDriver` asynchrone. Trois gardes anti-dérive sont en place — `contracts/actions.json` généré et
gardé, la table des capacités embarquées prouvée sous-ensemble strict, et le **corpus de
conformance** (`make conformance`, branché en CI) rejoué par les deux moteurs. La dérive réelle du
SDK `@aetherius/client` (deux types d'événement manquants depuis 2-E) est corrigée au passage.
Fondation de la Phase 3 : n'apporte **aucune capacité utilisateur seule** (comme le store 1.5-A et
le substrat de cognition 2-A) ; c'est la brique sans laquelle les deux Acts embarqués
dupliqueraient tout, et sans laquelle rien ne garantirait que les deux moteurs restent d'accord.
Ce document conserve la spécification d'origine du jalon.

## Objectif

Poser, testé et typé, le socle du moteur embarqué :

1. le **modèle de Blueprint** et sa **validation en deux temps**, identique au Python ;
2. la **table des capacités** du moteur embarqué, adossée à un contrat généré ;
3. les **erreurs typées**, le **bus d'événements** et le **`Result`** ;
4. l'interface **`ActDriver` asynchrone** et le `RunContext` ;
5. le **harnais de conformance** qui empêchera les deux moteurs de diverger.

Rien ne s'exécute à la fin de ce jalon : on peut charger, valider et refuser un Blueprint, pas le
jouer.

## Dépendances

Aucune. Le squelette (workspace npm, stubs) est déjà en place.

## Interfaces et fichiers

Déjà en place (stubs à implémenter) :

- [`sdks/engine/src/blueprint/types.ts`](../../sdks/engine/src/blueprint/types.ts) — `Blueprint`,
  `StepModel`, `InputSpec`, `Options`, `ActName`, `EMBEDDED_ACTS`.
- [`sdks/engine/src/errors.ts`](../../sdks/engine/src/errors.ts) — hiérarchie miroir de
  [`core/errors.py`](../../src/aetherius/core/errors.py).
- [`sdks/engine/src/events.ts`](../../sdks/engine/src/events.ts) — `RunEvent`, `RunEventType`,
  `Sink`, `EventBus`.
- [`sdks/engine/src/result.ts`](../../sdks/engine/src/result.ts) — `RunStatus`, `StepResult`,
  `Result`.
- [`sdks/engine/src/driver.ts`](../../sdks/engine/src/driver.ts) — `ActDriver`, `RunContext`,
  `Renderer`.

À créer :

- **`contracts/actions.json`** — nouveau contrat, **généré** depuis le registre Python
  ([`core/actions/registry.py`](../../src/aetherius/core/actions/registry.py) et
  [`core/actions/base.py`](../../src/aetherius/core/actions/base.py)) : pour chaque action, son nom,
  son résumé, ses paramètres (`ParamSpec`), et la table `ACT_CAPABILITIES`. Aujourd'hui le catalogue
  du builder est la seule projection du registre ; ce fichier en devient une seconde, lisible par
  n'importe quel langage.
- **Le générateur et sa garde** côté Python : une commande qui régénère le fichier, et un test dans
  [`tests/contracts/`](../../tests/contracts/) qui échoue si le fichier committé diverge du registre
  vivant — exactement le motif de `test_shipped_schema_matches_contract`.
- **`sdks/engine/src/blueprint/loader.ts`** — chargement et validation en deux temps.
- **`sdks/engine/src/blueprint/validator.ts`** — validation sémantique par act, récursive dans les
  branches de flux, avec la table des capacités du moteur embarqué.
- **Le validateur de schéma précompilé** — un artefact généré au build depuis
  [`contracts/blueprint.schema.json`](../../contracts/blueprint.schema.json), plus l'étape de build
  qui le produit et la garde qui détecte sa péremption.
- **`sdks/engine/src/events/bus.ts`** — implémentation du bus et des sinks.
- **Le harnais de conformance** : un répertoire de fixtures partagé, un exécuteur côté Python, un
  exécuteur côté TypeScript, et la cible `make conformance` (déjà déclarée dans le
  [`Makefile`](../../Makefile), en échec explicite tant que ce jalon n'est pas livré).

## Contrat

- **Ajout** de `contracts/actions.json`. Aucune modification de `blueprint.schema.json` ni de
  `events.schema.json` : le moteur embarqué s'y conforme, il ne les étend pas.
- La table des capacités du moteur embarqué est un **sous-ensemble strict** d'`ACT_CAPABILITIES` —
  jamais un sur-ensemble. Un Blueprint accepté par le moteur embarqué est toujours accepté par le
  moteur Python ; l'inverse n'est pas vrai, et c'est le sens du point 6 des décisions de phase.
- Le SDK [`@aetherius/client`](../../sdks/client) porte aujourd'hui une **dérive réelle** à corriger
  au passage : son `RunEventType` ne liste que huit valeurs et ignore `input_requested` /
  `input_provided`, pourtant définis par `contracts/events.schema.json` depuis le jalon 2-E. Le test
  de conformance des énumérations doit couvrir **les deux** paquets.

## Points de conception

- **Validation en deux temps, comme en Python.** D'abord le JSON Schema (structurel,
  langage-agnostique), ensuite la validation typée et sémantique. Deux étapes, deux erreurs
  distinctes (`BlueprintSchemaError` puis `BlueprintValidationError`) : un message qui dit *à quel
  niveau* le document est invalide vaut mieux qu'un message qui dit qu'il l'est.
- **Le schéma est précompilé, pas interprété.** Un validateur JSON Schema généraliste construit ses
  fonctions de validation par `new Function`, ce que le moteur JS mobile refuse. La compilation
  devient une **étape de build** dont la sortie est un module JavaScript ordinaire. Conséquence à
  assumer : cet artefact peut se périmer si le contrat bouge — d'où la garde.
- **Le message d'erreur d'une capacité absente doit être actionnable.** Côté Python, un act trop
  faible produit « requires act='continuum' or higher » grâce à `_CAPABILITY_ORIGIN`. Côté embarqué
  il existe un second motif — l'action existe pour cet act, mais pas sur cette plateforme. Les deux
  cas méritent des formulations différentes ; les confondre enverrait le lecteur corriger son `act`
  alors que le problème est ailleurs.
- **Le corpus de conformance est la vraie livraison de ce jalon.** Il ne teste pas du code : il fige
  ce que « le même Blueprint » signifie. Chaque fixture est un triplet (Blueprint, entrées, sorties
  attendues) que les deux moteurs rejouent. À ce stade il ne peut contenir que des cas de
  **validation** (accepté / refusé, et avec quelle erreur) — les cas d'exécution arrivent avec 3-B et
  3-C. Le concevoir dès maintenant évite d'avoir à le rétro-adapter à deux implémentations déjà
  écrites.
- **`exactOptionalPropertyTypes` et `noUncheckedIndexedAccess` sont actifs** sur le paquet. Ce sont
  les deux options qui rapprochent le plus TypeScript de la rigueur de pydantic en mode strict ; les
  activer plus tard reviendrait à réécrire le code.

## Plan de test

- **Chargement** : JSON valide, JSON malformé (`BlueprintLoadError`), document violant le schéma
  (`BlueprintSchemaError`), document valide au schéma mais sans `steps` ni `goal`.
- **Validation sémantique** : une action de Continuum dans un Blueprint `vector` est refusée avec le
  bon indice d'act ; une action valide pour l'act mais non portable est refusée avec l'autre message ;
  la validation descend bien dans `then`/`else`/`steps` et rapporte un chemin lisible
  (`steps[3].then[0]`) ; un `act: "oracle"` est refusé proprement.
- **Bus** : un sink qui lève est journalisé et avalé, les sinks suivants reçoivent quand même
  l'événement.
- **Conformance** : `make conformance` rejoue le corpus sur les deux moteurs et échoue si l'un des
  deux diverge. Un cas de dérive volontairement introduit doit faire échouer la cible.
- **Anti-dérive** : `contracts/actions.json` est régénérable à l'identique depuis le registre ; les
  énumérations d'événements de `@aetherius/client` **et** de `@aetherius/engine` couvrent exactement
  `contracts/events.schema.json`.

## Exemple exécutable à livrer

Aucun (fondation). Les exemples arrivent avec 3-C (Vector) et 3-D (Continuum). Le corpus de
conformance n'est pas un exemple : il ne s'adresse pas à un utilisateur.

## Définition de terminé

Les points de [CONTRIBUTING](../../CONTRIBUTING.md#définition-de--terminé-) applicables (pas
d'exemple exécutable ni de prise en main UI pour une fondation) ; `make check-all` vert ;
`make conformance` vert et branchée en CI ; les deux paquets restent `private` (rien à publier tant
que rien ne s'exécute).

## Critères d'acceptation

Un Blueprint des `examples/` se charge et se valide à l'identique par les deux moteurs ; un
Blueprint demandant une capacité absente du moteur embarqué est refusé **avant** exécution, avec un
message qui distingue « mauvais act » de « non portable sur appareil » ; `contracts/actions.json`
est généré et gardé ; le harnais de conformance échoue quand on fait diverger un moteur.
