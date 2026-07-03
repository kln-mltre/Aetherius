# Act I — Vector (HTTP/API)

Le plus léger. Client HTTP robuste (`httpx` + `tenacity`) : requêtes GET/POST, encodage form/JSON,
en-têtes, retries/backoff, pagination, auth (cookie, bearer, basic, form-login type CAS), extraction
déclarative JSON (JSONPath) et HTML (CSS/XPath).

Cas fondateur : les services `axios` de UKit (`PlanningApiService.ts`). Les constantes magiques
(`resType`, `colourScheme`) deviennent des `inputs`/`vars` explicites.

Modules : [`src/aetherius/acts/vector/`](../../src/aetherius/acts/vector/) —
`driver.py`, `client.py`, `auth.py`.

Exemple : [`examples/ukit-planning-week.blueprint.json`](../../examples/ukit-planning-week.blueprint.json).
