# Act II — Continuum (navigateur scripté)

**Statut : implémenté et opérationnel.** Le moteur suit le Blueprint à la lettre contre un vrai
navigateur Playwright : navigation, remplissage, clics, attentes, extraction DOM, JS injecté. Pour
les scénarios exigeant un navigateur (login, session, contenu rendu par JS). Discrétion optionnelle
(couture prête, couche stealth branchée dans un jalon ultérieur).

Cas fondateur : la WebView cachée de UKit (`WebBrowserScreen.tsx`, `CredentialsContext.tsx`) qui
scrape la scolarité après login CAS. Les sélecteurs, autrefois codés en dur dans du JS injecté,
deviennent des données du Blueprint ; les événements (`LOGIN_SUCCESS`, `PROGRESS`, …) sont émis par
le bus.

Modules : [`src/aetherius/acts/continuum/`](../../src/aetherius/acts/continuum/) —
`driver.py` (dispatch + screenshot), `browser.py` (cycle de vie Playwright), `actions.py` (mapping
action → opération page), `bridge.py` (extraction DOM, `wait_for`, `evaluate`).

Exemple : [`examples/ukit-scolarite-login.blueprint.json`](../../examples/ukit-scolarite-login.blueprint.json).

## Installation

L'Act II est un extra ; le cœur reste léger.

```bash
pip install "aetherius[browser]"     # installe Playwright
playwright install chromium          # télécharge le navigateur
```

Un Blueprint `continuum` lancé sans l'extra échoue avec une `DependencyError` claire (message +
commande d'installation), jamais avec un `ImportError` brut.

## Architecture

Le driver est **synchrone**, comme le moteur (`RunEngine.run()`) et comme Vector : on utilise l'API
**synchrone** de Playwright (`sync_playwright`), sans event-loop à gérer. Depuis la Console, le
moteur tourne dans un worker `@work(thread=True)` (pas la boucle asyncio Textual), donc l'API sync
fonctionne. `playwright` est importé **paresseusement** dans `BrowserSession.start()` : `import
aetherius` reste léger et sans dépendance navigateur.

Les actions Act-agnostiques (`emit`, `wait`, `set`, `assert`) sont fournies par
[`acts/_shared.py`](../../src/aetherius/acts/_shared.py) (`SharedActionsMixin`), partagé avec
Vector — aucune duplication.

## Actions supportées

| Action | Description | Champs |
|--------|-------------|--------|
| `navigate` | Charge une URL. | `url`, `wait_until` (défaut `load`) |
| `back` / `forward` / `reload` | Historique de navigation. | — |
| `click` | Clique une cible. | `selector`, `selector_type` |
| `fill` | Remplit un champ (efface puis écrit). | `selector`, `value` |
| `type` | Frappe caractère par caractère. | `selector`, `text`, `delay_ms` |
| `press` | Touche clavier (cible ou global). | `key`, `selector` (optionnel) |
| `select` | Sélectionne une/des option(s). | `selector`, `value`/`values` |
| `hover` | Survole une cible. | `selector` |
| `scroll` | Scroll vers une cible, ou par delta. | `selector`, ou `dx`/`dy` |
| `upload` | Renseigne un input file. | `selector`, `file` |
| `drag` | Glisser-déposer. | `source`/`from`, `target`/`to` |
| `screenshot` | Capture (page ou élément) écrite dans le run dir + événement `artifact`. | `name`, `selector`, `full_page` |
| `evaluate` | Exécute du JS injecté ; renvoie `{ result }`. | `script`/`expression`, `arg` |
| `wait_for` | Attend un sélecteur. | `selector`, `state` (défaut `visible`), `timeout_ms`, `on_timeout` |
| `extract` | Lit le DOM vivant vers des outputs typés. | `outputs` (voir plus bas) |
| `emit`, `wait`, `set`, `assert` | Hérités du core (mixin partagé). | cf. [Act I](vector.md) |

### Cibles et sélecteurs

`selector` est **CSS** par défaut ; `selector_type` bascule en `xpath` ou `text` (via
`page.get_by_text`). Le préfixe `xpath=` est ajouté automatiquement si besoin.

### `wait_for` et l'échec nommé

`wait_for` attend qu'un sélecteur atteigne un état. En cas de dépassement, si `on_timeout` vaut
`"fail:CODE"`, le step lève une `StepTimeoutError` portant `code=CODE` (ex. `LOGIN_FAILED`) ; le
moteur émet alors un événement `error` et clôt le run en échec avec ce code.

### Extraction DOM

Le step `extract` mappe des noms vers des lectures typées du DOM :

```json
{
  "id": "dossier",
  "action": "extract",
  "outputs": {
    "firstName": { "selector": ".identity .firstname", "as": "text" },
    "unread":    { "selector": ".unread-count", "as": "number" },
    "avatar":    { "selector": "img.avatar", "as": "attr", "attr": "src" },
    "rows":      { "selector": "table tr", "as": "count" }
  }
}
```

`as` : `text` (nettoyé), `number` (premier nombre trouvé, int ou float), `html` (inner HTML),
`attr` (requiert `attr`), `count` (nombre de correspondances). Les valeurs se relisent ensuite via
`{{ steps.dossier.firstName }}` dans `outputs`.

## Sessions et debug

- `options.session.persist: true` → contexte **persistant** Playwright sur un profil résolu par
  [`stealth/session/store.py`](../../src/aetherius/stealth/session/store.py)
  (`data_dir/profiles/<profile>`), réutilisant cookies, cache et historique entre runs. Sinon
  contexte éphémère.
- `options.debug: true` → fenêtre **visible** + ralenti (slow-mo) pour suivre chaque step.
- `data_dir` est configurable via `AETHERIUS_DATA_DIR`
  ([`config/settings.py`](../../src/aetherius/config/settings.py)).

La couche de discrétion (`options.stealth`) est acceptée mais **no-op** pour l'instant : la couture
est en place (`BrowserSession(stealth=...)`), l'implémentation est un jalon distinct.

## Tester Act II

```bash
# 1. Installer l'extra navigateur + Chromium
pip install -e ".[browser,dev]" && playwright install chromium

# 2. Tests navigateur (vrai Chromium headless, page servie via data: URL, aucun hôte externe)
make test-browser
```

Les tests unitaires du mapping (`tests/unit/acts/continuum/`) tournent **sans** navigateur (page
factice via `unittest.mock`) et restent dans la CI de base ; l'intégration
(`tests/integration/test_continuum_run.py`, marker `browser`) exécute un vrai Chromium et n'est
active que lorsque l'extra `[browser]` est présent (skip propre sinon).
