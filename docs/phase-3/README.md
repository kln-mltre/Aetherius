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
                                                                                            ├──► 3-G References
                                                                                            │
                                                                                            └──► 3-H Noms reserves

   3-B Expressions & extraction ──────────────────────────────────────────────► 3-I Extraction texte
```

| Jalon | Spécification | Dépend de | Résumé |
|-------|---------------|-----------|--------|
| 3-A | [3-a-socle-ts.md](3-a-socle-ts.md) | — | Socle du moteur TypeScript : modèle de Blueprint, validation en deux temps (schéma précompilé puis sémantique), erreurs typées, bus d'événements, `Result`, interface `ActDriver`. Nouveau contrat généré `contracts/actions.json` et **harnais de conformance**. Fondation : aucune capacité utilisateur seule. |
| 3-B | [3-b-expressions.md](3-b-expressions.md) | 3-A | Les deux mini-langages, sans `eval` : rendu d'expressions (sous-ensemble Jinja2, règle de l'expression nue, `StrictUndefined`, filtres de date), `isTruthy`, prédicat `where`, JSONPath, et l'extraction JSON/HTML. |
| 3-C | [3-c-vector.md](3-c-vector.md) | 3-B | Runtime asynchrone (moteur de run, exécuteur de steps, garde `when`, actions de flux) et **Act I — Vector** sur `fetch`. Premier Blueprint qui tourne réellement sur un téléphone. |
| 3-D | [3-d-continuum.md](3-d-continuum.md) | 3-C | **Act II — Continuum** sur WebView : agent injecté, RPC corrélée, locators, auto-attente, extraction DOM, `wait_for` avec `fail:CODE`, sessions et cookies, mode debug. Le jalon le plus volumineux. **Livré.** |
| 3-E | [3-e-integration.md](3-e-integration.md) | 3-D | La surface applicative : façade `Aetherius`, `SecretResolver` sur le trousseau, hygiène des secrets, flux d'événements pour l'UI, action `confirm` en modal natif, annulation, et un modèle d'erreur qui distingue enfin « source en panne » de « réponse vide ». **Livré.** |
| 3-F | [3-f-delivery.md](3-f-delivery.md) | 3-E | **Livraison des Blueprints** : socle embarqué dans le binaire, surcouche distante avec cache, contrôle d'intégrité, repli et interrupteur d'arrêt. Corriger un site cassé sans publier sur les stores — le vrai gain produit. **Livré.** |
| 3-G | [3-g-reference.md](3-g-reference.md) | 3-F | Blueprints de référence exécutables sous `examples/mobile/reference/` (quatre API réelles et un parcours SSO complet) et **guide de migration** : comment un service HTTP et une WebView cachée deviennent des Blueprints. **Livré.** |
| 3-H | [3-h-portails.md](3-h-portails.md) | 3-F | Étendre la surcouche : un préfixe de noms **réservé** sous lequel un manifeste a le droit d'*ajouter* un Blueprint absent du binaire, en opt-in et borné par un périmètre de secrets obligatoire. Le besoin vient du consommateur — ajouter le portail d'une nouvelle faculté sans publier sur les stores. Le format de manifeste ne change pas. **Livré.** |
| 3-I | [3-i-extraction-texte.md](3-i-extraction-texte.md) | 3-B | Une extraction `from: "text"` : le corps décodé d'une réponse, dans les deux moteurs. Une réponse qui n'est ni JSON ni HTML — iCalendar, CSV, `text/plain` — était hors de portée d'un Blueprint. Le besoin vient encore du consommateur : atteindre les emplois du temps universitaires par leur export iCal, seule voie qui ne demande pas un port par produit de planning. Le décodage suit l'en-tête de réponse, avec une **table d'encodages bornée et partagée** par les deux moteurs plutôt que déléguée à leurs plateformes. **Livré.** |

Les jalons **3-H** et **3-I** sont des appendices : la phase était terminée sans eux, et chacun s'est
ouvert parce qu'un port réel a rencontré une limite — la garde de 3-F pour le premier, les deux seules
formes d'extraction de 3-B pour le second. C'était le bon moment pour les traiter : après avoir vu la
règle d'origine tenir, pas avant.

> **Ce que 3-I a appris, et qui vaut au-delà de lui.** Une capacité qui a l'air d'être « rendre le
> corps » cachait la seule question qui compte pour deux moteurs : **qui décide de l'encodage**. La
> réponse paresseuse — chacun délègue à sa plateforme — aurait passé la CI (Node a ICU) et divergé
> sur l'appareil (React Native n'a pas `TextDecoder`). Écrire la table dans le contrat, et non dans
> les plateformes, est la même décision que le point 4 des décisions d'architecture, prise pour la
> même raison.

C'est le résultat attendu d'un consommateur réel, et non un signe que la phase avait été mal cadrée :
le jalon 3-G en avait déjà trouvé huit en portant six sources. Un moteur qui n'a jamais servi à
quelqu'un d'autre n'a pas de manques — il a des manques qu'on n'a pas encore vus.

> **Correctif 0.5.3, sans jalon.** Le même port a ensuite trouvé, sur iPhone, qu'une source
> injoignable n'atteignait **jamais** la famille `unavailable` : le signal d'échec de chargement de
> la WebView était bien câblé et jamais lu. Ce n'est pas une capacité qui manquait, c'est une
> promesse du jalon 3-E qui ne tenait pas — donc un correctif, pas un jalon de plus. Il corrige
> l'angle mort **des deux côtés** (le `navigate` du moteur Python levait une erreur Playwright brute)
> et ajoute un cas de conformance qui fige que les deux échouent au step `navigate`. Récit complet :
> [docs/embedded.md](../embedded.md#une-source-injoignable-atteint-unavailable-corrigé-en-053).

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
> jalon concerné** — sinon les tests anti-dérive et de contrats cassent. Les **neuf jalons sont
> livrés** (3-A à 3-G, plus les appendices 3-H et 3-I) : `contracts/actions.json` existe (généré depuis le registre Python et gardé), les deux
> mini-langages sont là, les Blueprints `vector` **et** `continuum` **s'exécutent** sur l'appareil,
> une application les consomme par une **façade** (secrets, `confirm`, annulation, modèle d'erreur),
> et ils ne sont plus figés dans le binaire — un **registre** les résout entre un socle embarqué et
> une surcouche distante vérifiée. Le jalon 3-F définit d'ailleurs le seul **nouveau** contrat de la
> phase, et il est *applicatif* (le format du manifeste). Le jalon 3-G **porte un cas d'usage
> mobile réel** en Blueprints et livre le guide de migration. Le jalon 3-H laisse ce même
> manifeste **ajouter** un Blueprint sous un préfixe réservé, sans changer son format d'un octet.
> Le jalon 3-I, enfin, ajoute au vocabulaire d'extraction sa **troisième et dernière** forme,
> `from: "text"` — une valeur d'énumération, aucune action ni clé de schéma.
> Le corpus de conformance vit sous [`conformance/`](../../conformance/README.md) et
> `make conformance` rejoue les deux moteurs — depuis 3-C sur des **runs entiers**, pas seulement des
> verdicts, et depuis 3-D sur des runs **navigateur** (un cas déclare alors `requires: "browser"`,
> et un troisième exécuteur, celui de `@aetherius/react-native`, les joue). Référence d'usage :
> [docs/embedded.md](../embedded.md).
>
> **Une seule évolution de contrat sur toute la phase** : un fichier **ajouté** au jalon 3-A
> (`contracts/actions.json`), et une **clé ajoutée** au jalon 3-G — `options.stealth.user_agent`,
> qui était documentée et implémentée côté embarqué mais absente du schéma, donc refusée par les
> deux moteurs. Un port réel l'a trouvée en une requête. Le jalon 3-I n'y ajoute rien :
> `blueprint.schema.json` laisse déjà le bloc `extract` ouvert, et seule l'aide de son paramètre —
> une ligne du contrat **généré** — nomme désormais les trois formes.
