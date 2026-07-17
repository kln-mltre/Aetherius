# Act III — Oracle (ciblage vision + discrétion)

**Statut : à venir (Phase 2, [Jalon 2-B](../phase-2/2-b-oracle.md)).** Quand les sélecteurs sont
fragiles, absents ou piégés, Oracle **regarde l'écran** : un modèle vision-langage (VLM) localise la
cible décrite en **langage naturel** sur une capture, et Aetherius **clique par coordonnées à travers
la couche de discrétion**. Le flux reste **scripté et déterministe** (un appel de grounding par step
ciblé) — c'est ce qui le distingue de Phantom (agent complet).

> **Redéfinition Phase 2.** Le plan d'origine reposait sur un **petit modèle ONNX entraîné par
> tâche**. Ce n'est plus le chemin par défaut : le grounding se fait par **VLM** (Claude par défaut),
> sans entraînement. Un **grounder local** (ONNX/VLM) reste branchable derrière la même interface,
> comme upgrade **optionnel** (voir [`training/`](../../training/README.md)). Décision et cadrage :
> [docs/phase-2/README.md](../phase-2/README.md).

Cas fondateur : l'upload TikTok, dont les steps désignent leurs cibles en langage naturel
(`target: {vision: "upload dropzone"}`).

## Le principe

- **Cibles par description** : un step (`click`, `type`, `upload`, `hover`, `wait_for`) porte
  `target: {vision: "le bouton Publier"}` au lieu d'un `selector`. Le `Grounder` du substrat de
  cognition rend une `Box` ; Aetherius clique son centre via `HumanInput.click_at` (bande off-center,
  timing humain).
- **Extraction sémantique** : l'action `read` lit des données décrites en langage naturel
  (`{action:"read", vision:"la liste des prix", schema:{...}}`) — la brique « donner une info
  directement humaine ». Utilisable seule, ou comme **dernier step** d'un run Continuum via la
  composition multi-Act ([Jalon 2-D](../phase-2/2-d-composition.md)).
- **Un seul navigateur, une seule discrétion** : Oracle **réutilise** la `BrowserSession` et la couche
  stealth de Continuum — il n'ouvre pas son propre navigateur.

## Modules

[`src/aetherius/acts/oracle/`](../../src/aetherius/acts/oracle/) — `driver.py` (dispatch, compose la
`BrowserSession` de Continuum), `locator.py` (`Target` vision → `Box`), `perception.py`/`model.py`
(seams réutilisant le substrat). Le substrat partagé vit dans
[`src/aetherius/acts/_cognition/`](../../src/aetherius/acts/_cognition/) et
[`_perception.py`](../../src/aetherius/acts/_perception.py).

## Installation (cible)

```bash
pip install "aetherius[cognition]"   # grounding par défaut (Claude)
# ou, pour le grounder local optionnel :
pip install "aetherius[vision]"      # onnxruntime / opencv
```

## Exemple

[`examples/oracle/tiktok-upload.blueprint.json`](../../examples/oracle/tiktok-upload.blueprint.json)
— **gabarit non exécutable** (compte/secrets), sert de référence de format. Un exemple **zéro config**
sur une page publique est livré avec le [Jalon 2-B](../phase-2/2-b-oracle.md).

## Recorder *(à venir)*

Plutôt que l'annotation de screenshots, la voie moderne est la **désignation en langage naturel** :
décrire la cible, laisser le VLM la localiser — branchée comme un backend recorder (cf.
[docs/recorder.md](../recorder.md#recorder--les-acts)).
