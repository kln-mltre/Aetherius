# Legacy examples — matière première d'Aetherius

Ces fichiers proviennent de deux projets réels de Kylian. Ils sont conservés **tels quels**, à titre
d'exemple et de contexte : ils ont fondé chaque décision d'architecture d'Aetherius.

> Ne jamais modifier ces fichiers. Ils sont de la référence en lecture seule, exclue du packaging.
> Cette carte de provenance est le seul ajout ; elle relie chaque fichier au composant Aetherius
> qu'il a inspiré, pour reprendre le contexte rapidement dans une future session.

## `ukit_project_examples/` — UKit (TypeScript / React Native)

Application mobile. Deux patterns d'accès au web qui fondent **Act I** et **Act II**.

| Fichier | Ce qu'il fait | Fonde |
|---------|---------------|-------|
| `PlanningApiService.ts` | Récupère l'emploi du temps via `axios` : GET liste de groupes, POST form-encodé (`qs.stringify`, `arrayFormat: repeat`) pour les événements, parsing/tri/filtrage manuels. | **Act I — Vector** : `acts/vector/` (client httpx, form-encoding, extraction déclarative). Voir `examples/ukit-planning-week.blueprint.json`. |
| `WebBrowserScreen.tsx` | WebView `react-native-webview` avec `injectedJavaScript` (login CAS auto) et pont `postMessage` ↔ `onMessage`. | **Act II — Continuum** : `acts/continuum/` (browser scripté, bridge JS injecté), et le **mode debug** (WebView visible). |
| `CredentialsContext.tsx` | Orchestration du scraping caché : modes cold/hot, stockage sécurisé, machine à événements (`LOGIN_SUCCESS`, `PROGRESS`, `ENT_DATA`, `DOSSIER_DATA`, `MAILBOX_DATA`, `DEBUG`). | **Act II** + le **bus d'événements** (`core/events/`) et la **gestion de session** (`stealth/session/`). Voir `examples/ukit-scolarite-login.blueprint.json`. |

Fragilités observées (que l'archi corrige) : constantes magiques répétées (`resType:'103'`,
`colourScheme:'3'`) → `inputs`/`vars` ; parsing regex et filtres par chaîne (`=== 'Vacances'`) →
extraction déclarative ; erreurs avalées (`catch { return null }`) → erreurs typées
(`core/errors.py`) ; sélecteurs codés en dur dans le JS injecté → sélecteurs = données du Blueprint,
+ **synthèse de sélecteurs robustes** du recorder.

## `tiktok_project_examples/` — automate TikTok (Python / Playwright)

Publication automatique de vidéos avec forte discrétion. Fonde le **système de discrétion** et
**Act III/IV**.

| Fichier | Ce qu'il fait | Fonde |
|---------|---------------|-------|
| `tiktok_driver.py` | Système *BioMouse* : bibliothèque de gestes humains `(x,y,t)`, downsampling euclidien, matching distance/angle (pondéré ×100), rejeu par transformation scale+rotation, `precise_sleep` busy-wait sub-20ms, frappe humaine (fautes 5 %, délais espaces/spéciaux), scroll ease-out cubique, masquage `navigator.webdriver`/`chrome.runtime`/`plugins`, clic off-center 30-70 %, parking souris, `add_mouse_helper_script` (overlay curseur). | **Discrétion modulaire** : `stealth/humanizer/{mouse,keyboard,scroll,timing}`, `stealth/gestures/`, `stealth/fingerprint/patch`. Overlay curseur → **mode debug**. Le flux d'upload guidé → **Act III — Oracle**. Voir `examples/tiktok-upload.blueprint.json`. |
| `setup_login.py` | Contexte Chrome persistant (`launch_persistent_context`, `user_data_dir`), login manuel initial, warmup d'historique, `ignore_default_args=["--enable-automation"]`. | **`stealth/session/{store,warmup}`** (profils persistants + warmup) et `stealth/fingerprint/`. |

Note : `data/human_library.json` (la bibliothèque de gestes réelle) n'était pas fournie dans les
exemples ; sa forme est reprise dans `src/aetherius/stealth/gestures/data/human_library.json`
(placeholder), à alimenter via le gesture recorder.
