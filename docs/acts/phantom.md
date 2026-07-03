# Act IV — Phantom (agent autonome)

Le plus lourd. Agent décisionnel orienté objectif : boucle percevoir (vision + DOM + arbre
d'accessibilité) → raisonner (planner VLM/LLM) → agir (via la couche de discrétion). Discrétion par
défaut, résilience anti-bot maximale. Pour les objectifs non scriptés (`goal`/`constraints` plutôt
que `steps`).

Planner par défaut : Claude (`claude-fable-5` / `claude-opus-4-8`), remplaçable par un VLM local.

Modules : [`src/aetherius/acts/phantom/`](../../src/aetherius/acts/phantom/) —
`driver.py`, `loop.py`, `planner.py`, `perception.py`, `memory.py`.

Usage : automatisation autorisée de ses propres comptes/données.
