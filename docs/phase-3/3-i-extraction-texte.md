# Jalon 3-I — Extraire un corps de réponse en texte

**Statut : livré (2026-08-13).** Second appendice de la Phase 3, ouvert le 2026-08-11 pour la même
raison que [3-H](3-h-portails.md) : le consommateur a buté sur une limite en portant une source
réelle, et le manque est du côté du contrat, pas du sien.

> **Ce qui a été livré**, au-delà de la lettre de la spécification : le décodage suit l'en-tête dans
> les deux moteurs, avec une **table d'encodages bornée et partagée** (§ [Ce qui a été tranché](#ce-qui-a-été-tranché)),
> les clés des autres dialectes sont refusées à la validation (pas seulement `path`), et la lecture
> en octets du moteur embarqué n'a lieu **que** si un `from: "text"` est déclaré. Récit d'usage :
> [docs/acts/vector.md](../acts/vector.md#from-text--les-formats-à-lignes) et
> [docs/embedded.md](../embedded.md#le-corps-en-texte-et-son-décodage).

## Le manque, et comment il s'est vu

L'extraction d'Act I ne connaît que deux formes : `from: "json"` et `from: "html"`
([`src/aetherius/core/extraction/dispatch.py`](../../src/aetherius/core/extraction/dispatch.py)). Et
le step `http.request` publie `status_code` et `headers`, **jamais le corps**
([`src/aetherius/acts/vector/driver.py`](../../src/aetherius/acts/vector/driver.py)).

Une réponse qui n'est **ni du JSON ni du HTML** est donc hors de portée d'un Blueprint. C'est le cas
de tous les formats à lignes : iCalendar (RFC 5545), CSV, vCard, les flux `text/plain`.

Le besoin vient de [UKit](../../docs-ukit/README.md), jalon `6-I` : atteindre les emplois du temps
universitaires par leur **export iCal**. Le constat qui l'a rendu urgent : à peu près aucune
université française n'expose un serveur de planning interrogeable sans authentification — un
balayage de vingt établissements n'en a trouvé qu'un — alors que presque toutes offrent un lien
d'abonnement. Le format est normalisé ; c'est la seule voie qui ne demande pas un port par produit.

Ce qui a été mesuré, pour ne pas avoir à le refaire :

```
ade.bordeaux-inp.fr/jsp/custom/modules/plannings/anonymous_cal.jsp
    ?resources=<ids>&projectId=<n>&calType=ical&firstDate=AAAA-MM-JJ&lastDate=AAAA-MM-JJ
```

anonyme, borné par les paramètres d'URL, et vivant : 93 événements sur une semaine de septembre 2025,
220 en janvier 2026, 71 en mai 2026. **Le contenu de l'année écoulée reste servi**, ce qui permet de
développer et de vérifier sans attendre une rentrée.

## Objectif

Une extraction `from: "text"` qui rend le **corps décodé de la réponse**, dans les deux moteurs, à
l'octet près.

Rien d'autre. Ni parseur, ni format supplémentaire : interpréter un iCalendar est le travail de
l'application, comme l'est déjà toute projection.

## Ce qui a été écarté, et pourquoi

**Publier le corps dans les sorties de `http.request`**, à côté de `status_code`. Ce serait plus court
à écrire et c'est la mauvaise réponse : chaque requête traînerait alors sa charge utile complète dans
les sorties du step — donc dans les journaux, dans les événements, et dans la mémoire d'un run qui n'en
a que faire. L'extraction nommée est précisément le mécanisme qui fait dire au Blueprint **ce qu'il
veut garder** ; un corps de réponse ne doit pas y échapper.

**Un `from: "regex"`.** Tentant, et c'est un piège : il ferait entrer un langage de plus dans le
contrat, avec ses différences d'implémentation entre Python et JavaScript — classes de caractères,
groupes nommés, comportement des quantificateurs. Deux moteurs, un contrat : ce qui n'est pas
identique par construction finit par diverger. Le filtrage d'un texte reste applicatif.

## Points de conception

- **Le décodage suit l'en-tête de réponse**, avec repli UTF-8. C'est le seul point où les deux moteurs
  peuvent diverger en silence : Python décode par `httpx` selon `Content-Type`, un `TextDecoder`
  JavaScript ne connaît pas toutes les étiquettes. Le corpus de conformance doit porter au moins une
  réponse **déclarée en ISO-8859-1 avec des accents** — sans quoi la première source française mal
  étiquetée le découvrira à notre place.
- **Aucun nouveau plafond de taille.** Un run télécharge déjà ce qu'il veut ; ajouter une limite ici
  déplacerait la question sans la trancher, et casserait des sources légitimes (une année d'iCal pèse
  quelques centaines de kilo-octets). Le plafond de la **livraison** — 512 Kio par Blueprint — est un
  sujet distinct et reste inchangé.
- **`path` n'a pas de sens** pour `from: "text"` : le rendre obligatoire par symétrie serait du
  cérémonial. Le refuser explicitement s'il est présent, en revanche, évite un Blueprint qui croit
  filtrer et ne filtre rien.
- **Act II n'est pas concerné.** L'extraction DOM a déjà `as: "text"` et `as: "html"` : la lacune est
  propre à Act I.

## Interfaces et fichiers

| Dépôt | Fichier | Ce qui change |
|---|---|---|
| Python | `src/aetherius/core/extraction/dispatch.py` | une troisième branche, `from: "text"` |
| Python | `src/aetherius/core/extraction/text_extractor.py` | ajouté : décodage et spécification |
| Python | `src/aetherius/acts/vector/driver.py` | rien, si le dispatch reçoit déjà la réponse — **à vérifier** : il passe `response.content`, or le décodage a besoin des en-têtes |
| TypeScript | `sdks/engine/src/extraction/` | la branche symétrique |
| Contrat | `contracts/actions.json` | régénéré (`make contracts`) : l'aide de `extract` nomme les trois formes |
| Conformance | `conformance/` | un cas par encodage, rejoué par les deux moteurs |

Le troisième point est le seul risque de conception réel : le dispatch actuel reçoit des **octets**,
et le décodage a besoin de l'étiquette d'encodage. Soit on lui passe la réponse entière, soit le
driver décode et transmet une chaîne. Trancher avant d'écrire, et l'écrire dans le fichier.

## Ce qui a été tranché

1. **Le dispatch reçoit les octets *et* l'étiquette**, pas la réponse.
   `dispatch_extract(body, specs, *, content_type=None)` d'un côté,
   `dispatchExtract(body, specs, {bytes, contentType})` de l'autre. Passer la réponse entière aurait
   lié l'extraction à `httpx` — et à rien du tout sur l'autre moteur.
2. **Une table d'encodages bornée, identique des deux côtés** : `iso-8859-1` et ses alias → latin-1
   **strict** (le codec Python, pas l'alias WHATWG vers cp1252) ; `windows-1252`/`cp1252` → cp1252 ;
   **tout le reste, ou rien, → UTF-8**. Laisser Python accepter ses centaines de codecs aurait
   reconduit la divergence silencieuse que ce jalon existe pour fermer : la table **est** le
   contrat, et s'élargit des deux côtés à la fois.
3. **Aucune dépendance, et surtout pas `TextDecoder`** : absent de React Native, complet sous Node —
   il aurait mis la CI d'accord et le téléphone en désaccord. Le moteur embarqué porte un décodeur
   UTF-8 (algorithme WHATWG, soit un `U+FFFD` par sous-partie maximale, ce que rend `errors="replace"`
   de CPython) et une table mono-octet. Un BOM est **conservé**, comme le fait le codec Python.
4. **Les octets ne sont lus que si un `from: "text"` est déclaré.** Le driver embarqué scanne le bloc
   `extract` avant d'envoyer la requête — lecture statique légitime, les specs n'étant jamais rendues
   — et n'appelle `arrayBuffer()` que dans ce cas. Une requête sans extraction texte emprunte
   exactement le chemin d'avant et ne paie pas le pont base64 de React Native ; un hôte sans
   `arrayBuffer()` obtient une erreur **typée qui le nomme**, jamais un décodage UTF-8 tacite.
5. **Le refus va au-delà de `path`** : `where`, `fields`, `selector`, `selector_type`, `attr` et
   `multiple` sont refusés avec lui, pour la raison qui motivait `path` — un Blueprint qui croit
   filtrer. Le message nomme la clé fautive, et la règle est **du contrat** : elle vit dans les deux
   validateurs, pas dans la couche de portabilité du moteur embarqué.
6. **Un cas de conformance suffit à la parité, mais pas deux fois moins** : `run/18-text-body-and-charset`
   sert quatre routes (latin-1 bien étiqueté, UTF-8 **mal** étiqueté, sans `charset`, corps vide), ce
   qui a demandé un champ de route `charset` aux deux serveurs de fixtures. Le refus de `path` est,
   lui, figé par un cas de validation.

## Plan de test

Unitaires, des deux côtés :

| Cas | Attendu |
|---|---|
| Corps `text/plain` UTF-8 | rendu tel quel, à l'octet près |
| Corps déclaré `charset=iso-8859-1` avec accents | décodé selon l'en-tête, **pas** en UTF-8 |
| Corps sans `Content-Type` | UTF-8 par défaut |
| Corps vide | chaîne vide, pas `null` — une réponse vide est un résultat |
| `from: "text"` avec un `path` | refusé à la validation, message explicite |
| Corps binaire (une image) | décodé en remplaçant les octets invalides, sans lever — ce n'est pas au moteur de deviner qu'on s'est trompé de source |

Conformance : **un cas**, servi par les serveurs de fixtures des deux côtés, comparant le texte rendu.
C'est le seul endroit qui prouve que les deux décodages coïncident.

## Exemple exécutable à livrer

Un Blueprint sous `examples/vector/` qui récupère un iCalendar public et **assert** qu'il commence par
`BEGIN:VCALENDAR` — la garde de forme minimale d'un format à lignes, l'équivalent de l'`assert` sur la
racine JSON. Sans lui, une page d'erreur HTML de 200 octets passerait pour un calendrier vide.

**Livré** : [`examples/vector/ical-planning-text.blueprint.json`](../../examples/vector/ical-planning-text.blueprint.json)
— l'export ADE anonyme mesuré plus haut, inputs figés sur une plage passée, donc zéro configuration
et reproductible sans attendre une rentrée. Deux nuances honnêtes :

- la garde est une **appartenance** (`{{ 'BEGIN:VCALENDAR' in steps.cal.ics }}`) et non un préfixe :
  le sous-ensemble d'expressions n'a ni tranche ni `startswith`, et c'est le corollaire direct du
  refus de `from: "regex"` ;
- une seconde garde exige un **accent** (`Bases de données`), parce qu'une garde de forme seule
  passerait aussi sur un corps décodé de travers.

La contre-épreuve vit à côté, dans [`examples/mobile/ical-error-page-probe.blueprint.json`](../../examples/mobile/ical-error-page-probe.blueprint.json) :
le même export **sans paramètres** répond 500 avec une page HTML déclarée `ISO-8859-1`, et le run
échoue au step de garde sur les deux moteurs, mot pour mot.

## Définition de terminé

1. ✅ `from: "text"` implémenté dans les deux moteurs, décodage compris.
2. ✅ Tests unitaires du tableau ci-dessus, verts des deux côtés — plus une table d'octets UTF-8
   invalides, dont les valeurs attendues viennent de CPython et sont recopiées dans le test
   JavaScript : c'est ce qui garde les deux décodeurs alignés sur les cas dégénérés qu'un serveur
   ne peut pas facilement servir.
3. ✅ Un cas de conformance (quatre routes), plus un cas de validation pour le refus de `path`.
4. ✅ `contracts/actions.json` régénéré et sa garde verte.
5. ✅ `make check-all` et `make conformance` verts (trois exécuteurs).
6. ✅ [docs/acts/vector.md](../acts/vector.md) et [docs/embedded.md](../embedded.md) portent la
   troisième forme, la règle de décodage et la table d'encodages.
7. ✅ L'exemple joué pour de vrai, sur le poste **et** sur un iPhone : `caracteres: 21461` et
   `80712` identiques au moteur Python, et la sonde conçue pour échouer échoue au même step avec le
   même message. Le pont d'octets de React Native (blob → base64 → natif) n'existe nulle part
   ailleurs, c'est donc la seule vérification qui pouvait le couvrir.

## Critères d'acceptation

- Le même Blueprint rend **le même texte** sur les deux moteurs, y compris sur un corps mal étiqueté.
- Aucune sortie de step ne grossit : un `http.request` sans extraction `text` publie exactement ce
  qu'il publiait.
- Le vocabulaire ne gagne qu'une valeur d'énumération : pas de nouvelle action, pas de nouveau champ.

## Ce que ça débloque

[UKit 6-I](../../docs-ukit/README.md) — l'emploi du temps par iCal, donc la possibilité de brancher une
université sans porter son produit de planning. C'est, pour ce consommateur, la différence entre
« ajouter une fac » et « ajouter une fac dont on a réimplémenté le serveur d'emploi du temps ».
