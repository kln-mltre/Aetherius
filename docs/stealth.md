# Discrétion (stealth)

Couche transverse, orthogonale aux Acts, activée par `options.stealth` dans le Blueprint. No-op par
défaut. Applicable aux Acts navigateur (II, III, IV). Assemblée par
[`stealth/policy.py`](../src/aetherius/stealth/policy.py) et injectée dans la couche d'entrée du
driver.

## Composants

- **humanizer/** — `mouse` (rejeu de geste humain transformé scale+rotation, généralisé du BioMouse),
  `keyboard` (cadence, fautes, délais), `scroll` (ease-out cubique), `timing` (délais, distraction,
  precise_sleep sub-20ms).
- **gestures/** — chargement/downsampling/analyse/matching de la bibliothèque de gestes
  (`data/human_library.json`, alimentée par le gesture recorder).
- **fingerprint/** — `patch` (masques `navigator.webdriver`, `chrome.runtime`, `plugins`,
  `permissions`), `profile` (UA/viewport/timezone/WebGL/canvas cohérents).
- **session/** — `store` (profils persistants), `warmup` (historique authentique avant automation).
- **ml/** *(optionnel, roadmap)* — `motion_model` (motion génératif), `fingerprint_model`
  (échantillonnage cohérent). Derrière les mêmes interfaces.

## Décision IA

Le rejeu géométrique de gestes est le moteur **par défaut** (léger, éprouvé). Le ML est un upgrade
optionnel, pas un prérequis.
