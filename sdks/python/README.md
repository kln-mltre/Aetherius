# Aetherius — SDK Python

Deux modes, un seul objet `Aetherius` :

- **In-process (sans daemon)** — le plus direct pour un projet Python. C'est la façade exposée par
  le paquet lui-même :

  ```python
  from aetherius import Aetherius

  client = Aetherius()
  result = client.run("blueprints/ukit-planning-week.blueprint.json",
                      inputs={"group": "TP-A1", "monday": "2026-09-07"})
  print(result.outputs["events"])
  ```

- **Remote (via le daemon)** — déléguer les runs au daemon local (`aetherius serve`), utile pour
  isoler le process navigateur, partager un daemon entre plusieurs clients, ou uniformiser avec les
  autres langages. Le daemon existe (voir [docs/daemon.md](../../docs/daemon.md)) et est déjà consommé
  par le **SDK TypeScript** ([`sdks/client`](../client)). Un **client remote mince Python**
  (à parité avec le SDK TS, par-dessus `httpx` déjà présent) est un ajout **différé** : le mode
  in-process ci-dessus couvre le cas Python le plus courant.

Le SDK Python n'a donc pas de paquet séparé à publier : il *est* le paquet `aetherius`. La création de
Blueprints se fait via la Console (`aetherius`) ; l'exécution, elle, est purement pilotée par le code.
