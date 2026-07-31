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

> **Etat : squelette.** Seules les interfaces sont posees ; rien ne s'execute encore. Le cadrage,
> les decisions d'architecture et les sept jalons sont dans
> [`docs/phase-3/`](../../docs/phase-3/README.md).
