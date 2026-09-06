# Jalon 3-J — Une lecture facultative, et le run partiel qui la rend visible

**Statut : livré.** Troisième appendice de la Phase 3, pour la même raison que
[3-H](3-h-portails.md) et [3-I](3-i-extraction-texte.md) : un port réel a rencontré une limite du
contrat, et le manque est de notre côté.

> **Amendé le 2026-09-05**, après les quatre questions de conception soulevées à la préparation du
> plan. Les arbitrages sont désormais **dans ce document** — sorties d'un bloc cédé, comportement des
> trois consommateurs, périmètre de la sonde dure, portée de la règle de validation — avec les six cas
> limites et les lignes exactes à toucher. Une correction de fait y a été faite au passage : la
> section sur les sorties affirmait qu'un `| default(...)` suffisait, **c'est faux**, et les deux
> moteurs sont d'accord pour lever. Voir [Les sorties doivent survivre au bloc](#les-sorties-doivent-survivre-au-bloc--et-cest-le-point-qui-casse-tout-si-on-loublie).

> **En une phrase.** Le vocabulaire ne sait exprimer que deux issues pour une étape — elle réussit,
> ou le run meurt. Il n'existe aucun moyen de dire *« cette lecture est un bonus ; son absence est un
> résultat acceptable »*. Ce jalon l'ajoute, et il le fait sans rien avaler : la défaillance reste
> **visible**, portée par un statut que les deux moteurs déclarent déjà et que rien ne produit.

## Le manque, et comment il s'est vu

Le 2026-09-05, sur un iPhone, le parcours froid d'un portail universitaire meurt après avoir lu
l'identité de l'étudiant. Le relevé, réel :

```
#12 extract dossier      success    11 ms      <- nom, INE, formation : LUS
#13 assert               success     1 ms
#14 navigate coordonnees success   287 ms
#15 wait_for             failed  47 012 ms     <- une page annexe ne repond pas
=> run FAILED : l'identite lue au step 12 est perdue avec le reste
```

Les quatre dernières lectures de ce Blueprint sont des **bonus** : des coordonnées, une adresse, un
libellé de formation, un identifiant d'emploi du temps. Aucune n'est nécessaire pour ouvrir une
session ; toutes enrichissent la fiche si elles arrivent. Et pourtant l'échec de la première emporte
les trois autres **et l'identité déjà extraite**.

L'auteur du Blueprint connaît cette asymétrie. Il n'a aucun moyen de l'écrire.

### Ce qu'il a essayé, et pourquoi ça ne suffit pas

Le contournement en vigueur chez le consommateur est l'extraction en `as: "list"`, qui rend `[]`
plutôt que de lever. Il ne couvre que l'**extraction** : la navigation qui la précède, elle, n'est
protégée par rien. La règle « une lecture bonus ne doit jamais emporter la connexion » a donc été
appliquée à la moitié qui pouvait l'être, et oubliée sur celle qui ne le pouvait pas — non par
négligence, mais parce que le contrat ne l'offre pas.

## L'état des lieux, vérifié plutôt que supposé

Avant d'ajouter quoi que ce soit, l'inventaire de ce qui existe. Il a été relu dans les deux moteurs.

| Mécanisme | Ce qu'il fait | Pourquoi il ne répond pas |
|---|---|---|
| `when` | garde **avant** exécution ; l'étape passe en `SKIPPED` | décide sur une expression connue d'avance, pas sur une défaillance |
| `describe` + `fallback` | **auto-réparation** (jalon 2-D) : rejoue l'étape sur un Act supérieur quand un sélecteur lâche | « réessayer plus intelligemment », pas « tolérer » ; et **hors de portée du moteur embarqué**, qui ne connaît que les Acts I et II |
| `options.retries` | reprises **HTTP**, Act I | ne concerne ni Act II ni une étape non réseau |
| `on_timeout: "fail:CODE"` | **nomme** l'échec d'un `wait_for` | le nomme, ne le tolère pas |
| `extract` … `as: "list"` | rend `[]` au lieu de lever | extraction seulement |

**Aucun `try`, aucun `optional`, aucun `on_error` nulle part.** Ce n'est pas un oubli de transfert
vers le moteur embarqué : les deux moteurs sont identiques sur ce point, et l'absence est cohérente
avec la thèse du projet — *les erreurs cessent d'être avalées*, huit familles d'échec dont une seule
veut dire « réessaye ». Un `try/catch` générique rouvrirait la porte que la Phase 6 du consommateur a
passé une phase entière à fermer.

Le trou réel est donc plus étroit, et c'est ce qui rend ce jalon petit : **le vocabulaire ne sait pas
dire qu'une lecture est facultative.**

### La place est déjà réservée dans l'architecture

C'est la découverte qui décide de la forme de la solution. `RunStatus` déclare **quatre** valeurs
dans les deux moteurs :

```python
# src/aetherius/core/runtime/result.py
class RunStatus(str, Enum):
    SUCCESS = "success"
    FAILED  = "failed"
    PARTIAL = "partial"     # <- declare, mappe, colore... et produit par RIEN
    SKIPPED = "skipped"
```

```ts
// sdks/engine/src/result.ts
export type RunStatus = "success" | "failed" | "partial" | "skipped";
```

`PARTIAL` est mappé par le daemon (`src/aetherius/server/schemas.py` le traduit en `succeeded`),
coloré en ambre par la Console (`src/aetherius/console/widgets/run_summary.py`), couvert par deux
tests d'existence — et **aucune ligne de code ne le pose jamais**. Une recherche sur tout le dépôt le
confirme.

Ce jalon ne crée donc pas un statut : il **honore celui qui attend depuis le début**.

## Objectif

Un bloc d'étapes déclaré facultatif. Si l'une d'elles échoue, le reste du bloc est sauté, la
défaillance est **enregistrée**, et le run continue — pour finir en `partial`.

Rien d'autre. Ni reprise, ni condition, ni capture d'exception généralisée.

## Ce qui est écarté, et pourquoi

**Un `try` / `catch` générique.** Il inviterait à envelopper n'importe quoi, y compris une
authentification, et rendrait silencieux exactement ce que le modèle d'erreur existe pour rendre
lisible. Le nom compte : `optional` décrit une **propriété de la lecture**, `try` décrit une
technique de programmation.

**Un drapeau `optional: true` sur une étape isolée.** Tentant, et c'est un piège mesuré : rendre un
seul `navigate` inoffensif laisse les étapes suivantes sur une page **inconnue**, et elles échoueront
plus loin en accusant un sélecteur. Ce qui est facultatif n'est jamais une étape, c'est une
**séquence** — naviguer, attendre, lire — dont on saute le reste dès que le premier maillon cède.

**Avaler la défaillance en silence.** Le bloc n'efface rien : l'étape fautive garde son `FAILED` et
son message, l'événement `error` est émis comme aujourd'hui, et le run le dit dans son statut. Un
appelant qui veut savoir ce qu'il n'a pas eu le lit dans `Result.steps`.

**Une valeur de repli déclarée dans le bloc** (`"on_failure": {...}`). Elle dupliquerait le filtre
`default`, qui existe déjà dans les deux moteurs et sait le faire à l'endroit correct — le rendu des
sorties.

## Points de conception

### La forme : une action de flux, comme ses trois sœurs

`optional` rejoint `if`, `repeat` et `for_each` : interprétée par l'exécuteur de steps, jamais
transmise à un driver, donc disponible dans **tous les Acts** sans toucher la table de capacités par
Act — c'est déjà le cas de ses trois sœurs, qui figurent dans les quatre listes.

```json
{
  "action": "optional",
  "steps": [
    { "action": "navigate", "url": "{{ vars.coordonnees }}" },
    { "action": "wait", "ms": 4000 },
    { "action": "wait_for", "selector": ".label-valeur", "timeout_ms": 30000 },
    { "id": "coord", "action": "extract", "from": "html", "fields": { "ville": ".ville" } }
  ]
}
```

### Les statuts, sans en inventer un seul

| Ce qui est observé | Statut |
|---|---|
| l'étape qui a cédé | `FAILED`, avec son message — inchangé |
| les étapes suivantes du bloc | `SKIPPED` |
| le bloc `optional` lui-même | `PARTIAL` |
| le run, si au moins un bloc a cédé et que rien d'autre n'a échoué | `PARTIAL` |
| le run, si un bloc a cédé **et** qu'une étape hors bloc a échoué | `FAILED` — l'échec dur gagne toujours |

Un bloc dont toutes les étapes réussissent est un `SUCCESS` ordinaire : `optional` ne teinte rien
quand il n'y a rien à signaler.

### Les sorties doivent survivre au bloc — et c'est le point qui casse tout si on l'oublie

Aujourd'hui, les deux moteurs ne rendent les `outputs` **que** si le run est `SUCCESS` :

```python
# src/aetherius/core/runtime/engine.py:111
if final_status == RunStatus.SUCCESS:
    if blueprint.outputs:
        final_outputs = render_value(blueprint.outputs, ctx.template_ctx())
```

```ts
// sdks/engine/src/runtime/engine.ts:116
if (status === "success" && blueprint.outputs !== undefined) {
```

Laissé tel quel, un run `partial` ne rendrait **aucune sortie** — donc pas même l'identité lue avant
le bloc, et le jalon n'aurait rien réparé. La condition devient « le run n'a pas échoué ».

Reste le rendu lui-même, et c'est le piège du jalon.

Quand le bloc a cédé, `steps.coord` n'existe **pas du tout** dans le contexte. Or les deux moteurs
rejettent l'indéfini **au point d'usage** : côté Python par `StrictUndefined`, côté TypeScript par le
`use()` de [`sdks/engine/src/expr/eval.ts`](../../sdks/engine/src/expr/eval.ts) qui lève avant tout
accès d'attribut. Donc `{{ steps.coord.ville | default(null) }}` **lève** — le filtre ne voit jamais
la valeur, l'accès `.ville` a déjà échoué. Les deux moteurs sont d'accord entre eux, ce qui est la
bonne nouvelle ; la règle d'écriture naïve, elle, ne marche pas.

**La décision : les steps du bloc qui n'ont rien produit publient un dict vide.** Celui qui a cédé
comme ceux qui ont été sautés exposent `{}` dans `steps.<id>`. `{{ steps.coord.ville | default(null) }}`
rend alors le repli, et la règle d'écriture annoncée devient vraie :

```json
"outputs": {
  "identite": "{{ steps.dossier.nom }}",
  "ville":    "{{ steps.coord.ville | default(null) }}"
}
```

L'effet de bord doit être documenté plutôt que découvert : **`steps.coord is defined` vaut désormais
vrai même quand le bloc a cédé.** C'est cohérent avec le partage des rôles que ce jalon installe — le
contexte de template porte de la *donnée*, `Result.step_results` porte ce qui s'est *passé*. Le
verdict « ce qu'on n'a pas eu » se lit dans le résultat, jamais dans l'absence d'une clé.

Deux options ont été écartées. **Documenter la forme longue**
(`{{ steps.coord.ville if steps.coord is defined else none }}`) : zéro code, mais une règle verbeuse
qu'un auteur oubliera, et différente de celle que la spec annonce. **Pré-semer partout**, y compris
les steps sautés par `when` hors bloc : plus cohérent globalement, mais ça change le comportement d'un
mécanisme livré et stable, et un Blueprint qui teste `is defined` sur une branche sautée en dépend —
hors périmètre.

### Les événements ne changent pas

L'étape fautive émet son `error` comme aujourd'hui : la défaillance ne doit jamais devenir invisible.
Les étapes sautées émettent `step_skipped`, déjà dans l'enum. **Aucun `EventType` n'est ajouté**, et
c'est délibéré — l'information « ce run est incomplet » vit dans le statut, pas dans un événement de
plus qu'aucun consommateur existant ne saurait lire.

> La conséquence pour un consommateur, à écrire dans la doc : **un événement `error` ne signifie plus
> à lui seul que le run a échoué.** Le verdict est `Result.status`. Les consommateurs actuels lisent
> déjà le résultat et non le flux d'événements pour décider, mais la règle mérite d'être dite.

### Imbrication

Un bloc `optional` peut contenir `if`, `repeat`, `for_each` et un autre `optional` — c'est la
mécanique de listes imbriquées qui existe déjà (`flow_nested_fields`). Un `optional` **imbriqué dans
un `optional`** qui cède ne fait céder que le sien : la tolérance ne remonte pas, elle s'arrête au
premier bloc englobant.

Ce qu'un bloc **ne rattrape pas** : une **annulation** traverse le bloc et arrête le run. Elle n'est
pas une défaillance de lecture, elle est la volonté de quelqu'un.

> Correction relevée à l'implémentation : la première version de ce paragraphe ajoutait « et une
> demande d'approbation refusée ». C'est faux, et le code le dit — un `confirm` refusé **ne lève
> pas**, il rend `{"approved": false}` et laisse le Blueprint en décider par une garde. Le seul
> `confirm` qui lève est celui dont le délai expire avec `on_timeout: "fail:CODE"`, et il est
> tolérable comme n'importe quel échec de step. Un auteur qui place un `confirm` dans un bloc
> facultatif obtient donc ce qu'il a demandé.

> Une précision qui évite une erreur d'implémentation : il n'existe **pas** de statut `cancelled`. Une
> annulation rend le run `failed`, en portant `RunCancelledError` comme cause — c'est la *nature* de
> l'erreur qui la distingue, jamais le statut
> ([`sdks/engine/src/runtime/cancel.ts`](../../sdks/engine/src/runtime/cancel.ts)). Et elle n'existe
> que côté embarqué : le moteur Python n'a pas de jumelle. Le bloc doit donc laisser passer
> `RunCancelledError` sans la convertir en tolérance, ce qui se teste.

### Ce que les consommateurs font d'un run partiel

Trois d'entre eux lisent le statut et n'ont jamais vu `partial`. La règle est **« partiel n'est pas un
échec, sauf pour une baseline »** :

| Consommateur | Comportement sur `partial` |
|---|---|
| `aetherius run` (CLI) | sort en **0** — le run a rendu ses sorties utiles |
| alerte `on: failure` | **ne se déclenche pas** |
| alerte `on: change` | **ignore le run sans déplacer sa baseline** |

Le troisième est le seul qui s'aligne sur l'échec, et pour une raison précise : des sorties
incomplètes ne sont pas une référence fiable. Déplacer la baseline dessus ferait produire au run
**complet** suivant un faux « changement ». C'est exactement pourquoi un échec ne la déplace pas déjà —
on suit ce précédent plutôt que d'inventer une règle.

Les trois décisions vivent sur **deux lignes**, et les voici pour éviter une chasse :

```python
# src/aetherius/cli/__init__.py  (commande `run`)
if result.status.value != "success":     # <- devient : seulement `failed`
    raise typer.Exit(1)

# src/aetherius/server/scheduler/alerts.py  (deux occurrences, dont le rendu du message)
failed = status != RunStatus.SUCCESS.value   # <- devient : status == RunStatus.FAILED.value
```

Et **le seul endroit où `partial` doit continuer de se comporter comme un échec** est la branche
`on == "change"` du même fichier, dont le commentaire dit déjà pourquoi pour les échecs : elle doit
sortir sans déplacer la baseline, donc tester le statut brut plutôt que le drapeau `failed` qui vient
de changer de sens. C'est le piège de cette question — corriger `failed` d'un seul geste ferait
silencieusement adopter une baseline incomplète.

Deux consommateurs n'ont **rien** à changer, et c'est utile de le savoir pour ne pas les « corriger » :
le daemon traduit déjà `PARTIAL` en `succeeded` (`src/aetherius/server/schemas.py`) et la Console le
colore déjà en ambre (`src/aetherius/console/widgets/run_summary.py`). Les deux attendaient ce jalon
sans le savoir.

### La validation ne s'aligne que sur le nouveau bloc

Aujourd'hui, un `repeat` sans `steps` passe la validation et n'échoue qu'à l'exécution. Ce jalon exige
que `optional` sans `steps` soit **refusé à la validation**, et n'y touche pour aucune des trois
sœurs.

La raison est propre au bloc, et c'est ce qui borne la règle : un `optional` mal formé qui échouerait
à l'exécution **se tolérerait lui-même** et deviendrait un no-op parfaitement silencieux. Aucune des
trois autres actions de flux ne porte ce piège.

Aligner les quatre est défendable et reste une suite possible ; ce serait changer le moment et le type
d'erreur de trois actions livrées et stables, donc une initiative hors du périmètre que la
[note de portée](README.md#implémenter-un-jalon) de la phase interdit.

### Les six cas limites, tranchés d'avance

Ils se rencontreront tous à l'implémentation ; les laisser au jugement du moment ferait diverger les
deux moteurs.

| Situation | Décision |
|---|---|
| un step **sans `id`** dans un bloc qui cède | rien à pré-semer : il n'apparaît pas dans le contexte de template |
| le bloc `optional` porte lui-même un `id` | il ne publie **rien** — une action de flux n'a pas de sorties, comme `if` et `repeat` |
| un step qui a **déjà publié** avant de céder | on ne l'écrase pas : le pré-semis ne concerne que ce qui n'a rien produit |
| un `when` **sur** le bloc `optional` | la garde décide d'abord : bloc entier `SKIPPED`, aucun pré-semis, run inchangé |
| un `optional` **imbriqué** dont l'intérieur cède | le bloc intérieur passe `PARTIAL` et l'extérieur **poursuit en `SUCCESS`** — la tolérance ne remonte pas |
| le **run**, dès qu'un bloc a cédé n'importe où | `PARTIAL`, y compris quand le bloc fautif était imbriqué et absorbé par son parent |

La dernière ligne mérite d'être lue deux fois : « la tolérance ne remonte pas » vaut pour les **blocs**,
jamais pour le **run**. Le statut du run se décide en balayant les résultats de steps, pas en
propageant de proche en proche.

Et une propriété à ne pas casser : `Result.error` reste **nul** sur un run partiel. Le run n'a pas
échoué ; l'erreur appartient au step qui l'a portée, et c'est là qu'un appelant la lit.

## Interfaces et fichiers

| Fichier | Ce qu'il gagne |
|---|---|
| `src/aetherius/core/actions/base.py` | `Capability.OPTIONAL`, ajoutée à `_VECTOR_CAPS`, à `FLOW_ACTIONS` et à `FLOW_NESTED_FIELDS` |
| `src/aetherius/core/actions/flow.py` | la `ActionSpec` `optional` (paramètre `steps`, requis) |
| `src/aetherius/core/runtime/flow.py` | `FlowOutcome`, `_flow_optional`, et le pré-semis des sorties du bloc |
| `src/aetherius/core/runtime/steps.py` | l'interprétation du bloc : capture de `StepFailed`, `SKIPPED` sur le reste, `PARTIAL` sur le bloc |
| `src/aetherius/core/blueprint/validator.py` | `optional` sans `steps` refusé, message explicite |
| `src/aetherius/core/runtime/engine.py` | statut final `PARTIAL`, et le rendu des sorties qui ne s'arrête plus à `SUCCESS` |
| `contracts/blueprint.schema.json` | la **description** de `steps` seulement (voir ci-dessous) |
| `contracts/actions.json` | **régénéré** — la garde de dérive existe déjà |
| `sdks/engine/src/blueprint/capabilities.ts` | `"optional"` dans la table embarquée, **écrite à la main** |
| `sdks/engine/src/runtime/steps.ts` · `flow.ts` · `engine.ts` | le miroir exact, y compris la condition de rendu des sorties |
| `sdks/engine/src/blueprint/validator.ts` | `optional` sans `steps` refusé, message explicite |
| `src/aetherius/cli/__init__.py` · `cli/schedule.py` | code de sortie : `partial` sort en 0 |
| `src/aetherius/server/scheduler/alerts.py` · `notify/sink.py` | `failed` cesse d'englober `partial` — **sauf** dans la branche `on: change` |
| `conformance/cases/` | les cas ci-dessous |
| `docs/blueprint-schema.md` · `docs/embedded.md` · `docs/acts/{vector,continuum}.md` · `docs/scheduler.md` · `docs/notifications.md` | la section « lecture facultative », la règle `default`, la note aux consommateurs |

### Trois corrections de fait, relevées à l'implémentation

Le premier jet de cette spécification affirmait trois choses que le code dément. Elles sont
corrigées ici, plutôt que laissées à découvrir :

1. **« La table de capacités par Act ne change pas »** est faux au pied de la lettre. Les actions de
   flux **figurent** nommément dans `_VECTOR_CAPS`, et il faut y ajouter `Capability.OPTIONAL` (les
   trois autres Acts en dérivent par union) **et** l'ajouter à `VECTOR_CAPABILITIES` côté embarqué,
   une liste écrite à la main dont aucune garde ne signalerait l'oubli — le test de sous-ensemble
   strict resterait vert, et le bloc serait refusé sur l'appareil. Ce qui ne change pas, c'est la
   *forme* de la table : aucune asymétrie par Act n'apparaît.
2. **Le schéma n'a besoin d'aucun changement structurel.** `$defs/step` est générique
   (`additionalProperties: true`) et déclare déjà `steps`. Seule sa **description** est complétée —
   ce qui change son empreinte, donc impose de resynchroniser la copie livrée
   `src/aetherius/_contracts/blueprint.schema.json` et de rebâtir le workspace TypeScript.
3. **`FLOW_ACTIONS` manquait à la liste.** Côté Python c'est lui qui route un step vers
   l'interprétation du flux ; côté TypeScript rien à faire, la détection est **dérivée du contrat
   généré**. Et dans les deux moteurs, la branche `optional` doit être insérée **avant** le
   `return for_each(...)` qui sert de fourre-tout, sans quoi un bloc serait interprété comme une
   boucle mal formée et échouerait sur un `items` absent.

Deux points que la spécification laissait ouverts, tranchés à l'implémentation : l'événement `done`
d'un run partiel porte le niveau **`info`** (seul un `failed` est une erreur, sans quoi la règle des
consommateurs se contredirait), et le bloc **ne tolère pas** une exception non typée — un défaut du
moteur n'est pas une lecture qui manque.

## Plan de test

Unitaires, des deux côtés :

| Cas | Attendu |
|---|---|
| bloc dont toutes les étapes réussissent | run `success`, bloc `success`, aucun `partial` nulle part |
| bloc dont la 2ᵉ étape sur 4 échoue | étape 2 `failed` avec son message, étapes 3 et 4 `skipped`, bloc `partial`, run `partial` |
| bloc en échec **et** étape hors bloc en échec ensuite | run `failed` — l'échec dur gagne |
| sorties d'un run `partial` | rendues, celles du bloc en `default(...)` valant leur repli |
| sortie référençant un bloc cédé **sans** `default` | le run échoue au rendu des sorties, message explicite |
| `steps.<id>` d'un step du bloc qui n'a pas produit | vaut `{}` — et `is defined` vaut vrai, ce qui est le comportement voulu, pas un accident |
| `optional` imbriqué dans `optional` | seul le bloc intérieur passe `partial` ; l'extérieur continue |
| annulation pendant un bloc (moteur embarqué) | le run s'arrête en `failed`, cause `RunCancelledError`, la tolérance ne s'applique pas |
| `optional` sans `steps` | refusé à la validation, sur les deux moteurs |
| `when` posé sur le bloc | bloc `SKIPPED`, run `success`, aucun pré-semis |
| bloc imbriqué qui cède | intérieur `partial`, extérieur `success`, **run `partial`** |
| run partiel | `Result.error` vaut `null` |
| CLI sur un run partiel | code de sortie **0** |
| alerte `on: change` sur un run partiel | ni alerte, ni baseline déplacée |

Conformance : **deux cas** — un bloc qui cède au milieu (statuts, événements et sorties comparés à
l'octet près entre les deux moteurs), et un cas de validation pour le refus de `optional` sans
`steps`. Le premier est celui qui compte : c'est le seul endroit qui prouve que les deux exécuteurs
sautent **exactement** les mêmes étapes.

## Exemple exécutable à livrer

Sous `examples/vector/`, un Blueprint qui lit une ressource publique puis tente une lecture
secondaire sur une adresse volontairement morte, et **rend quand même** la première dans ses sorties.
Un run `partial` observable en une commande, sans compte ni configuration.

La sonde dure exigée par [CONTRIBUTING](../../CONTRIBUTING.md) reste **dans ce dépôt** : un Blueprint
sous `examples/mobile/`, joué depuis l'application de démonstration sur un appareil réel, dont une
lecture bonus vise une adresse morte. Il doit rendre ses sorties principales, marquer le bloc
`partial`, et le run doit sortir en `partial` — pas en `failed`.

**L'adoption chez le consommateur n'appartient pas à ce jalon**, et c'est le précédent de
[3-I](3-i-extraction-texte.md) : le jalon prouve la capacité du moteur, le consommateur l'adopte
ensuite. La lier ici créerait une dépendance circulaire — il faudrait publier le paquet npm avant de
pouvoir clore le jalon — et ferait déborder la clôture sur un second dépôt. Côté consommateur ce
n'est de toute façon pas une release mais une **publication de fichiers** : le Blueprint entoure ses
lectures bonus d'un bloc, rien d'autre ne bouge.

## Définition de terminé

1. `optional` implémenté dans les deux moteurs, statuts et événements compris.
2. Le rendu des sorties ne s'arrête plus à `SUCCESS` dans les deux moteurs.
3. Tests unitaires du tableau ci-dessus, verts des deux côtés.
4. Deux cas de conformance.
5. `contracts/actions.json` régénéré, garde de dérive verte.
6. `make check-all` et `make conformance` verts (trois exécuteurs).
7. `docs/blueprint-schema.md`, `docs/embedded.md` et la doc d'Act portent le bloc, la règle
   `default` et la note « un `error` ne veut plus dire run échoué ».
8. Exemple exécutable joué pour de vrai, sur le poste **et** sur un appareil — le moteur embarqué est
   la cible qui a motivé le jalon.
9. `PARTIAL` cesse d'être un statut mort : le retirer casserait désormais un test.

## Critères d'acceptation

- Un Blueprint dont un bloc facultatif cède rend **toutes** les sorties qui ne dépendent pas de lui.
- Les deux moteurs sautent les mêmes étapes et rendent les mêmes statuts sur le même Blueprint.
- Un échec **hors** bloc reste un échec de run : aucune tolérance ne fuit hors des accolades.
- Le vocabulaire gagne **une action de flux**, aucun statut, aucun événement, aucune capacité par Act.

## Ce que ça débloque

Chez le consommateur, la fin d'un défaut mesuré et coûteux : un étudiant perdait son nom, son numéro
national et sa formation — tous trois déjà lus — parce qu'une page de coordonnées n'avait pas répondu.
Le remède actuellement envisagé de son côté est un **découpage en Blueprints séparés**, qui changerait
le contrat de sorties d'un parcours et multiplierait les runs. Ce jalon le rend inutile : le fichier
reste un seul run, une seule session, et gagne quatre accolades.

Au-delà de lui : toute lecture d'enrichissement, dans n'importe quel portail, cesse d'être un pari sur
la disponibilité d'une page annexe.
