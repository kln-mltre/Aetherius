# @aetherius/react-native

L'**Act II (Continuum) sur appareil** et la surface que consomme une application React Native.

Ce paquet apporte ce que [`@aetherius/engine`](../engine) ne peut pas porter sans dependre d'une
plateforme : le driver Continuum adosse a une **WebView cachee** pilotee par un agent JavaScript
injecte, la resolution des secrets par le trousseau de l'OS, et la facade `Aetherius` que
l'application appelle.

C'est la reponse a un cas concret : une application mobile qui se connecte au portail d'une
universite et en extrait des donnees. Aujourd'hui cela s'ecrit en JavaScript injecte sous forme de
gabarits de chaine — non type, non verifiable, et fragile des que le site bouge. Avec Aetherius, le
comportement redevient un **Blueprint**, les requetes partent du telephone de l'utilisateur, et les
identifiants ne quittent jamais l'appareil.

> **Etat : squelette.** Seules les interfaces sont posees ; rien ne s'execute encore. Le cadrage,
> les decisions d'architecture et les sept jalons sont dans
> [`docs/phase-3/`](../../docs/phase-3/README.md).
