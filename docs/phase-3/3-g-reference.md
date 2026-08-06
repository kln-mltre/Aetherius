# Jalon 3-G — Blueprints de référence & guide de migration

**Statut : livré.** Doc de référence : [docs/mobile-migration.md](../mobile-migration.md), et
[docs/embedded.md](../embedded.md#porter-un-cas-dusage-réel) pour ce que le port a trouvé. Dernier
jalon de la phase. Le moteur existait et se déployait ; il restait à démontrer qu'il remplace
réellement le code qu'il prétend remplacer, et à écrire comment.

> **Ce que la livraison a changé au plan.** Le contrat annoncé était « aucun » — et l'intérêt du
> jalon était précisément là : si porter un cas d'usage réel demande de toucher au moteur, c'est que
> la phase n'est pas finie. Il a fallu y toucher **huit fois**. Une URL construite de deux variables
> ne se rendait pas ; un prédicat `where` sur un champ imbriqué rendait des données **différentes**
> selon le moteur ; le littéral `true` en minuscules levait d'un côté ; le mode booléen de `default`
> manquait de l'autre ; et `options.stealth.user_agent`, documenté et implémenté, était refusé par
> le schéma partagé. S'y ajoutent deux défauts d'ergonomie de l'échec : le code d'un `fail:CODE`
> n'atteignait jamais l'appelant côté Python, et sur un appareil une opération en échec revenait en
> **silence** plutôt qu'avec sa raison. Le plus structurant est le dernier, et il n'a été trouvé
> qu'en jouant un vrai client web sur un vrai téléphone : un **changement de fragment** était pris
> pour un nouveau document, si bien que l'agent injecté se réinstallait par-dessus une opération en
> vol, qui ne répondait alors plus jamais. Aucun n'était visible depuis le dépôt : il
> fallait écrire un Blueprint contre une source qu'on n'a pas choisie, et le jouer sur un téléphone.
> Les huit correctifs sont gardés par des tests miroir et des cas de conformance.

## Objectif

1. Porter les **Blueprints de référence** issus des cas d'usage réels, et les vérifier sur le moteur
   embarqué.
2. Livrer le **guide de migration** : comment un service HTTP écrit à la main et une WebView cachée
   deviennent des Blueprints, et ce qui reste du ressort de l'application.

## Dépendances

Jalon 3-F (le moteur complet et sa livraison).

## Interfaces et fichiers

Déjà en place — le dépôt porte la matière première depuis la Phase 1 :

- [`legacy_examples/ukit_project_examples/`](../../legacy_examples/) — le code d'origine et sa
  **carte de provenance**, qui relie chaque fichier au composant Aetherius qu'il a inspiré.
- [`examples/vector/ukit-planning-week.blueprint.json`](../../examples/vector/ukit-planning-week.blueprint.json)
  — le service d'emploi du temps, déjà déclaratif.
- [`examples/continuum/ukit-scolarite-login.blueprint.json`](../../examples/continuum/ukit-scolarite-login.blueprint.json)
  et [`bordeaux-cas-login.blueprint.json`](../../examples/continuum/bordeaux-cas-login.blueprint.json)
  — le parcours d'authentification.

À créer :

- **`examples/mobile/`** — les Blueprints manquants pour couvrir un cas d'usage mobile complet, et
  le regroupement de ceux qui existent déjà.
- **`docs/mobile-migration.md`** — le guide.

## Contrat

Aucun. Ce jalon ne produit que des Blueprints et de la documentation. C'est précisément son intérêt :
si porter un cas d'usage réel demandait de toucher au moteur, c'est que la phase n'est pas finie.

## Points de conception

- **Le catalogue à couvrir est déjà cartographié.** Un cas d'usage mobile réel mélange deux natures
  de source, et les deux Acts embarqués y répondent exactement :
  - **API tierces, Act I** — un calendrier universitaire (dont les constantes magiques `resType`,
    `calView`, `colourScheme` et la borne de fin exclusive deviennent des `inputs` et des `vars`
    documentés), une API d'affluence de lieux (en-têtes spécifiques, plusieurs points d'interrogation
    géographiques, catégories numériques non documentées), un service de restauration, et un fichier
    éditorial statique servi par CDN.
  - **Portail authentifiant, Act II** — l'enchaînement authentification unifiée puis pages internes,
    avec ses sélecteurs positionnels et ses attentes.
- **Les fragilités qui disparaissent, et celles qui restent.** Le guide doit être honnête sur les
  deux. Disparaissent : les constantes magiques disséminées, le parsing par expression régulière, les
  erreurs avalées, le JavaScript injecté non typé, l'échappement manuel des identifiants.
  **Restent** : un sélecteur positionnel reste un sélecteur positionnel. La différence n'est pas
  qu'il devient robuste — c'est qu'il devient **une ligne dans un fichier de données**, corrigeable à
  distance en quelques minutes au lieu d'attendre une publication sur les stores. Promettre autre
  chose serait mentir.
- **Ce qui ne devient pas un Blueprint.** Le guide doit tracer la frontière aussi nettement que ce
  qu'il couvre : le cache et la persistance, l'internationalisation, le rendu, la navigation et la
  logique métier restent du code applicatif. Aetherius remplace **l'accès au web**, pas la couche de
  service entière. Une migration qui essaierait d'absorber le cache dans les Blueprints échouerait,
  et pour de bonnes raisons.
- **La stratégie de migration doit être incrémentale.** Un service à la fois, derrière sa signature
  typée existante, avec l'ancien code en repli le temps de la vérification. Un remplacement en bloc
  d'une couche d'accès réseau est irréaliste sur une application en production.
- **Les identifiants réels passent par la configuration locale.** Le parcours authentifié ne peut pas
  être zéro configuration : il se teste avec de vrais identifiants fournis à l'exécution, jamais
  écrits dans un fichier — la règle est déjà posée par
  [CONTRIBUTING](../../CONTRIBUTING.md#exemples-exécutables) et [`docs/secrets.md`](../secrets.md).
  Les Blueprints à identifiants sont marqués comme tels et ne comptent pas comme l'exemple exécutable
  zéro configuration requis.

## Plan de test

- **Chaque Blueprint de référence** est validé contre le schéma par la CI (déjà automatique pour tout
  ce qui vit sous `examples/`), et **joué en réel** au moins une fois sur les deux moteurs.
- **Comparaison de sorties** : pour au moins un Blueprint de chaque nature (API tierce et portail
  authentifiant), les données extraites par le moteur embarqué et par le moteur Python sont
  identiques. C'est la démonstration finale de la parité, sur des cas réels et non sur des fixtures.
- **Sur appareil** : le parcours d'authentification complet, joué depuis l'application de
  démonstration, avec les sondes dures exigées par
  [CONTRIBUTING](../../CONTRIBUTING.md#définition-de--terminé-) — dont un cas conçu pour échouer
  (identifiants faux, page indisponible, sélecteur devenu introuvable). Un échec **propre et
  explicable** est un résultat valide ; un comportement surprenant est un correctif ou une limite à
  documenter avant de clore.
- **Le guide se vérifie en le suivant** : partir d'un service écrit à la main, appliquer le guide,
  obtenir le même résultat. Un guide qu'on n'a pas parcouru soi-même n'est pas un guide.

## Exemple exécutable à livrer

L'ensemble d'`examples/mobile/`, dont **au moins un Blueprint zéro configuration** par Act. Les
Blueprints à identifiants sont livrés en plus, documentés comme tels.

## Définition de terminé

Les 6 points de [CONTRIBUTING](../../CONTRIBUTING.md#définition-de--terminé-) ; `make check-all` et
`make conformance` verts ; `docs/mobile-migration.md` livrée ; `docs/embedded.md` finalisée ; la
Phase 3 basculée en « terminée » dans le [README](../../README.md), section « État d'avancement ».

## Critères d'acceptation

Un cas d'usage mobile réel est intégralement décrit par des Blueprints, sans une ligne de JavaScript
injecté écrite à la main ; les données extraites sont identiques sur les deux moteurs ; le guide
permet à quelqu'un d'autre de migrer un service sans contexte oral ; les fragilités qui subsistent
sont nommées, pas passées sous silence.

## Ce qui a été livré

- **[`examples/mobile/reference/`](../../examples/mobile/reference/)** — six Blueprints, sur les
  vrais services : un fichier éditorial servi par CDN, une API de restauration, une API d'affluence
  de lieux, un serveur d'emplois du temps, et le **parcours authentifiant** en deux volets (le
  dossier administratif, puis la messagerie) qui remplace 323 lignes de composant WebView. Le
  découpage n'est pas un contournement : c'est la distinction que l'application d'origine fait déjà
  entre son parcours froid et son parcours chaud, et chaque service rebondit seul sur
  l'authentification unifiée. Quatre sont zéro configuration ; les deux autres sont marqués
  « identifiants requis » et ne comptent pas comme l'exemple exécutable.
- **[`docs/mobile-migration.md`](../mobile-migration.md)** — le guide : la frontière, l'ordre de
  migration, les deux ports pas à pas (service HTTP et WebView cachée), ce qui **reste** fragile, ce
  qui n'est pas exprimable et pourquoi, la stratégie incrémentale, et comment vérifier.
- **Les huit correctifs** trouvés en portant, avec leurs tests miroir et leurs cas de conformance
  (`extract-where-nested-field`, `extract-where-absent-nested-field`,
  `extract-where-lower-case-literals`, `expr-two-expressions-no-surrounding-text`,
  `expr-default-boolean-mode`, et les cinq cas de validation des Blueprints de référence).
- **Le banc de vérification** gagne cinq cartes ; le dépôt UKit n'a **pas** été modifié — la
  migration applicative se fait dans son propre dépôt, service par service.

### La limite que la campagne a fini par nommer

Les six Blueprints de référence sont vérifiés sur l'appareil, sorties identiques au moteur Python.
Le dernier — la messagerie — a demandé **cinq passes**, et chacune a éliminé une hypothèse sans
toucher la cause : ce n'était ni le sélecteur, ni le DOM, ni le ralentissement des minuteurs hors
écran, ni le portail. Ce qui a tranché est une sonde qui ne demandait rien à la page sinon **ce
qu'elle était** — URL, titre, nombre de nœuds : tout répondait, et à l'identique du poste.

La cause est alors devenue lisible : **une opération émise pendant un enchaînement de navigations se
perd**. Le moteur ne rejoue que ce qu'il sait avoir perdu, et il n'apprend pas tous les
remplacements de document qu'une redirection en cascade produit. Le Blueprint livré laisse donc la
page arriver avant de l'interroger, par une pause **visible** — un contournement écrit comme tel,
pas déguisé, et la limite du moteur est nommée dans
[docs/embedded.md](../embedded.md#sondes-du-jalon-3-g).

### Un morceau d'infrastructure qui disparaît

Le Blueprint d'emplois du temps visait d'abord le **point d'entrée dédié** que l'application
d'origine interroge — un relais, tombé en panne pendant la livraison (statut 522). La bonne question
est venue de l'utilisateur : *pourquoi passer par ce relais alors que le service de l'université
répond directement ?* Parce qu'une page web ne peut pas appeler un autre domaine sans son accord, et
que l'application, elle, était une WebView. Une requête émise **nativement depuis l'appareil** n'y
est pas soumise : le Blueprint vise donc le service directement, et le relais — un serveur à
héberger, à payer et à surveiller — n'a plus de raison d'être. C'est un gain de migration qu'aucune
relecture de code n'aurait produit, et il est passé de « bloqué par un tiers en panne » à « vérifié,
sorties identiques sur les deux moteurs ».
