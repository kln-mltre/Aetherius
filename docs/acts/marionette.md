# Act II — Marionette (navigateur scripté)

Automatisation Playwright suivant le Blueprint à la lettre : navigation, remplissage, clics,
attentes, extraction DOM, bridge JS injecté. Pour les scénarios exigeant un vrai navigateur (login,
session, contenu rendu par JS). Discrétion optionnelle.

Cas fondateur : la WebView cachée de UKit (`WebBrowserScreen.tsx`, `CredentialsContext.tsx`) qui
scrape la scolarité après login CAS. Les sélecteurs, autrefois codés en dur dans du JS injecté,
deviennent des données du Blueprint ; les événements (`LOGIN_SUCCESS`, `PROGRESS`, …) sont émis par
le bus.

Modules : [`src/aetherius/acts/marionette/`](../../src/aetherius/acts/marionette/) —
`driver.py`, `browser.py`, `actions.py`, `bridge.py`.

Exemple : [`examples/ukit-scolarite-login.blueprint.json`](../../examples/ukit-scolarite-login.blueprint.json).
