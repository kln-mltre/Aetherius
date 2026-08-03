# Jalon 3-E — Intégration applicative

**Statut : livré.** Doc de référence :
[docs/embedded.md](../embedded.md#la-surface-applicative). Le moteur tournait ; ce jalon décide de
**ce qu'une application voit de lui** — la surface publique du moteur embarqué, celle qu'on ne pourra
plus changer sans casser ses consommateurs.

Livré : la façade `Aetherius` (mêmes noms que le SDK daemon), la résolution des secrets par un
magasin **injecté** (le trousseau de l'OS par défaut) et le masquage des valeurs sur le chemin de
sortie, `confirm` en modal natif avec la sémantique exacte du jalon 2-E, l'annulation d'un run, et le
modèle d'erreur `describeFailure` — le point le plus structurant, puisque c'est lui qui rend une
source en panne distinguable d'une réponse vide.

Deux défauts du jalon 3-D trouvés par les sondes et corrigés au passage : l'auto-attente ne
s'appliquait pas à une cible **absente** (un `click` échouait en 6 ms au lieu d'attendre, là où
Playwright attend), et un sélecteur périmé se présentait comme un bug du moteur — **des deux côtés**,
le moteur Python laissant même échapper la temporisation Playwright en `RunError`. Détail et
correctifs : [docs/embedded.md](../embedded.md#sondes-du-jalon-3-e).

**Joué sur un iPhone** (Expo Go SDK 54, téléphone en 5G) : le parcours complet
`quotes-login-confirm` — trousseau, modal réel, secret masqué dans le flux, `connecte: 1` —, le CAS
de l'université de bout en bout depuis le réseau du téléphone, le corps `form` de UKit contre le vrai
serveur ADE, et `carried: true` sur la sonde de session. La campagne a trouvé **deux défauts du jalon
3-D** que rien hors appareil ne pouvait produire (voir
[docs/embedded.md](../embedded.md#sondes-du-jalon-3-e)), et la seconde passe les a vérifiés corrigés
là où ils s'étaient manifestés. Elle a du même coup fermé les points laissés ouverts aux jalons 3-C
(corps `form` sur appareil) et 3-D (portail authentifiant réel).

**La vérification sur appareil est complète** : parcours nominal, refus au modal, expiration pendant
que l'application dort, annulation qui libère la WebView, persistance de session, `LOGIN_FAILED` sur
de mauvais identifiants, et mode avion. Elle a coûté **quatre correctifs du moteur** — redirection,
horloge de la WebView, cycle de vie de la vue persistante, navigation vers la page déjà affichée —
et deux du banc lui-même. Aucun n'était atteignable depuis un double : deux tenaient à des
comportements d'iOS (minuteurs gelés hors écran, cookie de session lié au contexte de navigation) que
seule une exécution réelle révèle.

Le reste — façade, secrets, hygiène, `confirm`, concurrence, modèle d'erreur — est gardé par la suite
de tests, le corpus de conformance et les sondes contre de vraies sources.

## Objectif

1. La **façade** `Aetherius` : charger un Blueprint, le jouer, en suivre le déroulé.
2. La **résolution des secrets** par le trousseau de l'OS, et l'hygiène qui va avec.
3. Le **flux d'événements** consommable par une interface.
4. L'action **`confirm`** : garer un run jusqu'à une décision humaine.
5. Un **modèle d'erreur** exploitable.

## Dépendances

Jalon 3-D (les deux Acts sont exécutables).

## Interfaces et fichiers

Déjà en place (stubs à implémenter) :

- [`sdks/react-native/src/secrets.ts`](../../sdks/react-native/src/secrets.ts) — `SecretResolver`.
- [`sdks/react-native/src/index.ts`](../../sdks/react-native/src/index.ts) — la surface exportée.

Références :

- [`sdks/client/src/client.ts`](../../sdks/client/src/client.ts) — la façade du SDK daemon, dont les
  noms doivent être repris.
- [`core/runtime/approvals.py`](../../src/aetherius/core/runtime/approvals.py) et
  [`docs/human-in-the-loop.md`](../human-in-the-loop.md) — la sémantique de `confirm`.
- [`docs/secrets.md`](../secrets.md) — la doctrine des secrets côté Python.

À créer sous [`sdks/react-native/src/`](../../sdks/react-native/src) :

- **`aetherius.ts`** — la façade.
- **`secrets/`** — l'adaptateur trousseau.
- **`confirm/`** — le rendez-vous d'approbation et sa surface d'interface.

## Contrat

Aucune modification des contrats. `confirm` réutilise les événements `input_requested` /
`input_provided` **déjà définis** par `contracts/events.schema.json` depuis le jalon 2-E — d'où
l'importance de corriger au jalon 3-A la dérive du SDK client, qui les ignore encore.

## Points de conception

- **Les mêmes noms que le SDK daemon.** `client.run(blueprint, { inputs, secrets, onEvent })` doit
  se lire identiquement, qu'on pilote un moteur distant ou qu'on en embarque un. Le choix
  d'architecture — moteur embarqué ou daemon — ne doit pas se voir dans le code appelant.
- **Les secrets ne quittent jamais l'appareil, et ne franchissent jamais la frontière du journal.**
  L'invariant du moteur Python est reproduit tel quel : un événement `step_skipped` publie
  l'expression `when` **brute**, jamais sa valeur rendue, parce que cette valeur peut contenir un
  secret. Cette discipline doit être testée, pas seulement documentée.
- **La résolution des secrets est branchable.** Le trousseau de l'OS est l'implémentation par défaut,
  pas une dépendance du moteur. Une application qui gère ses identifiants autrement doit pouvoir
  fournir la sienne — c'est aussi ce qui rend le moteur testable sans trousseau.
- **`confirm` sur mobile est plus naturel qu'ailleurs.** Côté Python, il a fallu quatre surfaces
  (console, terminal, API, notification) pour poser une question à un humain. Sur un téléphone, il y
  en a une seule et elle est évidente : un modal. Reprendre la sémantique exacte du jalon 2-E — le
  run reste vivant et garé, le statut ne change pas, le délai d'attente est **obligatoire** et
  `on_timeout` vaut **refus** par défaut. Le refus par défaut n'est pas de la prudence décorative :
  une application mise en arrière-plan ne répondra jamais, et le comportement sûr doit être celui qui
  arrive tout seul.
- **Le modèle d'erreur est le point le plus structurant de ce jalon.** Le réflexe répandu, dans les
  couches de service mobiles, est de tout rattraper et de rendre une valeur vide. Le résultat est
  qu'**une source en panne et une réponse légitimement vide deviennent indistinguables** : un écran
  qui affiche « aucun résultat » peut masquer un service indisponible. Le moteur lève des erreurs
  **typées** (jalon 3-A) et ne décide pas à la place de l'application ; il fournit de quoi
  distinguer les cas. C'est l'adaptateur applicatif qui traduit, et il doit pouvoir le faire
  finement. Ce jalon doit livrer le motif recommandé, pas seulement l'outillage.
- **L'annulation est un besoin réel sur mobile, pas un raffinement.** Un utilisateur qui quitte un
  écran, une application mise en arrière-plan : un run doit pouvoir être interrompu, et libérer sa
  WebView. Sans cela, une WebView cachée survit à l'écran qui l'a demandée.
- **Le flux d'événements est déjà une UI de progression.** Les événements du moteur portent ce qu'il
  faut pour afficher une progression étape par étape — c'est précisément ce que les applications
  réimplémentent aujourd'hui à la main avec des états ad hoc. Le montrer dans la doc vaut mieux que
  de le décrire.

## Plan de test

- **Façade** : run nominal, run en échec, entrées manquantes, secret absent, annulation en cours de
  run (les ressources sont libérées), deux runs concurrents.
- **Secrets** : un secret n'apparaît dans **aucun** événement ni journal, y compris quand un step est
  sauté par un `when` qui le référence, et y compris dans le message d'une erreur.
- **`confirm`** : approbation, refus, expiration (par défaut refus), application mise en arrière-plan
  pendant l'attente, décision arrivant après l'expiration (doit être ignorée).
- **Erreurs** : chaque famille d'erreur typée remonte distinctement jusqu'à l'appelant ; une source
  en panne et une réponse vide produisent deux issues différentes.
- **Sur appareil** : un parcours complet piloté depuis une interface réelle, avec progression et un
  `confirm` réel.

## Exemple exécutable à livrer

L'application de démonstration est étendue en **prise en main de référence** : un écran qui lance un
Blueprint, affiche la progression issue du flux d'événements, gère une confirmation et affiche
proprement les trois issues (succès, échec, source indisponible). C'est l'équivalent, côté mobile,
des captures de la Console.

## Définition de terminé

Les 6 points de [CONTRIBUTING](../../CONTRIBUTING.md#définition-de--terminé-), le point 6 (prise en
main UI) s'appliquant ici à l'application de démonstration ; `make check-all` et `make conformance`
verts ; `docs/embedded.md` complétée de la surface publique, de la doctrine des secrets et du modèle
d'erreur recommandé.

## Critères d'acceptation

Une application joue un Blueprint en quelques lignes, avec les mêmes noms que le SDK daemon ; aucun
secret n'apparaît dans le flux d'événements, prouvé par un test ; un `confirm` gare le run et le
reprend après décision, et expire en refus si personne ne répond ; annuler un run libère sa WebView ;
une panne de source et une réponse vide sont distinguables par l'appelant.
