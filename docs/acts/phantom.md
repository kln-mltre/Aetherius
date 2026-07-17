# Act IV — Phantom (agent autonome)

**Statut : à venir (Phase 2, [Jalon 2-C](../phase-2/2-c-phantom.md)).** Le plus lourd. Un agent
décisionnel orienté **objectif** : plutôt qu'une séquence de `steps`, le Blueprint décrit un `goal` et
des `constraints`, et Phantom boucle **percevoir → raisonner → agir** jusqu'à l'atteindre. Pour les
objectifs non scriptés et la résilience maximale.

## Le principe

- **Objectif, pas script** : un Blueprint Phantom déclare `goal`/`constraints` au lieu de `steps` (le
  schéma l'autorise déjà). Le moteur invoque la boucle de l'agent.
- **Boucle percevoir → raisonner → agir** : percevoir la page (capture + DOM + arbre d'accessibilité,
  substrat 2-A) → un **planner** (Claude par défaut) choisit la prochaine action → l'action est jouée
  via le ciblage vision d'Oracle (2-B) et la couche de discrétion → la mémoire enregistre → on
  recommence, borné par un **budget de pas** et les `constraints`.
- **Réutilisation** : perception, ciblage vision, action `read` et stealth viennent du substrat et
  d'Oracle. Phantom n'ajoute que la *boucle de décision* et la *mémoire*.

## Planner

Par défaut **Claude** (`claude-fable-5` / `claude-opus-4-8`), via l'extra `[cognition]`
(`anthropic`) et l'interface `Planner` du substrat de cognition — **remplaçable par un VLM local**
derrière la même interface, comme le grounder d'Oracle. Aucun appel modèle au niveau module :
`anthropic` est importé paresseusement.

## Modules

[`src/aetherius/acts/phantom/`](../../src/aetherius/acts/phantom/) — `driver.py` (seam `run_goal`),
`loop.py` (la boucle bornée), `planner.py` (adapte `CognitionProvider.plan`), `memory.py`
(`AgentMemory`), `perception.py` (fusion). Substrat partagé :
[`acts/_cognition/`](../../src/aetherius/acts/_cognition/).

## Installation (cible)

```bash
pip install "aetherius[cognition]"   # planner par défaut (Claude)
```

## Garde-fous (limites de conception)

- **Budget de pas** (`max_steps`) : un agent qui boucle sans fin est un bug, pas un mode.
- **Respect des `constraints`** et arrêt net sur objectif atteint.
- **Coût assumé** : plusieurs appels modèle par run (un par pas) — d'où l'intérêt de garder Oracle
  (un appel par cible) pour les flux connus.
- **Non-déterminisme** : deux runs peuvent différer ; à réserver aux objectifs réellement non
  scriptés.

## Exemple

Un objectif **zéro config** sur une page publique est livré avec le
[Jalon 2-C](../phase-2/2-c-phantom.md) (ex. « trouve la première citation de l'auteur X sur
`quotes.toscrape.com` »).

## Recorder *(à venir)*

Plutôt qu'un script, une **démonstration → `goal`** (on montre l'objectif, pas chaque step), branchée
comme un backend recorder (cf. [docs/recorder.md](../recorder.md#recorder--les-acts)).
