# Jalon 3-H — Étendre la surcouche : les noms réservés

**Statut : livré**, passe sur appareil comprise —
[la campagne](../embedded.md#les-noms-réservés-sur-appareil) a joué les sept parcours sur iPhone,
sans trouver de défaut. Doc de référence :
[docs/embedded.md](../embedded.md#étendre--les-noms-réservés).

Le jalon 3-F a livré la livraison des Blueprints avec une règle nette : **le manifeste ne peut que
mettre à jour des noms déjà embarqués**. C'est la bonne règle pour *corriger*, et elle achète deux
choses qu'on ne veut pas perdre — le premier lancement hors ligne *pour chaque* Blueprint, et
l'impossibilité pour un manifeste compromis d'ajouter du comportement que personne n'a relu.

Elle ne tient plus dès qu'il s'agit d'**étendre**. Le cas est réel et il vient du consommateur du
moteur : une application universitaire qui veut ajouter le portail d'une nouvelle faculté en cours
d'année ([UKit](../../docs-ukit/README.md), sa phase de migration). Chaque nouvelle faculté coûte
aujourd'hui une publication sur les stores, alors que tout ce qui la distingue est un fichier de
données.

Ce jalon lève la règle, **en opt-in et bornée**, sans toucher au reste.

## Ce qui justifie la levée, et ce qui ne la justifie pas

Les deux raisons de la règle d'origine ne pèsent pas le même poids pour un nom **nouveau** :

| Raison de la règle | Pour un nom déjà embarqué | Pour un nom nouveau |
|---|---|---|
| Garantir un repli hors ligne | **tient** — l'application doit pouvoir jouer ce Blueprint sans réseau | **sans objet** — il n'existe pas encore pour l'utilisateur, il n'y a rien à quoi retomber |
| Empêcher l'ajout de comportement non relu | **tient** | **tient toujours** — c'est ce que le périmètre borne |

La levée porte donc uniquement sur la première ligne, et la seconde reste entière. C'est ce
déséquilibre qui rend le jalon défendable ; sans lui, il faudrait refuser.

## Objectif

1. Une application peut déclarer un **préfixe de noms réservé** sous lequel un manifeste a le droit
   d'**ajouter** des Blueprints qu'elle n'embarque pas.
2. Toutes les autres gardes s'appliquent inchangées, et le **périmètre de secrets** devient
   obligatoire dès que la capacité est activée.
3. Rien ne bouge pour une application qui ne l'active pas — y compris son comportement en cas de
   manifeste contenant des noms inconnus, qui continuent d'être ignorés.

## Dépendances

Jalon 3-F. Aucune autre : ni le moteur, ni les `contracts/`, ni le format de manifeste ne changent.

## Interfaces et fichiers

`sdks/react-native/src/delivery/` — le module de la livraison. Les fichiers concernés :

| Fichier | Ce qui change |
|---|---|
| `scope.ts` | **ajouté à la livraison** : la couverture du préfixe et ses gardes de construction, isolées parce qu'elles sont consultées à trois endroits (résolution, rafraîchissement, purge) et qu'il ne doit pas en exister trois versions — même raison que `verify.ts` |
| `types.ts` | `RegistryConfig` gagne la déclaration du préfixe réservé |
| `registry.ts` | la résolution accepte un nom absent du socle **si** il est couvert par le préfixe |
| `verify.ts` | la garde de périmètre devient obligatoire quand le préfixe est déclaré |
| `refresh.ts` | une entrée hors socle **et** hors préfixe reste ignorée, comme aujourd'hui |
| `cache.ts` | une entrée cachée dont le nom n'est plus couvert est **purgée** — retirer le préfixe doit désinstaller ce qu'il avait laissé entrer |

## Contrat

**Le format de manifeste ne change pas.** C'est le point le plus important du jalon : un manifeste
écrit pour ce jalon reste lisible par une application qui ne l'active pas, et elle ignore simplement
les entrées qu'elle n'embarque pas — exactement ce qu'elle fait déjà.

La déclaration est donc entièrement côté application :

```ts
new BlueprintRegistry({
  bundled,
  manifest: "https://…/manifest.json",
  cache: AsyncStorage,
  // Le seul ajout du jalon.
  allowNew: { prefix: "ukit.portail.", secrets: ["portail_user", "portail_pass"] },
});
```

`allowNew.secrets` est **obligatoire** quand `allowNew` est présent. Il n'a pas de valeur par défaut,
et surtout pas « l'union des secrets du socle » comme pour `allowedSecrets` : ce défaut-là est
raisonnable pour une mise à jour (le fichier remplacé déclarait déjà ces secrets, l'application a été
construite pour les fournir), et il ne l'est pas pour un fichier que personne n'a relu. Obliger à
l'écrire, c'est obliger à décider ce qu'un inconnu aura le droit de demander.

## Points de conception

- **Un préfixe, pas un motif.** Une comparaison de début de chaîne, sans joker ni expression
  régulière. Un motif serait plus expressif et beaucoup plus facile à écrire de travers — et une
  garde qu'on écrit de travers est une garde absente.
- **Le préfixe vide et le préfixe qui ne se termine pas par un séparateur sont refusés à la
  construction.** `""` ouvrirait tout ; `"ukit"` couvrirait `ukit.planning.semaine`, c'est-à-dire
  précisément les Blueprints que l'application embarque et qu'on ne veut pas voir remplaçables par
  un nom voisin. Refuser tôt et bruyamment vaut mieux qu'une surface ouverte par inadvertance. **Le
  séparateur retenu à la livraison est le point, et lui seul** — un `name` est un identifiant pointé
  au contrat, et commencer strict est relaxable plus tard sans casser une application existante ;
  l'inverse ne l'est pas.
- **Un nom embarqué gagne toujours sa règle habituelle.** Si un nom est *à la fois* dans le socle et
  couvert par le préfixe, c'est la règle de 3-F qui s'applique : version strictement supérieure. Le
  préfixe ajoute des noms, il n'assouplit rien pour ceux qui existent.
- **Retirer le préfixe désinstalle.** Une entrée arrivée par cette porte et qui n'est plus couverte —
  parce que l'application a changé son préfixe ou retiré `allowNew` — est purgée à la lecture
  suivante, pas conservée. Un interrupteur d'arrêt qui laisse en place ce qu'il a laissé entrer n'en
  est pas un.
- **`min_engine` prend tout son sens ici.** Un portail publié pour un moteur plus récent doit être
  ignoré **silencieusement** par les applications anciennes : c'est ce qui permet d'écrire un
  nouveau portail sans se demander qui l'exécutera.
- **Aucune nouvelle famille d'erreur.** Un nom refusé n'est pas un échec : c'est une entrée ignorée,
  visible dans le `RefreshReport` avec sa raison, comme les autres.

## Ce que ça change au modèle de menace

Le tableau de [docs/embedded.md](../embedded.md#le-modèle-de-menace-et-ce-quil-ne-couvre-pas) gagne
une ligne, et une seule :

| Menace | Traitement |
|---|---|
| Blueprint **ajouté** à distance sous un nom que l'application n'a jamais relu | **partiellement couverte.** Il est validé, son intégrité est vérifiée, il ne peut déclarer que les secrets de `allowNew.secrets`, et il n'existe que sous le préfixe réservé. Ce qu'il fait de ces secrets et où il envoie ses requêtes n'est **pas** borné — comme pour n'importe quel Blueprint distant depuis 3-F. |

La nature du risque ne change pas : un publieur compromis pouvait déjà livrer un Blueprint
malveillant sous un nom existant. Ce jalon augmente le **nombre de portes**, pas leur solidité — et
c'est pourquoi la ligne « publieur compromis » reste la première du tableau, et pourquoi le périmètre
de secrets devient obligatoire plutôt que déductible.

## Plan de test

Unitaires (`sdks/react-native/test/`) :

| Cas | Attendu |
|---|---|
| Nom hors socle, couvert par le préfixe, entrée valide | résolu, `origin: "remote"` |
| Le même, sans `allowNew` déclaré | ignoré, comme aujourd'hui |
| Nom hors socle, **hors** préfixe | ignoré, raison dans le rapport |
| Nom nouveau déclarant un secret hors `allowNew.secrets` | refusé **avant** le cache |
| Nom nouveau invalide au schéma, ou non portable sur ce moteur | refusé avant le cache |
| Nom nouveau avec `min_engine` supérieur | ignoré, silencieusement |
| Nom nouveau, empreinte fausse | refusé, rien n'est mis en cache |
| Entrée nouvelle en cache, puis `allowNew` retiré | **purgée**, non résolue |
| Entrée nouvelle en cache, puis préfixe modifié | purgée |
| Préfixe `""`, `"ukit"`, non terminé par un séparateur | refusé à la construction |
| Nom présent dans le socle **et** couvert par le préfixe | règle de 3-F, version strictement supérieure |
| Manifeste écrit avec des noms nouveaux, lu par une application **sans** `allowNew` | comportement de 3-F, inchangé |

Conformance : **rien**. Le corpus compare deux moteurs sur des Blueprints ; la livraison est
applicative et n'y figure pas.

## Exemple exécutable à livrer

Étendre [`examples/mobile/registry/`](../../examples/mobile/registry/) : un Blueprint publié sous un
nom **absent** du socle de l'application de démonstration, et un second sous un nom hors préfixe qui
reste ignoré. Les deux dans le même manifeste — c'est le contraste qui montre la garde, pas le cas
qui marche.

## Définition de terminé

1. `allowNew` implémenté, avec ses gardes de construction.
2. Tests unitaires du tableau ci-dessus, verts.
3. `make check-all` vert (`make conformance` inchangé).
4. [docs/embedded.md](../embedded.md) : la section « Le socle embarqué n'est pas optionnel » est
   nuancée, la ligne du modèle de menace ajoutée, `allowNew` documenté avec **la raison** de son
   périmètre obligatoire.
5. [README.md](../../README.md) : ligne de la Phase 3 amendée.
6. L'exemple de `examples/mobile/registry/` étendu et joué sur un appareil.

## Critères d'acceptation

- Une application qui n'active pas la capacité se comporte **exactement** comme avant, y compris
  face à un manifeste qui contient des noms inconnus.
- Un Blueprint ajouté à distance ne peut pas déclarer un secret que l'application ne lui a pas
  explicitement ouvert.
- Retirer la capacité ou changer le préfixe **désinstalle** ce qui était entré par là, sans réseau.
- Le format de manifeste est inchangé, octet pour octet.
