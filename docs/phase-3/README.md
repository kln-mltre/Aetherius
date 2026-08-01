# Phase 3 — Embarqué : le moteur sur l'appareil

Après la **Phase 1** (socle réutilisable, Acts I–II), la **Phase 1.5** (socle opérationnel :
planification, alertes, réactivité, furtivité) et la **Phase 2** (Acts cognitifs, composition,
human-in-the-loop) — toutes livrées — la Phase 3 change d'axe. Elle n'ajoute **aucune capacité** au
vocabulaire des Blueprints : elle livre un **second moteur**, écrit en TypeScript, qui rejoue les
**mêmes Blueprints** directement sur l'appareil de l'utilisateur. Référence d'usage du socle livré :
[docs/embedded.md](../embedded.md).

Périmètre volontairement resserré : **Acts I (Vector) et II (Continuum) uniquement**. Oracle et
Phantom restent l'apanage du moteur Python.

## Pourquoi

Aetherius s'expose aujourd'hui à TypeScript par un daemon local et le SDK
[`@aetherius/client`](../../sdks/client). C'est la bonne réponse pour une application de bureau ou un
service. Pour une **application mobile**, c'en est une mauvaise, et pour trois raisons qui ne sont
pas des détails d'implémentation :

1. **Les requêtes partent du mauvais endroit.** Un daemon hébergé fait sortir *toutes* les requêtes
   d'une seule IP, pour tous les utilisateurs. Il faut alors des proxies et de la rotation d'IP pour
   ne pas se faire bloquer — c'est-à-dire construire une infrastructure entière pour compenser le
   fait qu'on a déplacé le travail au mauvais endroit. Depuis le téléphone, chaque utilisateur part
   de sa propre connexion : le problème n'existe pas.
2. **Les identifiants transiteraient par une machine tierce.** Une application universitaire qui
   scrape l'ENT de son utilisateur détient ses identifiants CAS. Les faire transiter par un serveur,
   fût-il le nôtre, casse la promesse « vos identifiants ne vont qu'au CAS de votre université ». Sur
   appareil, ils ne quittent jamais le trousseau de l'OS.
3. **Le serveur devient un point de panne et un coût** pour une application qui, sans lui, n'a besoin
   d'aucune infrastructure.

Ce que ces applications écrivent à la place, aujourd'hui, c'est exactement ce qu'Aetherius existe
pour supprimer : une WebView cachée pilotée par du **JavaScript injecté sous forme de gabarits de
chaîne** — non typé, invérifiable par le compilateur, avec des sélecteurs positionnels en dur au
milieu du code applicatif, et des services HTTP truffés de constantes magiques. Chaque changement du
site distant demande une **publication sur les stores**.

**La Phase 3 rend cette couche déclarative sur mobile.** Le comportement redevient de la donnée
versionnée, corrigeable sans republier l'application (jalon 3-F), et le même Blueprint tourne
indifféremment sur le moteur Python et sur le moteur embarqué.

## Décisions d'architecture

| # | Décision | Choix retenu |
|---|----------|--------------|
| 1 | Nature du moteur | **Réimplémentation TypeScript.** Embarquer Python (Chaquopy, Pyodide) est exclu en environnement mobile managé, et coûterait des dizaines de mégaoctets pour exécuter un interpréteur dans un interpréteur. Les `contracts/` restent l'unique source de vérité : **deux moteurs, un contrat**. |
| 2 | Frontière des paquets | [`@aetherius/engine`](../../sdks/engine) est **neutre plateforme** (cœur + Act I sur `fetch`) et tourne aussi sous Node — la conformance se joue donc en CI, sans simulateur. [`@aetherius/react-native`](../../sdks/react-native) porte l'Act II sur WebView et la façade applicative. [`@aetherius/client`](../../sdks/client) (le SDK daemon) reste inchangé : *piloter* un moteur distant et *être* un moteur sont deux métiers. |
| 3 | Synchrone → asynchrone | Le moteur Python est synchrone de bout en bout (`ActDriver.setup/run_step/teardown`, Playwright en API sync, `confirm` bloquant). Sur appareil, rien ne peut bloquer la boucle JS : **tout devient `Promise`**. C'est la seule divergence structurelle assumée ; la sémantique observable — ordre des steps, événements émis, forme du `Result` — reste identique. |
| 4 | Contrainte du moteur JS mobile : **ni `eval`, ni `new Function`** | Hermes ne les supporte pas. Cette contrainte n'est pas un détail : elle décide trois briques. (a) Le rendu d'expressions est un **évaluateur maison** (parseur + interpréteur d'AST), pas Nunjucks. (b) La validation JSON Schema est **précompilée au build** depuis `contracts/blueprint.schema.json` — Ajv génère du code par `new Function` en mode runtime. (c) JSONPath et le prédicat `where` passent par le **même** évaluateur. Accessoirement, c'est aussi la bonne posture de sécurité pour un moteur qui exécute de la donnée téléchargée. |
| 5 | Act II sans moteur de locators | Playwright n'existe pas dans une WebView : ni résolution de sélecteurs, ni auto-attente, ni appel synchrone dans la page. Le driver pilote un **agent JavaScript injecté** via une **RPC corrélée** (`injectJavaScript` d'un côté, `postMessage` de l'autre). Corollaire structurant : les paramètres traversent **encodés en JSON**, jamais interpolés dans la source du script — la classe de bug la plus courante des WebView écrites à la main (un mot de passe contenant une apostrophe qui casse le script) devient impossible par construction. |
| 6 | Capacités non portables | Certaines capacités de Continuum n'ont pas d'équivalent honnête en WebView (`upload`, `drag`, `screenshot`, le code de statut de `navigate`). Le moteur embarqué déclare **sa propre table de capacités** et **échoue à la validation** avec un message explicite — miroir de `PENDING_ACTIONS` côté Python. Un Blueprint non exécutable le dit avant de démarrer, jamais au milieu d'un run. |
| 7 | Anti-dérive | Deux moteurs qui divergent silencieusement seraient pires qu'un seul. Deux gardes : un contrat **généré** `contracts/actions.json` (projection du registre Python, gardé par un test), consommé par le moteur TypeScript ; et un **corpus de conformance** partagé, rejoué par les deux moteurs, enrichi à chaque jalon. |
| 8 | Hors périmètre, explicitement | Acts III/IV, stealth lourd (gestes de souris, empreinte, proxy, impersonation TLS), recorder, builder, console, daemon, scheduler, store. Une seule bribe de stealth survit — le **user-agent configurable** —, parce qu'un portail sert souvent un DOM différent aux mobiles et qu'un Blueprint doit pouvoir en décider. |

### Périmètre fonctionnel du moteur embarqué

| Capacité | Embarqué | Note |
|----------|:---:|------|
| Act I — Vector (`http.request`, `extract`) | oui | sur `fetch` |
| Act II — Continuum (navigation, interaction, extraction DOM) | oui | sur WebView, moins les capacités du point 6 |
| Flux — `when`, `if`, `repeat`, `for_each` | oui | cœur du runtime |
| Utilitaires — `set`, `assert`, `emit`, `wait` | oui | |
| `confirm` (human-in-the-loop) | oui | modal natif, biométrie possible |
| `notify` | non | l'application a déjà ses notifications |
| Acts III/IV, `read` | non | restent au moteur Python |
| Store, scheduler, proxy, stealth avancé | non | |

## Comment les deux moteurs cohabitent

```
                    contracts/  ── blueprint.schema.json · events.schema.json · actions.json
                         │              (source de verite, langage-agnostique)
          ┌──────────────┴───────────────┐
          │                              │
   Moteur Python                  Moteur embarque (Phase 3)
   src/aetherius/                 sdks/engine · sdks/react-native
   Acts I II III IV               Acts I II
   Playwright · httpx             WebView · fetch
   synchrone                      asynchrone
          │                              │
   daemon + @aetherius/client       importe directement par l'app mobile
   (pilote un moteur distant)       (est le moteur, sur l'appareil)
          │                              │
          └────────► corpus de conformance partage ◄────────┘
                     (le meme Blueprint, le meme resultat)
```

Le moteur Python garde tout ce qui demande une machine : les Acts cognitifs, la planification,
l'outillage (Console, Studio, Recorder). Le moteur embarqué prend ce qui doit partir de l'appareil.
Un Blueprint écrit dans le Studio et testé depuis la Console tourne ensuite sur le téléphone, sans
retouche : c'est tout l'intérêt d'avoir un contrat plutôt qu'une implémentation de référence.

## Les jalons et leur ordre

Chaque jalon fait l'objet d'une **spécification autonome**, au même format que les Phases 1.5 et 2.
Le squelette (workspace npm, stubs d'interface documentés) est déjà en place ; chaque spécification
décrit ce qu'il reste à implémenter, sa « Définition de terminé », son plan de test et son exemple
exécutable.

```
3-A Socle TS & parite
        │
        └──► 3-B Expressions & extraction ──► 3-C Runtime + Act I (Vector)
                                                        │
                                                        └──► 3-D Act II (Continuum / WebView)
                                                                     │
                                                                     └──► 3-E Integration applicative
                                                                                  │
                                                                                  └──► 3-F Livraison
                                                                                            │
                                                                                            └──► 3-G References
```

| Jalon | Spécification | Dépend de | Résumé |
|-------|---------------|-----------|--------|
| 3-A | [3-a-socle-ts.md](3-a-socle-ts.md) | — | Socle du moteur TypeScript : modèle de Blueprint, validation en deux temps (schéma précompilé puis sémantique), erreurs typées, bus d'événements, `Result`, interface `ActDriver`. Nouveau contrat généré `contracts/actions.json` et **harnais de conformance**. Fondation : aucune capacité utilisateur seule. |
| 3-B | [3-b-expressions.md](3-b-expressions.md) | 3-A | Les deux mini-langages, sans `eval` : rendu d'expressions (sous-ensemble Jinja2, règle de l'expression nue, `StrictUndefined`, filtres de date), `isTruthy`, prédicat `where`, JSONPath, et l'extraction JSON/HTML. |
| 3-C | [3-c-vector.md](3-c-vector.md) | 3-B | Runtime asynchrone (moteur de run, exécuteur de steps, garde `when`, actions de flux) et **Act I — Vector** sur `fetch`. Premier Blueprint qui tourne réellement sur un téléphone. |
| 3-D | [3-d-continuum.md](3-d-continuum.md) | 3-C | **Act II — Continuum** sur WebView : agent injecté, RPC corrélée, locators, auto-attente, extraction DOM, `wait_for` avec `fail:CODE`, sessions et cookies, mode debug. Le jalon le plus volumineux. |
| 3-E | [3-e-integration.md](3-e-integration.md) | 3-D | La surface applicative : façade `Aetherius`, `SecretResolver` sur le trousseau, hygiène des secrets, flux d'événements pour l'UI, action `confirm` en modal natif, et un modèle d'erreur qui distingue enfin « source en panne » de « réponse vide ». |
| 3-F | [3-f-delivery.md](3-f-delivery.md) | 3-E | **Livraison des Blueprints** : socle embarqué dans le binaire, surcouche distante avec cache, contrôle d'intégrité, repli et interrupteur d'arrêt. Corriger un site cassé sans publier sur les stores — le vrai gain produit. |
| 3-G | [3-g-reference.md](3-g-reference.md) | 3-F | Blueprints de référence exécutables sous `examples/mobile/` (API publiques et un parcours SSO complet) et **guide de migration** : comment un service HTTP et une WebView cachée deviennent des Blueprints. |

**Ordre recommandé :** strictement séquentiel, de 3-A à 3-G — chaque jalon consomme le précédent.
Deux avertissements de charge : **3-B** est le jalon à risque (c'est là que se paie la contrainte du
point 4, et la surface exacte de Jinja2 à reproduire ne se découvre qu'en écrivant le corpus), et
**3-D** est le plus volumineux (l'agent injecté réimplémente à lui seul ce que Playwright offre
gratuitement). Les découper en plusieurs sessions est attendu, pas un échec.

## Implémenter un jalon

Un jalon se traite en suivant sa **spécification** et la
[« Définition de terminé »](../../CONTRIBUTING.md#définition-de--terminé-) de `CONTRIBUTING.md`.
Deux adaptations pour un jalon TypeScript :

- **La porte est `make check-all`**, pas seulement `make check` : elle enchaîne la passe Python et le
  workspace npm. À partir de 3-A, `make conformance` s'y ajoute.
- **Le point 5 (« flux vérifié à la main ») se joue sur un appareil ou un simulateur**, pas dans un
  terminal. Une application de démonstration est introduite au jalon 3-C précisément pour cela. Les
  « sondes réalistes dures » exigées par [CONTRIBUTING](../../CONTRIBUTING.md) gardent tout leur
  sens : un portail réel, pas seulement `quotes.toscrape.com`.

> **Note de portée.** Comme en Phase 2, tout ce qui toucherait la table des `capabilities`, les
> contrats (`contracts/*.json|yaml`), l'enum `EventType` ou le dispatch d'un driver est **différé au
> jalon concerné** — sinon les tests anti-dérive et de contrats cassent. Le jalon **3-A est livré** :
> `contracts/actions.json` existe (généré depuis le registre Python et gardé), le corpus de
> conformance est en place sous [`conformance/`](../../conformance/README.md), et `make conformance`
> rejoue les deux moteurs. Référence d'usage du socle : [docs/embedded.md](../embedded.md). Aucun
> contrat existant n'a été modifié : un fichier a été **ajouté**, rien n'a bougé.
