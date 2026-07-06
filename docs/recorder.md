# Recorder & création de Blueprints

**Statut : implémenté et opérationnel** (blueprint recorder + gesture recorder). Extra `[browser]`
requis (Playwright) ; sans lui, une `DependencyError` claire donne la commande d'installation, jamais
un `ImportError` brut. Le cœur du recorder — synthèse de sélecteurs, transformation événements→steps,
segmentation de gestes — est **pur** et couvert par la CI de base (sans navigateur).

Trois voies de création (voir aussi le [README](../README.md)) :

1. **Blueprint Studio** — création guidée dans la Console (`console/screens/builder/`), sans JSON.
   S'appuie sur le module headless [`builder/`](../src/aetherius/builder/). *(jalon suivant)*
2. **Blueprint recorder** — par démonstration : navigateur visible, capture des actions, synthèse de
   sélecteurs robustes, puis émission d'un Blueprint `continuum` minimal et propre. Décrit ci-dessous.
3. **JSON à la main** — contrôle total, validé contre le schéma.

## Blueprint recorder

Modules : [`recorder/`](../src/aetherius/recorder/) —
`selector_synth.py` (politique de sélecteurs, pure), `_capture_js.py` (script injecté),
`capture.py` (cycle de vie du navigateur, `RecordingSession`), `blueprint_recorder.py`
(orchestration + transformation pure), `_playwright.py` (import paresseux + boucle de pump partagée).

### Fonctionnement

Le recorder ouvre un Chromium **visible**, où l'utilisateur réalise la tâche. Un script injecté
(`add_init_script`, réinstallé à chaque navigation et sur toute nouvelle page) écoute les vrais
événements DOM d'une démonstration — `click`, `change`, `Enter` — et remonte, pour chacun, un
descripteur JSON au binding `__aetherius_capture` exposé côté Python. Les navigations de haut niveau
sont captées via l'événement `framenavigated` de Playwright.

La **séparation des responsabilités** est la même que dans la couche de discrétion (calcul pur vs
application au navigateur) :

- **In-page (JS)** : le seul endroit qui peut appeler `CSS.escape` et **mesurer l'unicité** d'un
  sélecteur contre le DOM vivant (`querySelectorAll(sel).length === 1`). Il ne remonte que des
  *faits* : les sélecteurs candidats et, pour chacun, s'il est unique.
- **En Python (pur, testable sans navigateur)** :
  - [`selector_synth.py`](../src/aetherius/recorder/selector_synth.py) applique la **politique de
    priorité** : `data-testid`/`-test`/`-cy`/`-qa` → `id` → `name` → `aria-label` → `role` → texte
    visible (pour les cliquables, `selector_type: "text"`) → chemin CSS positionnel (repli). Le
    premier candidat **unique** dans cet ordre gagne. Un sélecteur ancré sur l'intention survit bien
    mieux à une évolution du site qu'un `div > div:nth-child(3)` fragile.
  - [`blueprint_recorder.py`](../src/aetherius/recorder/blueprint_recorder.py) transforme les
    événements en steps `navigate`/`click`/`fill`/`select`/`press`, puis assemble un Blueprint
    minimal ordonné.

### Credentials → secrets

Un login demandé au recorder ne doit **jamais** écrire d'identifiant en clair dans le fichier. Deux
règles :

- un champ **`type=password`** devient un `{{ secrets.<nom> }}` ; sa valeur n'est **jamais capturée**
  (le script injecté ne l'envoie pas, il n'émet qu'un marqueur `redacted`) ;
- avec l'heuristique credentials (activée par défaut), un champ **username/login/email** (détecté par
  `name`/`autocomplete`) devient aussi un secret. `--no-secrets` (CLI) ou la bascule de la Console
  garde ces champs littéraux — le password, lui, reste toujours un secret.

Le nom du secret est dérivé du `name` du champ (`password`, `username`, …), unique et stable.

### Autres décisions de conception

- **Coalescence des `fill`.** Plusieurs éditions successives du même champ sont fusionnées en un seul
  `fill` avec la valeur finale (on écoute `change`, pas chaque frappe).
- **Dédup de navigation.** Une navigation qui suit immédiatement un `click`/`press` a été provoquée
  par lui : elle est **omise** (le clic l'implique déjà). Seule la navigation initiale, et une
  navigation manuelle (barre d'adresse) non précédée d'une interaction, sont conservées.
- **Validation canonique.** Chaque fichier produit est **relu** par `load_blueprint` +
  `validate_for_act` avant d'être rendu : le recorder ne peut retourner qu'un Blueprint schéma-valide
  et exécutable, ou échouer bruyamment.
- **Sauvegarde.** Le Blueprint est écrit dans `./blueprints/<nom>.blueprint.json` (le dossier que la
  Library découvre, voir [`library_scan.py`](../src/aetherius/console/screens/library_scan.py)), donc
  il apparaît immédiatement dans la Console.

### Usage

Console (`aetherius` → Recorder) : renseigner un nom et une URL de départ, cliquer **Start** ; le
navigateur s'ouvre, la démonstration se fait, et fermer la fenêtre (ou **Stop**) sauvegarde. Les
actions capturées défilent en direct dans le journal d'événements (même pattern `Sink → EventLog`
que les runs, voir [docs/console.md](console.md)) et le Blueprint produit s'affiche à la fin.

CLI :

```bash
aetherius record quotes.login --url https://quotes.toscrape.com/login
# demontrez la tache, fermez la fenetre -> blueprints/quotes.login.blueprint.json
```

Exemple committé, **vraie sortie du recorder** pour ce login (rejouable) :
[`examples/continuum/quotes-recorded-login`](../examples/continuum/quotes-recorded-login.blueprint.json).

### Limites connues

- **Navigateur visible = pas de headless.** Le recorder ouvre une fenêtre : il ne tourne pas dans un
  job CI headless (les tests d'intégration injectent donc les mêmes scripts dans un Chromium headless
  et pilotent la démonstration via Playwright).
- **Dédup de navigation heuristique.** La règle « navigation après un clic = implicite » couvre le cas
  courant (login → tableau de bord) ; un multi-page complexe peut demander un ajustement manuel du
  Blueprint après coup.
- **Boutons sans hook stable.** Un `<input type=submit>` sans `id`/`name`/`data-testid`/texte tombe
  sur un chemin CSS positionnel (unique mais plus fragile) — c'est ce que la page offre. L'exemple
  ci-dessus l'illustre honnêtement.
- **Pas de flux conditionnel.** Le recorder produit une séquence linéaire ; `if`/`for_each` restent à
  éditer à la main (comme pour Continuum en général).

## Gesture recorder

[`recorder/gesture_recorder.py`](../src/aetherius/recorder/gesture_recorder.py) capture des traces de
souris humaines réelles pour enrichir la bibliothèque de gestes de la discrétion.

Un script injecté (`_gesture_js.py`) streame des échantillons `[x, y, t]` (bufferisés puis flushés
par timer et à chaque clic, pour ne pas marteler le binding). La fonction **pure** `segment_gestures`
découpe ces échantillons en gestes *visés* — le mouvement menant jusqu'à un clic, aussi coupé sur les
pauses longues — et rebase chacun en **offsets relatifs** `[dx, dy, t]` depuis son origine, le format
exact de [`stealth/gestures/library.py`](../src/aetherius/stealth/gestures/library.py). Les gestes
dégénérés (trop courts) sont écartés. `merge_into_library` fusionne les traces dans le fichier cible
**sans détruire** l'existant et marque `meta.source: "recorded-human"`.

Cette bibliothèque est **source-agnostique** ([docs/stealth.md](stealth.md)) : le seed synthétique
(`meta.source: "synthetic-seed"`), les traces réelles du gesture recorder et de futures traces IA
coexistent derrière la même interface. Le humanizer ne change pas d'une ligne.

CLI :

```bash
aetherius record-gestures        # bougez/cliquez naturellement, fermez la fenetre pour sauver
aetherius record-gestures --out chemin/vers/lib.json   # cible un fichier separe (non destructif)
```

## Tester

Cœur pur (CI de base, sans navigateur) :

```bash
make test    # tests/unit/recorder/ : synthese de selecteurs, transformation, segmentation
```

Intégration (vrai Chromium, marker `browser`) :

```bash
pip install -e ".[browser,dev]" && playwright install chromium
make test-browser    # tests/integration/test_recorder_run.py : capture reelle + Blueprint valide
```

À la main, le flux complet (fenêtre visible) :

```bash
aetherius record quotes.login --url https://quotes.toscrape.com/login
aetherius run blueprints/quotes.login.blueprint.json --secret username=x --secret password=y
```
