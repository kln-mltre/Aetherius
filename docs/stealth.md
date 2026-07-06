# Discrétion (stealth)

**Statut : implémenté et branché dans Continuum (Act II).** Couche transverse, orthogonale aux Acts,
activée par `options.stealth` dans le Blueprint. No-op par défaut (`"off"`), donc le comportement
historique est strictement inchangé quand elle n'est pas demandée. Applicable à tout Act navigateur
(II aujourd'hui ; III et IV réutiliseront la même couture). Décodée par
[`stealth/policy.py`](../src/aetherius/stealth/policy.py) et injectée dans la couche d'entrée du
driver via [`BrowserSession`](../src/aetherius/acts/continuum/browser.py).

Le patron de référence est le système *BioMouse* éprouvé des projets d'origine (voir
[`legacy_examples/`](../legacy_examples/)) : rejeu géométrique de gestes, frappe humaine, scroll
adouci, masques de fingerprint.

## Activation

Trois formes, toutes validées par le schéma ([`contracts/blueprint.schema.json`](../contracts/blueprint.schema.json)) :

```json
"options": { "stealth": "off" }                     // défaut : aucune discrétion
"options": { "stealth": "human" }                   // preset : tout activé + fingerprint chrome-desktop
"options": { "stealth": {                            // configuration fine
  "mouse": "gestures",        // "off" | "gestures"
  "keyboard": "human",        // "off" | "human"
  "scroll": "eased",          // "off" | "eased"
  "timing": { "distraction": 0.1 },   // proba d'une pause "distraction" occasionnelle (0..1)
  "fingerprint": "chrome-desktop"     // nom d'un profil de fingerprint, ou absent
} }
```

Une forme invalide (preset inconnu, valeur d'enum hors liste, clé inconnue) échoue à la construction
avec une `BlueprintValidationError` claire — jamais de dégradation silencieuse.

## Fonctionnement

`build_policy(options.stealth)` produit une `StealthPolicy` gelée. Au démarrage du navigateur,
`BrowserSession` :

1. applique les **options de contexte** du profil de fingerprint (user agent, viewport, locale,
   timezone) à la création du contexte Playwright ;
2. injecte, avant tout script de page (`add_init_script`), le **patch anti-automation**
   ([`fingerprint/patch.py`](../src/aetherius/stealth/fingerprint/patch.py) : `navigator.webdriver`,
   `chrome.runtime`, `permissions`, `plugins`) puis le **script de cohérence** du profil
   ([`fingerprint/profile.py`](../src/aetherius/stealth/fingerprint/profile.py) :
   `platform`/`hardwareConcurrency`/`deviceMemory`/`languages`, vendor/renderer WebGL) ;
3. construit un `HumanInput` si la policy humanise au moins une entrée.

Le driver route alors les actions interactives (`click`/`hover`/`fill`/`type`/`scroll`) vers ce
`HumanInput` quand la policy le demande ; sinon elles empruntent les actions Playwright brutes
(inchangées). La sélection est décidée une fois par
[`humanized_actions(policy)`](../src/aetherius/acts/continuum/human_actions.py).

## Composants

- **[`policy.py`](../src/aetherius/stealth/policy.py)** — `StealthPolicy` + `build_policy` + presets
  (`off`, `human`). L'unique point de décodage de `options.stealth`.
- **[`humanizer/`](../src/aetherius/stealth/humanizer/)** — entrées humanisées, calcul pur séparé de
  l'application au navigateur (donc unit-testable sans Chromium) :
  - `timing.py` : `precise_sleep` (busy-wait sub-20 ms) et `human_pause` (délai aléatoire,
    distraction occasionnelle) ;
  - `scroll.py` : `ease_out_deltas` (courbe cubic ease-out, pure) et `human_scroll` ;
  - `keyboard.py` : `plan_typing` (frappe, typo+correction, délais espaces/spéciaux, pure) et
    `human_type` ;
  - `mouse.py` : `plan_replay` (transform scale+rotation d'un geste, pure) et `HumanMouse` (rejeu
    point par point, clic off-center, micro-pauses, `park` du curseur vers le bas pendant les
    attentes) ;
  - `input.py` : façade `HumanInput` (click/hover/fill/type/scroll), l'unique objet manipulé par
    l'Act. Chaque méthode dégrade par feature (souris off → clic Playwright brut, etc.).
- **[`gestures/`](../src/aetherius/stealth/gestures/)** — `library.py` (`GestureLibrary` :
  chargement, downsampling, analyse distance/angle, `best_match`) **source-agnostique**, et
  `seed.py` (générateur déterministe du seed).
- **[`fingerprint/`](../src/aetherius/stealth/fingerprint/)** — `patch.py` (masques d'automation) et
  `profile.py` (profils cohérents ; `chrome-desktop` fourni).
- **[`session/`](../src/aetherius/stealth/session/)** — `store.py` (profils persistants, déjà en
  place) et `warmup.py` (`plan_warmup`/`warmup_profile` : historique authentique avant automation).
- **[`ml/`](../src/aetherius/stealth/ml/)** *(optionnel, roadmap)* — modèle de mouvement génératif et
  modèle de fingerprints, derrière les mêmes interfaces.

## La bibliothèque de gestes est source-agnostique

`GestureLibrary` ne lit qu'un format neutre (`{ "meta": {...}, "gestures": [[x, y, t], ...] }`) : un
geste est une liste d'offsets `[dx, dy, t]` depuis son origine. **D'où viennent les traces ne la
concerne pas.** Trois sources coexistent derrière la même interface, distinguées par `meta.source` :

- **seed synthétique** (fourni, `meta.source: "synthetic-seed"`) : traces générées par un modèle
  minimum-jerk + overshoot + tremor ([`seed.py`](../src/aetherius/stealth/gestures/seed.py)), pour
  que `mouse: gestures` fonctionne dès l'installation et soit testable en conditions réelles ;
- **traces humaines réelles** : capturées par le [gesture recorder](recorder.md#gesture-recorder)
  (`aetherius record-gestures`), qui écrit le même format dans
  `stealth/gestures/data/human_library.json` ;
- **traces générées par IA** : upgrade ML de la roadmap.

Régénérer le seed : `python -m aetherius.stealth.gestures.seed`.

## Décision IA

Le rejeu géométrique de gestes est le moteur **par défaut** (léger, éprouvé, sans dépendance ML). Le
ML (`stealth/ml/`) est un upgrade optionnel, pas un prérequis. Le cœur stealth est **stdlib pur**
(`math`, pas de numpy) : toute sa logique est couverte par la CI de base, sans extra.

## Limites connues

- **Seed de gestes synthétique par défaut.** La bibliothèque livrée est le seed généré ; `mouse:
  gestures` rejoue donc des gestes réalistes mais synthétiques tant que le
  [gesture recorder](recorder.md#gesture-recorder) (`aetherius record-gestures`) n'a pas ajouté de
  traces humaines réelles. L'interface est identique ; les traces réelles se substituent au seed sans
  changement de code côté humanizer.
- **Profils de fingerprint statiques.** `chrome-desktop` est un preset figé, pas un échantillon d'une
  distribution matérielle réelle ; la version d'UA peut diverger du build Chromium sous-jacent (client
  hints). Le modèle ML de fingerprints est l'upgrade prévu, derrière la même interface.
- **Clic par coordonnées.** Le clic humanisé vise des coordonnées (après avoir amené la cible dans le
  viewport), non le retry auto-piloté de `locator.click()`. C'est le prix de la discrétion ; les
  cibles très mouvantes restent plus fiables sans `mouse: gestures`.
- **Warmup minimal.** `warmup_profile` visite une liste d'URLs avec dwell ; il ne simule pas encore
  d'interactions pendant les visites.

## Tester la discrétion

Exemple réel, exécutable tel quel (fenêtre visible car `debug: true` — on **voit** la souris humaine
glisser vers le titre, dériver vers le bas pendant l'attente, puis cliquer la pagination). En debug,
le `slow_mo` de Playwright est automatiquement neutralisé quand les entrées sont humanisées : le
humanizer fournit déjà son propre timing, et empiler `slow_mo` par-dessus hacherait chaque geste :

```bash
aetherius run examples/continuum/quotes-stealth.blueprint.json
```

… ou depuis la Console (`aetherius` → Library → Run). Suites automatisées :

```bash
make test               # cœur stealth : unit tests, sans navigateur (CI de base)
make test-browser       # intégration : run Chromium reel, fingerprint + entrées humanisées
```

Le cœur (`tests/unit/stealth/`) tourne **sans** navigateur (fake page). L'intégration
([`tests/integration/test_stealth_run.py`](../tests/integration/test_stealth_run.py), marker
`browser`) exécute un vrai Chromium et vérifie que `navigator.webdriver` est masqué, que le profil de
fingerprint est appliqué (`navigator.platform`), et que le flux `fill`/`click` humanisé aboutit.
