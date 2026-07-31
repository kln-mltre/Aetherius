# Jalon 3-C — Runtime asynchrone & Act I (Vector)

**Statut : à faire.** Premier jalon qui produit une capacité utilisateur : à la fin, un Blueprint
`act: "vector"` tourne réellement sur un téléphone, et la requête part de l'appareil.

## Objectif

1. Le **runtime** asynchrone : moteur de run, exécuteur de steps, garde `when`, actions de flux,
   gestion des drivers, actions utilitaires partagées.
2. L'**Act I — Vector** sur `fetch` : requêtes, authentification, reprises, extraction.
3. Une **application de démonstration** qui sert de banc de vérification manuelle pour ce jalon et
   les suivants.

## Dépendances

Jalon 3-B (rendu d'expressions et extraction).

## Interfaces et fichiers

Références côté Python :

- [`core/runtime/engine.py`](../../src/aetherius/core/runtime/engine.py),
  [`steps.py`](../../src/aetherius/core/runtime/steps.py),
  [`flow.py`](../../src/aetherius/core/runtime/flow.py),
  [`context.py`](../../src/aetherius/core/runtime/context.py),
  [`drivers.py`](../../src/aetherius/core/runtime/drivers.py).
- [`acts/_shared.py`](../../src/aetherius/acts/_shared.py) — les actions act-agnostiques
  (`set`/`assert`/`emit`/`wait`).
- [`acts/vector/driver.py`](../../src/aetherius/acts/vector/driver.py),
  [`client.py`](../../src/aetherius/acts/vector/client.py),
  [`auth.py`](../../src/aetherius/acts/vector/auth.py).

À créer sous [`sdks/engine/src/`](../../sdks/engine/src) :

- **`runtime/`** — `engine.ts`, `steps.ts`, `flow.ts`, `context.ts`, `drivers.ts`.
- **`acts/shared.ts`** — les actions act-agnostiques.
- **`acts/vector/`** — `driver.ts`, `client.ts`, `auth.ts`.

À créer sous [`examples/`](../../examples/) :

- **`examples/mobile/`** — une application de démonstration minimale, et au moins un Blueprint
  exécutable zéro configuration.

## Contrat

Aucune modification des contrats. Le moteur doit émettre **exactement** les mêmes événements que le
moteur Python, dans le même ordre et avec les mêmes `step_id` — c'est ce que vérifie le corpus de
conformance, et c'est ce qui permet à une UI d'être écrite une fois.

## Points de conception

- **La conversion en asynchrone est mécanique sauf à trois endroits.** L'exécuteur de steps, les
  actions de flux (`repeat` et `for_each` deviennent des boucles séquentielles `await`, jamais
  parallèles — l'ordre est observable) et `wait`. Partout ailleurs, `Promise` ne change rien à la
  sémantique. La tentation de paralléliser `for_each` « puisqu'on est en asynchrone » doit être
  écartée : elle rendrait les runs non reproductibles et casserait les Blueprints dont les
  itérations partagent une session.
- **`fetch` sur mobile n'est pas `httpx`.** Trois écarts à traiter de front, pas à découvrir en
  production :
  - **Les en-têtes `Set-Cookie` ne sont pas lisibles depuis JavaScript.** Une stratégie
    d'authentification qui inspecte un cookie de session ne peut pas fonctionner telle quelle.
  - **Les redirections sont suivies d'office** et les réponses intermédiaires ne sont pas
    observables. Un enchaînement d'authentification à base de tickets fonctionne — mais en aveugle :
    on constate le résultat, on ne pilote pas les étapes.
  - **Le magasin de cookies est celui de la plateforme**, partagé par le processus. Il n'y a pas
    d'isolation par run gratuite.

  Ce jalon doit **décider et documenter** la stratégie qui en découle, y compris ce qui devient une
  limite du moteur embarqué. C'est le point qui mérite le plus de temps.
- **Les reprises restent une politique, pas un comportement câblé.** `retries.max` et le type de
  recul (`none`/`linear`/`exponential`) sont des données du Blueprint ; leur sémantique doit être
  identique des deux côtés, y compris le cas `max: 0` qui désactive toute reprise. Ajouter du
  jitter « parce que c'est mieux » ferait diverger les deux moteurs.
- **Le budget de dépendances est un critère de conception.** Chaque paquet ajouté alourdit le binaire
  d'une application mobile. La règle : rien qui ne soit indispensable, rien qui tire des modules de
  plateforme, et un poids justifié explicitement dans la doc.
- **L'application de démonstration est un outil de vérification, pas une vitrine.** Elle sert le
  point 5 de [CONTRIBUTING](../../CONTRIBUTING.md#définition-de--terminé-) — « le vrai run, pas
  seulement les tests » — sur le seul environnement qui compte ici : un appareil. Elle doit rester
  minimale et le rester dans les jalons suivants.

## Plan de test

- **Runtime** : ordre des steps ; `when` faux produit un statut `skipped` et l'événement
  correspondant, avec l'expression **brute** dans les données ; `if`/`repeat`/`for_each` y compris
  imbriqués, avec la variable de boucle correctement restaurée en sortie ; un `for_each` sur zéro
  élément ; un step en échec arrête le run et produit un `Result` en échec, sans pile.
- **Vector** : méthodes et encodages (`form`, `json`, `params`) ; `expect.status` satisfait et
  violé ; reprise sur erreur de transport puis succès ; reprises épuisées ; `max: 0` ; chaque
  stratégie d'authentification ; `json` et `form` simultanés refusés.
- **Sur appareil** : au moins un Blueprint réel joué depuis l'application de démonstration, en
  vérifiant que la requête part bien de l'appareil et non d'une machine de développement.
- **Conformance** : le corpus gagne des runs complets d'Act I — mêmes sorties, même séquence
  d'événements, mêmes erreurs sur les cas d'échec.

## Exemple exécutable à livrer

Un Blueprint `vector` **zéro configuration** exécutable depuis l'application de démonstration comme
depuis `aetherius run` — le même fichier, les deux moteurs. Un endpoint public et autorisé, dans
l'esprit des exemples existants.

## Définition de terminé

Les 6 points de [CONTRIBUTING](../../CONTRIBUTING.md#définition-de--terminé-), le point 5 étant
joué **sur un appareil ou un simulateur** ; `make check-all` et `make conformance` verts ;
`docs/embedded.md` livrée avec la stratégie cookies/redirections et le budget de dépendances ;
`@aetherius/engine` peut sortir de `private` et rejoindre le flux de publication.

## Critères d'acceptation

Un Blueprint `vector` d'`examples/` produit le même `Result` et la même séquence d'événements sur les
deux moteurs ; le même Blueprint tourne depuis l'application de démonstration sur un appareil ; les
limites de `fetch` sur mobile sont écrites, et chacune est couverte par un test qui montre le
comportement retenu.
