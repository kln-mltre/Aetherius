# Recorder & création de Blueprints

Trois voies de création (voir aussi le [README](../README.md)) :

1. **Blueprint Studio** — création guidée dans la Console (`console/screens/builder/`), sans JSON.
   S'appuie sur le module headless [`builder/`](../src/aetherius/builder/).
2. **Blueprint recorder** — par démonstration : navigateur visible, capture des actions (CDP),
   synthèse de sélecteurs robustes, puis émission d'un Blueprint minimal et propre.
   Modules : [`recorder/`](../src/aetherius/recorder/) — `blueprint_recorder.py`, `capture.py`,
   `selector_synth.py`.
3. **JSON à la main** — contrôle total, validé contre le schéma.

## Gesture recorder

[`recorder/gesture_recorder.py`](../src/aetherius/recorder/gesture_recorder.py) capture des traces
de souris humaines réelles pour enrichir `stealth/gestures/data/human_library.json`.

Cette bibliothèque est **source-agnostique** ([docs/stealth.md](stealth.md)) : elle est aujourd'hui
amorcée par un **seed synthétique** (généré par [`stealth/gestures/seed.py`](../src/aetherius/stealth/gestures/seed.py),
`meta.source: "synthetic-seed"`) pour que la souris humaine fonctionne dès l'installation. Le gesture
recorder écrit exactement le même format ; ses traces réelles se substituent au seed sans changement
de code côté humanizer.
