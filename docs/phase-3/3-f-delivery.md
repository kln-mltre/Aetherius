# Jalon 3-F — Livraison des Blueprints

**Statut : à faire.** Le gain produit de la phase. Sans ce jalon, un Blueprint embarqué dans le
binaire d'une application n'est qu'un fichier de configuration : le corriger demande toujours une
publication sur les stores. Avec lui, un site qui change se répare en quelques minutes, pour tous les
utilisateurs, sans republier quoi que ce soit.

## Objectif

1. Un **registre de Blueprints** : socle embarqué dans le binaire, surcouche distante.
2. Un **cache** et un comportement **hors ligne** irréprochables.
3. Un **contrôle d'intégrité**, un **repli** et un **interrupteur d'arrêt**.

## Dépendances

Jalon 3-E (la façade et le modèle d'erreur).

## Interfaces et fichiers

À créer sous [`sdks/react-native/src/`](../../sdks/react-native/src) :

- **`registry/`** — le registre : résolution d'un Blueprint par nom et version, source embarquée,
  source distante, cache, politique de rafraîchissement.

Références :

- [`core/blueprint/loader.ts`](../../sdks/engine/src/blueprint) (jalon 3-A) — tout Blueprint résolu
  passe par le même chargement et la même validation, quelle que soit sa provenance.
- [`docs/phase-3/3-b-expressions.md`](3-b-expressions.md) — l'absence d'exécution de code dynamique
  dans l'évaluateur est le socle sur lequel repose la sûreté de ce jalon.

## Contrat

Aucune modification des contrats du moteur. Ce jalon en définit un **nouveau, applicatif** : le
format du manifeste distant (quels Blueprints, quelles versions, quelles empreintes). Il doit être
spécifié dans `docs/embedded.md` avec le même soin que les contrats du moteur — c'est lui qui sera
servi en production.

## Points de conception

- **Le socle embarqué n'est pas optionnel.** Une application doit fonctionner au premier lancement,
  hors ligne, sans avoir jamais contacté le réseau. Les Blueprints embarqués dans le binaire sont la
  source de vérité de départ ; le distant est une **surcouche**, jamais un prérequis. Un registre
  purement distant transformerait une panne de CDN en application morte.
- **Le distant ne gagne que s'il est plus récent et valide.** L'ordre de résolution est explicite :
  cache local valide, sinon embarqué. Le rafraîchissement est **asynchrone et hors du chemin
  critique** — un run ne doit jamais attendre le réseau pour savoir quel Blueprint jouer.
- **Un Blueprint est de la donnée exécutable, et il faut le traiter comme tel.** Trois gardes, dans
  cet ordre d'importance :
  1. **Intégrité** — un Blueprint téléchargé dont l'empreinte ne correspond pas au manifeste est
     rejeté, silencieusement remplacé par la version précédente.
  2. **Périmètre** — un Blueprint distant ne peut pas élargir ce que le moteur sait faire. Il ne
     déclare pas de nouveaux secrets à sa guise : les secrets qu'un Blueprint peut réclamer sont
     bornés par l'application, pas par le fichier. Sans cette borne, un Blueprint distant compromis
     pourrait demander le contenu du trousseau et l'exfiltrer par une simple requête.
  3. **Sûreté d'exécution** — assurée par construction depuis le jalon 3-B : l'évaluateur n'exécute
     pas de code dynamique et n'expose aucune fonction native. C'est ce qui rend ce jalon
     défendable ; le rappeler explicitement dans la doc évite qu'on « optimise » plus tard
     l'évaluateur en réintroduisant une compilation dynamique.
- **L'interrupteur d'arrêt est le complément honnête du déploiement à distance.** Si un Blueprint
  distant se révèle mauvais, il faut pouvoir revenir à l'embarqué sans attendre. Un mécanisme de
  déploiement sans mécanisme de retour arrière n'est pas un mécanisme de déploiement.
- **Le versionnage protège des mises à jour croisées.** Un Blueprint distant peut être écrit pour une
  version du moteur plus récente que celle installée sur l'appareil — les anciennes versions d'une
  application vivent longtemps. Le manifeste doit porter une contrainte de compatibilité, et un
  Blueprint incompatible est ignoré au profit de l'embarqué, sans erreur visible pour l'utilisateur.
- **Ne pas réinventer un CDN.** Un dépôt de fichiers statiques servi par un CDN public suffit et
  constitue un motif déjà éprouvé pour du contenu éditorial d'application. Ce jalon livre le
  **client** et le **format**, pas une infrastructure.

## Plan de test

- **Résolution** : embarqué seul ; distant plus récent ; distant plus ancien (ignoré) ; distant
  invalide au schéma (rejeté, repli sur l'embarqué) ; distant incompatible avec la version du moteur
  (ignoré).
- **Intégrité** : empreinte incorrecte, réponse tronquée, manifeste malformé — tous rejetés sans
  jamais remplacer la version en place.
- **Périmètre** : un Blueprint distant réclamant un secret non autorisé par l'application est
  refusé ; une tentative d'exfiltration montée de bout en bout échoue.
- **Hors ligne** : premier lancement sans réseau ; réseau perdu pendant un rafraîchissement ; cache
  corrompu.
- **Interrupteur d'arrêt** : le retour à l'embarqué est effectif au run suivant.
- **Sur appareil** : le scénario complet — un Blueprint cassé volontairement, corrigé à distance, et
  l'application qui se répare sans réinstallation.

## Exemple exécutable à livrer

Un **manifeste d'exemple** et le parcours de bout en bout dans l'application de démonstration :
lancer un Blueprint embarqué, publier une correction, la voir prise en compte, déclencher
l'interrupteur d'arrêt et revenir à l'embarqué.

## Définition de terminé

Les 6 points de [CONTRIBUTING](../../CONTRIBUTING.md#définition-de--terminé-) ; `make check-all` et
`make conformance` verts ; `docs/embedded.md` complétée du format de manifeste, de l'ordre de
résolution, du modèle de menace et de ses limites explicites.

## Critères d'acceptation

Une application démarre et fonctionne hors ligne au premier lancement ; un Blueprint corrigé à
distance est pris en compte sans republication ; un Blueprint altéré, incompatible ou hors périmètre
est rejeté au profit de l'embarqué, sans dégrader l'expérience ; l'interrupteur d'arrêt ramène à
l'embarqué.
