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

- **Remote (via le daemon)** — même API, mais les runs sont délégués au daemon local (utile pour
  isoler le process navigateur, partager un daemon entre plusieurs clients, ou uniformiser avec les
  autres langages).

Le SDK Python n'a donc pas de paquet séparé à publier : il *est* le paquet `aetherius`. Ce dossier
documente le contrat client et hébergera le client remote mince quand le daemon sera implémenté.
La création de Blueprints se fait via la Console (`aetherius`) ; l'exécution, elle, est purement
pilotée par le code.
