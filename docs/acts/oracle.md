# Act III — Oracle (vision + discrétion)

Quand les sélecteurs sont fragiles ou absents, Oracle localise les cibles sur des captures d'écran
via un petit détecteur entraîné (ONNX) spécifique à la tâche, puis agit par coordonnées à travers la
couche de discrétion. La discrétion y est first-class (mais reste modulaire).

Cas fondateur : l'upload TikTok (`tiktok_driver.py`) avec son système BioMouse.

Modules : [`src/aetherius/acts/oracle/`](../../src/aetherius/acts/oracle/) —
`driver.py`, `perception.py`, `locator.py`, `model.py`.
Entraînement des modèles : [`training/`](../../training/).

Exemple : [`examples/oracle/tiktok-upload.blueprint.json`](../../examples/oracle/tiktok-upload.blueprint.json).

Recorder *(à venir)* : **annotation visuelle** — encadrer les cibles sur des captures d'écran pour
alimenter [`training/`](../../training/), branché comme un backend recorder (cf.
[docs/recorder.md](../recorder.md#recorder--les-acts)).
