# @aetherius/engine

Le **moteur Aetherius embarque** : il execute un Blueprint la ou il tourne, sans daemon et sans
serveur. C'est le pendant TypeScript de `src/aetherius/` — meme format de Blueprint, memes contrats,
meme flux d'evenements.

A ne pas confondre avec [`@aetherius/client`](../client) : ce dernier *pilote* un moteur Python
distant par HTTP ; celui-ci *est* un moteur.

Le paquet est **neutre plateforme** — il ne connait ni React Native, ni Node. Il porte le coeur
(modele de Blueprint, runtime, extraction, evenements, erreurs typees) et l'**Act I (Vector)** sur
`fetch`. L'**Act II (Continuum)**, qui exige une WebView, vit dans
[`@aetherius/react-native`](../react-native).

> **Etat : Act I executable (jalon 3-C).** Sur le socle des jalons 3-A (charger, valider, refuser)
> et 3-B (expressions et extraction), un Blueprint `act: "vector"` **tourne** : runtime asynchrone,
> flux, garde `when`, utilitaires partages et requetes HTTP sur `fetch`. L'Act II arrive au jalon
> 3-D, la facade applicative au jalon 3-E.

```ts
import { RunEngine, parseBlueprint } from "@aetherius/engine";

const blueprint = parseBlueprint(text, "planning.blueprint.json");
const result = await new RunEngine().run(blueprint, {
  inputs: { group: "TP-A1" },
  sinks: [{ onEvent: (event) => console.log(event.type, event.step_id) }],
});

console.log(result.status, result.outputs);
```

Une seule chose est demandee a l'hote : `fetch`. Le moteur n'ajoute aucune dependance d'execution
pour l'Act I, et accepte le sien (`RunOptions.fetch`) — ce qui le rend testable sans reseau.

## Build

Le validateur de schema est **precompile** : le moteur JS mobile refuse `eval` et `new Function`,
donc la compilation est une etape de build dont la sortie est du JavaScript ordinaire. `npm run
build` regenere `src/generated/` depuis `contracts/` avant d'appeler `tsc` ; ces fichiers sont
git-ignores.

La meme contrainte decide le reste : le rendu d'expressions est un evaluateur maison (`src/expr/`),
pas Nunjucks, et les seules dependances d'execution — `htmlparser2`, `domhandler`, `domutils`,
`css-select`, pour l'extraction HTML hors navigateur — sont retenues parce qu'elles ne generent pas
de code. `test/no-dynamic-code.test.js` le verifie a chaque execution.

```bash
npm --prefix sdks install
npm --prefix sdks run build --workspace @aetherius/engine
npm --prefix sdks test  --workspace @aetherius/engine
```

Reference d'usage, table des capacites embarquees et limites connues :
[`docs/embedded.md`](../../docs/embedded.md). Cadrage et jalons :
[`docs/phase-3/`](../../docs/phase-3/README.md).
