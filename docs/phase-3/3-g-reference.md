# Jalon 3-G — Blueprints de référence & guide de migration

**Statut : à faire.** Dernier jalon de la phase. Le moteur existe et se déploie ; il reste à
démontrer qu'il remplace réellement le code qu'il prétend remplacer, et à écrire comment.

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
