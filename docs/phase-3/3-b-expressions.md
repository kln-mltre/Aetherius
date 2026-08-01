# Jalon 3-B — Expressions, templates & extraction

**Statut : livré.** Doc de référence : [docs/embedded.md](../embedded.md#expressions-et-extraction).
Le jalon à risque de la phase : c'est ici que se paie la contrainte « ni `eval`, ni `new Function` »,
et c'est ici que se joue la parité réelle entre les deux moteurs. Tout ce qui suit (le runtime, les
deux Acts) consomme ces briques.

Ce qui a été livré : un **évaluateur maison** (analyseur lexical, parseur à précédence,
interpréteur d'AST) sous [`expr/`](../../sdks/engine/src/expr), unique brique des **trois** usages —
rendu ([`template.ts`](../../sdks/engine/src/template.ts)), vérité `isTruthy`, prédicat `where` ;
l'extraction JSON (sous-ensemble JSONPath maison) et HTML (pile `htmlparser2`/`css-select`, sans
génération de code, gardée par un test) sous
[`extraction/`](../../sdks/engine/src/extraction) ; le refus XPath **à la validation**
([`portability.ts`](../../sdks/engine/src/blueprint/portability.ts)) ; et l'extension du corpus de
conformance aux premiers cas d'**exécution** (familles `expression`, `extraction`, `truthy`), qui
devient à partir d'ici la vraie mesure de la parité. Côté Python, un seul changement, annoncé : la
construction des specs d'extraction quitte le driver Vector pour
[`core/extraction/dispatch.py`](../../src/aetherius/core/extraction/dispatch.py), afin que le
corpus emprunte le vrai chemin de production plutôt qu'une copie.

## Objectif

Reproduire, **sans exécution de code dynamique**, les deux mini-langages sur lesquels repose un
Blueprint :

1. le **rendu d'expressions** `{{ ... }}`, y compris la règle de l'expression nue et la sémantique
   « variable indéfinie = erreur » ;
2. la **vérité** (`isTruthy`) partagée par `when` et `assert` ;
3. le **prédicat `where`** de l'extraction ;
4. **JSONPath**, et l'**extraction** JSON et HTML dans ses deux dialectes.

## Dépendances

Jalon 3-A (modèle, erreurs, harnais de conformance).

## Interfaces et fichiers

Références côté Python, à reproduire à l'identique :

- [`core/blueprint/template.py`](../../src/aetherius/core/blueprint/template.py) — `render_value`,
  la règle de l'expression nue, les trois filtres de date.
- [`core/runtime/flow.py`](../../src/aetherius/core/runtime/flow.py) — `is_truthy`.
- [`core/extraction/json_extractor.py`](../../src/aetherius/core/extraction/json_extractor.py) —
  `ExtractSpec`, JSONPath, `where`, `fields`.
- [`core/extraction/html_extractor.py`](../../src/aetherius/core/extraction/html_extractor.py) —
  `HtmlExtractSpec`.

À créer sous [`sdks/engine/src/`](../../sdks/engine/src) :

- **`expr/`** — l'analyseur lexical, le parseur et l'interpréteur d'AST. C'est **une seule brique**
  au service de trois usages (rendu, `when`/`assert`, `where`) : les dupliquer serait la garantie
  qu'ils divergeront.
- **`template.ts`** — le rendu de valeur (chaîne, tableau, objet), au-dessus de `expr/`.
- **`extraction/json.ts`**, **`extraction/html.ts`** — les deux extracteurs.
- **`extraction/jsonpath.ts`** — le sous-ensemble JSONPath retenu.

## Contrat

Aucune modification des contrats. En revanche ce jalon **écrit une limite** : le sous-ensemble
d'expressions et de JSONPath réellement supporté par le moteur embarqué. Cette limite doit être
documentée dans `docs/embedded.md` et **matérialisée par le corpus de conformance** — une limite qui
n'est pas testée n'est pas une limite, c'est une surprise à retardement.

## Points de conception

- **Un parseur, pas un moteur de templates généraliste.** La tentation est d'importer une
  bibliothèque compatible Jinja2 ; aucune ne fonctionne sans compilation dynamique, et toutes pèsent
  bien plus que le sous-ensemble réellement utilisé. Un analyseur lexical et un parseur à précédence
  couvrent le besoin dans un volume comparable, sans dépendance et sans surface d'exécution.
- **La règle de l'expression nue est le piège principal.** Quand une chaîne est *exactement* une
  expression (`"{{ steps.week.events }}"`), le moteur Python rend l'**objet brut** — une liste reste
  une liste. Dès qu'il y a du texte autour, le résultat est une chaîne. Ne pas reproduire cette
  distinction casserait silencieusement tous les `outputs` qui rendent des collections : le run
  réussirait, avec des chaînes à la place des données.
- **`StrictUndefined` est un choix, pas un détail.** Une variable absente doit lever, pas rendre une
  chaîne vide. C'est ce qui transforme une faute de frappe dans un Blueprint en erreur immédiate
  plutôt qu'en donnée manquante à l'autre bout de la chaîne.
- **`isTruthy` doit être copié à la lettre**, y compris ses bizarreries : la valeur est convertie en
  chaîne, mise en minuscules et comparée à `true` / `1` / `yes`. Le booléen `True` de Python devient
  la chaîne `"True"`, qui est vraie. Un portage « intelligent » qui utiliserait la véracité native de
  JavaScript ferait diverger `when` sur des cas réels. C'est un cas de conformance obligatoire.
- **Le prédicat `where` est du code fourni par le Blueprint.** Côté Python il est exécuté après
  filtrage de l'AST par liste blanche, avec les accès aux attributs spéciaux explicitement refusés.
  Côté embarqué, l'interpréteur maison n'a tout simplement **rien** à offrir à un attaquant : il n'y
  a pas d'accès aux fonctions natives, donc pas de liste blanche à maintenir. C'est le bénéfice
  collatéral de la contrainte du point 4 — et l'argument qui rend acceptable le jalon 3-F, où les
  Blueprints arrivent du réseau.
- **JSONPath : viser le sous-ensemble utile, pas la spécification.** Le moteur Python s'appuie sur
  une implémentation étendue très complète ; la reproduire intégralement serait un projet en soi. Le
  corpus de conformance, alimenté par les `examples/` existants, définit le périmètre. Ce qui est
  hors périmètre doit **échouer bruyamment**, jamais rendre un résultat partiel.
- **Deux dialectes d'extraction, à ne pas fusionner.** Vector extrait avec
  `{from, path, where, fields}` ou `{from, selector, selector_type, attr, multiple}` ; Continuum
  extrait avec `outputs: {nom: {selector, as, item, attr, each, fields}}`. Ce sont deux vocabulaires
  distincts qui se ressemblent, et les unifier « pour simplifier » casserait des Blueprints
  existants.
- **HTML sans DOM.** L'extraction HTML de Vector s'exécute hors navigateur : elle demande un parseur
  pur JavaScript. Si le coût de XPath se révèle disproportionné face à son usage réel, le déclarer
  **limite documentée** est une réponse acceptable — l'inacceptable serait de l'accepter à la
  validation puis d'échouer à l'exécution.

## Plan de test

- **Rendu** : accès pointé, indexation, filtres `add_days`/`sub_days`/`format_date` sur des dates
  ISO, `| length`, comparaisons, `and`/`or`/`not`/`in`, interpolation multiple dans une même chaîne,
  récursion dans les tableaux et les objets, scalaires non-chaînes laissés intacts.
- **Expression nue** : `"{{ liste }}"` rend une liste ; `"a {{ liste }}"` rend une chaîne. Cas de
  conformance obligatoire.
- **Indéfini** : une variable absente lève `TemplateError` ; un chemin partiellement absent aussi.
- **`isTruthy`** : table exhaustive incluant `"True"`, `"true"`, `"1"`, `"yes"`, `"0"`, `""`,
  `"false"`, et des valeurs non-chaînes.
- **`where`** : filtrage nominal, comparaison sur un champ absent, et **tentatives d'évasion**
  (accès à un attribut spécial, appel de fonction, accès au contexte global) qui doivent échouer et
  non s'exécuter.
- **Extraction** : JSONPath sur les fixtures des `examples/` existants ; `fields` rendant zéro, une
  et plusieurs correspondances ; extraction HTML par sélecteur CSS avec et sans `attr`,
  `multiple: false`.
- **Conformance** : le corpus gagne ses premiers cas d'**exécution** — chaque expression et chaque
  extraction ci-dessus est rejouée par les deux moteurs, résultats comparés.

## Exemple exécutable à livrer

Aucun exemple utilisateur (brique interne). Le livrable équivalent est **l'extension du corpus de
conformance**, qui devient à partir d'ici la vraie mesure de la parité.

## Définition de terminé

Points de [CONTRIBUTING](../../CONTRIBUTING.md#définition-de--terminé-) applicables ;
`make check-all` et `make conformance` verts ; les limites (JSONPath, XPath) écrites dans
`docs/embedded.md` **et** couvertes par un cas de conformance qui vérifie qu'elles échouent
proprement.

## Critères d'acceptation

Les expressions de tous les Blueprints d'`examples/` rendent la même valeur sur les deux moteurs, y
compris celles qui rendent des collections ; `isTruthy` est identique sur toute sa table ; un
prédicat `where` malveillant échoue sans rien exécuter ; les limites documentées échouent avec un
message explicite plutôt qu'un résultat partiel.

## Ce qui a été décidé en chemin

- **La pile HTML est une dépendance, pas un parseur maison.** `htmlparser2` + `domutils` +
  `css-select` sont du JavaScript pur et — vérifié, puis **gardé par un test** sur le closure résolu
  depuis le lockfile — sans `eval` ni `new Function`. Ce sont les premières dépendances d'exécution
  du paquet ; réécrire un tokeniser HTML tolérant et un moteur de sélecteurs aurait coûté ~600
  lignes de code subtil pour un résultat moins correct.
- **XPath est refusé à la validation, JSONPath hors sous-ensemble à l'extraction.** L'asymétrie est
  volontaire : `selector_type` est une enum du schéma, donc refusable statiquement sans risque de
  faux positif, alors qu'un parseur JSONPath plus strict que `jsonpath-ng` refuserait des Blueprints
  corrects. Un faux refus est pire qu'un échec propre.
- **L'interpolation est fidèle à Python.** `str(True)` vaut `"True"`, pas `"true"`. Un booléen ou un
  `None` interpolé dans une URL, un formulaire ou un en-tête diverge sinon en silence — la classe de
  bug que la phase existe pour supprimer.
- **Les bizarreries du moteur Python sont reproduites, pas corrigées** : la règle `isTruthy`
  (chaîne minusculée comparée à `true`/`1`/`yes`, donc le nombre `2` est faux dans un `when`), le
  refus d'une chaîne qui commence *et* finit par une expression (`"{{ a }} {{ b }}"`, dont le motif
  de l'expression nue va jusqu'au dernier `}}`), et les coins de `jsonpath-ng` (`[*]` est une
  tranche, `.*` un accès de champ ; un opérateur de liste sur un non-liste le traite comme une liste
  d'un élément ; un indice numérique peut lever). Les « corriger » ici ferait diverger le même
  Blueprint d'un moteur à l'autre.
- **Les sondes valent la suite de tests.** Trois différentiels (les 101 expressions des `examples/`
  sur trois contextes, l'extraction sur les vraies pages, les 44 formes JSONPath sur 12 documents)
  ont trouvé quatre défauts qu'aucun test unitaire n'aurait montrés, dont un **côté Python**
  (`render_value` laissait échapper un `TypeError` non typé). Le détail est dans
  [docs/embedded.md](../embedded.md#parité-sur-le-corpus-livré).
