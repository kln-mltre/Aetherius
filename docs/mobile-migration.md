# Migrer une application mobile vers des Blueprints

Comment une couche d'accès au web écrite à la main — des services HTTP et une WebView cachée pilotée
par du JavaScript injecté — devient un jeu de Blueprints joués par le
[moteur embarqué](embedded.md), sur l'appareil.

Ce guide est issu du jalon [3-G](phase-3/3-g-reference.md) et se lit avec les Blueprints qu'il a
produits : [`examples/mobile/reference/`](../examples/mobile/reference/). Ils ne sont pas des
illustrations, ce sont les ports réels des sources d'un projet en production
([UKit](../docs-ukit/README.md)), joués sur les deux moteurs — cinq sur six sur un vrai téléphone,
le sixième butant sur une limite écrite plus bas plutôt que passée sous silence.

## Ce que ce guide couvre, et ce qu'il ne couvre pas

Aetherius remplace **l'accès au web**. Pas la couche de service, pas l'application.

| Ce qui devient un Blueprint | Ce qui reste du code applicatif |
|---|---|
| L'URL, la méthode, les en-têtes, l'encodage du corps | Le cache et sa péremption |
| Les constantes magiques du protocole distant | La persistance, le trousseau, l'état |
| La sélection et le nommage des données extraites | L'internationalisation |
| Le filtrage exprimable sur un élément | Le calcul (distances, tri, agrégats, dérivés) |
| Le parcours d'authentification et les attentes | Le rendu, la navigation, la logique métier |

La frontière n'est pas administrative, elle est **fonctionnelle** : un Blueprint décrit ce qu'on
demande à une source et ce qu'on en retient. Tout ce qui a besoin de l'heure courante, de la
position de l'utilisateur, de l'état des écrans ou de la langue choisie n'a pas ces informations —
et ne doit pas les avoir, sinon le fichier cesse d'être rejouable à l'identique par les deux
moteurs.

Une migration qui essaierait d'absorber le cache dans les Blueprints échouerait, et pour de bonnes
raisons.

## Avant de commencer : inventorier ses sources

La première étape ne touche à aucun fichier. Elle consiste à écrire, source par source : l'URL
exacte, la méthode, les en-têtes indispensables, la forme du corps, les constantes et **leur
signification**, les règles de filtrage, et ce que le code fait de la réponse.

UKit a cet inventaire : [`docs/sources-externes.md`](../docs-ukit/README.md) — sept sources,
« assez de détail pour rejouer chaque appel sans lire le code ». C'est exactement le document dont
la migration a besoin, et l'écrire révèle déjà la moitié du travail : les constantes qu'on ne sait
plus justifier, les filtres dupliqués, les erreurs avalées.

Ordre de migration recommandé, du plus sûr au plus engageant :

1. un fichier statique ou une API publique **sans en-tête particulier** — le port dure dix minutes
   et valide la chaîne complète (voir `ukit-campus-annonces`) ;
2. une API avec en-têtes et filtres (`ukit-campus-restaurants`, `ukit-campus-affluence`) ;
3. une API avec encodage exigeant (`ukit-celcat-semaine` : form-encodé, clé répétée, borne
   exclusive) ;
4. **en dernier**, le parcours authentifiant (`ukit-scolarite-sso`). C'est le plus rentable, et
   celui qui demande d'avoir confiance dans tout le reste.

## Migrer un service HTTP (Act I)

### Avant

```ts
const response = await fetch('https://cdn.jsdelivr.net/gh/KAE-Lab/ukit-data@main/annonces.json');
if (!response.ok) throw new Error('Network response was not ok');
const data = await response.json();
const now = new Date();
if (data && data.annonces) {
    return data.annonces.filter((item: BdeAnnonce) => {
        if (!item.is_active) return false;
        return new Date(item.expires_at) > now;
    });
}
return [];
```

### Après

```json
{
  "id": "annonces",
  "action": "http.request",
  "method": "GET",
  "url": "{{ vars.cdn }}/annonces.json",
  "headers": { "Accept": "application/json" },
  "expect": { "status": 200 },
  "extract": {
    "publiees": {
      "from": "json", "path": "$.annonces[*]", "where": "item.is_active == true",
      "fields": { "id": "$.id", "titre": "$.title", "expire_le": "$.expires_at" }
    }
  }
}
```

Quatre choses ont changé, et une seule est cosmétique.

- **L'URL est une donnée.** Le jour où le dépôt change de branche, on publie un Blueprint corrigé
  ([livraison](embedded.md#la-livraison-des-blueprints)) au lieu d'attendre une revue de store.
- **`expect` remplace le `if (!response.ok)`.** Un statut inattendu devient un échec **nommé**
  (`rejected` pour `describeFailure`), pas un tableau vide.
- **Le filtre `is_active` est déclaratif.** Il tient dans une expression, donc il descend dans le
  Blueprint.
- **Le filtre `expires_at > now` ne descend pas** — et c'est le premier arbitrage du guide, pas un
  manque. Un prédicat `where` ne connaît que son élément : ni l'heure, ni le fuseau de l'appareil.
  L'expiration reste une ligne applicative, et elle y est mieux : la même donnée peut être affichée
  grisée plutôt que masquée, ce qu'un filtre côté extraction interdirait.

### Un relais posé pour le navigateur peut disparaître

Question à se poser sur chaque source : **pourquoi passe-t-on par là ?** L'application de référence
interrogeait le calendrier universitaire à travers un point d'entrée dédié — un relais hébergé par
l'équipe — alors que le service de l'université répond parfaitement bien en direct.

La raison est structurelle, et elle disparaît avec la migration : une page web ne peut pas appeler
un autre domaine sans son accord, et cette application était une WebView. Une requête émise
**nativement depuis l'appareil** n'est pas soumise à cette règle. Le Blueprint vise donc le service
directement :

```json
"vars": { "domaine": "https://celcat.exemple.fr/calendar" }
```

Un serveur à héberger, à payer et à surveiller sort de l'architecture. Ce n'est pas un cas isolé :
un relais, un proxy « CORS », une fonction *serverless* qui ne fait que retransmettre — chacun mérite
la question, parce que la contrainte qui l'a fait naître n'existe plus.

### Les constantes magiques deviennent des `vars` nommées

C'est le gain le plus immédiat et le moins spectaculaire. `resType: '103'` disséminé dans deux
services devient :

```json
"vars": { "res_type": "103", "cal_view": "agendaWeek", "colour_scheme": "3" }
```

et la borne de fin **exclusive** — un `moment(date).add(1, 'day')` que rien n'expliquait — s'écrit
là où on la lit :

```json
"form": { "start": "{{ inputs.lundi }}", "end": "{{ inputs.lundi | add_days(7) }}" }
```

L'encodage exigeant survit au passage : `federationIds[]` reste une clé littérale répétable, et les
deux moteurs postent **les mêmes octets** (`quote_plus`, pas `URLSearchParams` — voir
[docs/embedded.md](embedded.md#act-i--vector-sur-fetch)).

### Les conversions de format descendent aussi

L'API de restauration renvoie et attend `DD-MM-YYYY` là où l'application manipule des dates ISO. Le
code portait la conversion à la main, avec son bug documenté (`.includes()` sur une valeur
possiblement nulle). Côté Blueprint :

```json
"url": "{{ vars.api }}/restaurants/{{ inputs.restaurant }}/menu/{{ inputs.jour | format_date('%d-%m-%Y') }}"
```

Le sens de la conversion compte : `format_date` **produit** le format de l'API à partir d'une date
ISO. Il ne sait pas lire `DD-MM-YYYY` — les filtres de date acceptent `YYYY-MM-DD` et refusent le
reste **bruyamment**, des deux côtés. Reformater une date **reçue** reste donc applicatif.

### Ce que la grammaire refuse, et pourquoi c'est voulu

Le prédicat `where` accepte les comparaisons, la logique booléenne, `not`, les attributs et les
littéraux. Il refuse les appels, les filtres, l'indexation et les ternaires — **des deux côtés**,
délibérément : un prédicat accepté par un moteur et refusé par l'autre serait pire qu'une limite.

Conséquence concrète, rencontrée au port de l'API d'affluence : « garder les sites dont l'une des
catégories a l'identifiant 1 ou 20 » n'est pas exprimable, parce que `categories` est une liste et
qu'indexer une liste est refusé. Le Blueprint extrait donc les identifiants de catégorie et
l'application filtre :

```json
"categories": "$.categories[*].id"
```

C'est la bonne réponse, pas un contournement : la règle « qu'est-ce qu'une bibliothèque » est une
décision **produit**, pas une propriété de la source.

> **Piège d'arité.** Un chemin de `fields` qui ne correspond à rien rend `null`, une seule fois rend
> **la valeur**, plusieurs fois rend **la liste**. Un site à une seule catégorie rend donc `20` et
> non `[20]`. Le code appelant doit normaliser ; les deux moteurs se comportent à l'identique
> (cas de conformance `extract-fields-arity`).

### Les erreurs cessent d'être avalées

Tous les services de départ renvoient `null` ou `[]` en cas d'échec. Le résultat est écrit noir sur
blanc dans leur propre documentation : « une panne du fournisseur et une réponse légitimement vide
sont indistinguables ». Un écran « aucun résultat » peut masquer une source morte.

Le Blueprint échoue, et [`describeFailure`](embedded.md#le-modèle-derreur) range l'échec dans l'une
des familles d'écran :

| Ce qui s'est passé | `kind` | Ce que l'application affiche |
|---|---|---|
| Réseau injoignable, délai dépassé | `unavailable` | « Service indisponible », avec un bouton Réessayer |
| Statut inattendu (`expect`) | `rejected` | « Réponse inattendue » — la source a changé |
| Sélecteur ou extraction sans correspondance | `data` | « La page a changé » — Blueprint à corriger |
| Secret ou entrée absente | `config` | « Saisis tes identifiants » |
| Échec **nommé** par le Blueprint (`fail:CODE`) | `blocked` + `code` | Le message du cas, tel quel |

Une liste vide redevient ce qu'elle doit être : **une liste vide**.

## Migrer une WebView cachée (Act II)

C'est le morceau qui justifie la phase. Le point de départ, dans UKit : 323 lignes de composant dont
environ 176 de **JavaScript en gabarits de chaîne**, quatre scripts déclenchés selon l'URL de fin de
chargement, une machine à états de phases, et le même motif d'attente recopié par script.

### Le JavaScript injecté devient des steps

```ts
// avant : un script par page, avec sa propre détection et sa propre attente
u.value = ${JSON.stringify(username)};
p.value = ${JSON.stringify(password)};
var btn = document.querySelector('input[type="submit"], button[type="submit"], .btn-submit');
if (btn) { btn.click(); } else { f.submit(); }
```

```json
{ "action": "fill",  "selector": "#username", "value": "{{ secrets.bordeaux_user }}" },
{ "action": "fill",  "selector": "#password", "value": "{{ secrets.bordeaux_pass }}" },
{ "action": "click", "selector": "input[type=submit]" }
```

Le gain n'est pas la brièveté. C'est que **les paramètres ne traversent plus la source d'un
script** : ils sont encodés en JSON et transmis par une RPC corrélée
([docs/embedded.md](embedded.md#le-protocole-de-lagent-injecté)). Le second script injecté de UKit
montre pourquoi ça compte — il interpole le mot de passe entre apostrophes :

```ts
passwordInput.value = '${savedCredentials?.password || ''}';
```

Un mot de passe contenant une apostrophe casse le script. Pas l'authentification : **le script**,
silencieusement. Cette classe de bug devient impossible par construction.

### L'attente est écrite une fois

Chaque script artisanal porte son `MutationObserver`, son plafond (18 s, 20 s, 18 s) et sa valeur de
repli quand le plafond tombe. Trois copies, trois comportements légèrement différents. Le Blueprint
déclare l'attente, et le moteur l'implémente une fois :

```json
{ "action": "wait_for", "selector": "#gwt-uid-41", "timeout_ms": 25000,
  "on_timeout": "fail:LOGIN_FAILED" }
```

`fail:CODE` est le point important : l'échec porte **le nom que le Blueprint lui a donné**, et
l'application branche dessus au lieu de deviner. Les deux moteurs le remontent — côté embarqué dans
`describeFailure(...).code`, côté Python en tête du message d'erreur (`LOGIN_FAILED: wait_for timed
out …`).

### Une lecture qui suit une attente porte un délai court

Corollaire non évident, et il a coûté une campagne sur appareil pour être vu. Un `extract` qui suit
un `wait_for` réussi **réarme** une auto-attente du même budget que le step. Sur un téléphone, les
minuteurs de la page ne sont pas fiables — une WebView hors écran les ralentit — alors que
l'appelant, lui, compte en temps réel. Si l'élément a disparu entre les deux steps, l'agent attend
son propre délai, l'appelant abandonne le premier, et l'échec devient un **silence** rapporté comme
« la page a changé » au lieu d'un « aucun élément ne correspond ».

```json
{ "id": "messagerie", "action": "extract", "timeout_ms": 5000,
  "outputs": { "non_lus": { "selector": "#zti__main_Mail__2_textCell", "as": "number" } } }
```

La règle est simple : **une lecture n'a rien à attendre**, sa présence vient d'être prouvée. Un
budget court garantit que la page réponde avant l'appelant, donc qu'un échec reste lisible.

### Laisser arriver une cascade d'authentification avant de l'interroger

```json
{ "action": "click",    "selector": "input[type=submit]" },
{ "action": "wait",     "ms": 15000 },
{ "action": "wait_for", "selector": "#compteur", "timeout_ms": 30000,
  "on_timeout": "fail:MESSAGERIE_INDISPONIBLE" }
```

Ce `wait` détonne, et c'est voulu : **l'auto-attente existe précisément pour ne pas semer des délais
fixes**, et une WebView écrite à la main en est truffée. Il est là parce qu'une authentification
unifiée à plusieurs sauts, suivie d'un client qui pose son propre fragment, fait perdre l'opération
émise pendant la cascade — le moteur ne rejoue que ce qu'il sait avoir perdu, et il n'apprend pas
tous ces remplacements de document.

La règle pratique : **si un clic déclenche une redirection en chaîne, laisse-la arriver.** Et
laisse-le visible dans le fichier plutôt que de le déguiser en `timeout` généreux — un contournement
qu'on peut lire est un contournement qu'on saura retirer le jour où le moteur absorbera le cas.

Le symptôme, si on l'oublie, ne ressemble pas à sa cause : « la page a changé », alors que la page va
très bien. Quatre passes sur appareil ont été nécessaires pour le nommer, et ce qui a tranché est une
sonde qui ne demandait rien à la page sinon **ce qu'elle était** — URL, titre, nombre de nœuds. Quand
un diagnostic patine, cesser d'interroger la donnée qu'on veut et demander à la page de se décrire
coûte un run et élimine trois hypothèses.

### Découper selon les parcours de l'application, pas selon les pages

Le composant d'origine enchaîne quatre pages dans une seule session, avec une machine à états. La
traduction fidèle serait un Blueprint de douze steps — et c'est ce qu'on a écrit d'abord. Mais
l'application distingue déjà deux parcours, *froid* (identité complète, au premier login) et *chaud*
(la messagerie seule, aux lancements suivants), et chaque service **rebondit lui-même** sur
l'authentification unifiée. Deux Blueprints valent donc mieux qu'un : ils correspondent à ce que
l'application demande vraiment, chacun se rejoue seul, et une panne de l'un n'emporte pas l'autre.
Un Blueprint long parce qu'on a recopié un enchaînement que personne ne joue d'un bloc ne démontre
rien.

### Partir du service, pas du portail

Le code d'origine ouvre la page d'accueil du portail puis navigue de page en page en injectant
`window.location.href = …`. Le Blueprint de référence ouvre **directement** le service voulu :

```json
{ "action": "navigate", "url": "{{ vars.dossier }}" }
```

Le service redirige vers le CAS avec son paramètre `service=`, et la redirection de retour ramène à
la bonne page — fragment compris. C'est plus court, plus robuste, et ça survit à ce qui est arrivé
entre-temps : l'hôte du portail historique **ne résout plus**. Un parcours qui dépend d'une page
d'accueil dépend de la page la plus susceptible d'être refondue.

### Le user-agent est parfois porteur de sens

`options.stealth.user_agent` est la seule bribe de discrétion du périmètre embarqué, et elle n'est
pas décorative. Mesuré sur la messagerie de l'université :

| User-agent | URL servie | `#zti__main_Mail__2_textCell` |
|---|---|---|
| Chrome desktop | `/mail#1` | présent — « Réception (788) » |
| Safari iOS | `/modern/` | **absent** (DOM entièrement différent) |

Un portail sert souvent un DOM différent aux mobiles ; le Blueprint doit pouvoir en décider. Sur un
appareil, c'est le seul moyen d'atteindre le DOM que les sélecteurs décrivent.

### Le comptage par expression régulière disparaît

```ts
var m = t.match(/\((\d+)\)/);   // "Réception (760)" -> "760", string
```

```json
"non_lus": { "selector": "#zti__main_Mail__2_textCell", "as": "number" }
```

`as: "number"` extrait le premier nombre du texte et rend un **entier**, identiquement sur les deux
moteurs. Limite honnête : un libellé sans parenthèses rend `null` là où le code rendait `"0"`. C'est
une différence à décider côté application, pas à ignorer.

## Les fragilités : celles qui disparaissent, celles qui restent

| Fragilité de départ | Après migration |
|---|---|
| Constantes magiques disséminées | `vars` nommées, en un seul endroit |
| Parsing par expression régulière | `as: number`, `fields`, `where` — ou explicitement applicatif |
| Erreurs avalées (`catch { return null }`) | Erreurs typées, huit familles d'écran |
| JavaScript injecté non typé | Vocabulaire d'actions fermé, validé avant le run |
| Identifiants interpolés dans une source | Paramètres encodés en JSON, jamais concaténés |
| Attente recopiée par script | Une auto-attente, un `timeout_ms`, un `fail:CODE` |
| **Sélecteurs positionnels** (`#gwt-uid-41`) | **Toujours positionnels** |

La dernière ligne est celle qu'il ne faut pas maquiller. Les identifiants du dossier administratif
sont attribués par le framework de la page selon l'ordre de construction du DOM : une modification
côté université les décale silencieusement. La migration ne les rend **pas** robustes. Ce qu'elle
change est ailleurs, et c'est déjà beaucoup : ils deviennent **une ligne dans un fichier de
données**, corrigeable à distance en quelques minutes pour tous les utilisateurs, au lieu d'une
constante compilée dans un binaire en attente de publication.

Et le format déclaratif permet un filet que le code d'origine n'avait pas : lire **le libellé
voisin** et l'affirmer.

```json
{ "action": "assert",
  "condition": "{{ steps.dossier.libelle_numero == 'Dossier' and steps.dossier.libelle_ine == 'NNE' }}",
  "message": "Les libelles du dossier ont bouge : les identifiants sont positionnels, donc les valeurs lues ne sont plus celles qu'on croit." }
```

Un décalage devient un **échec nommé** au lieu d'une donnée fausse enregistrée dans le trousseau.
C'est le seul endroit du guide où la version migrée est franchement meilleure que l'originale, et
elle ne le doit qu'au fait que la description est de la donnée.

## Migrer sans casser : la stratégie incrémentale

Un remplacement en bloc d'une couche d'accès réseau est irréaliste sur une application en
production. Un service à la fois, derrière sa signature existante :

```ts
// La signature ne bouge pas : les écrans ne savent pas ce qui se passe derrière.
async function fetchAnnonces(): Promise<BdeAnnonce[]> {
  try {
    const result = await client.run(await registry.resolve("ukit.campus.annonces"), {});
    if (result.status === "success") return result.outputs.annonces as BdeAnnonce[];
    report(describeFailure(result));            // journalise, ne masque pas
  } catch (error) {
    report(describeFailure(error));
  }
  return legacyFetchAnnonces();                 // repli, le temps de la verification
}
```

Trois règles qui font la différence entre une migration et une réécriture :

1. **La signature typée existante ne bouge pas.** Les écrans ne doivent pas apprendre qu'il y a un
   moteur derrière ; sinon la migration cesse d'être réversible.
2. **L'ancien code reste en repli** jusqu'à ce que les sorties aient été comparées sur des données
   réelles — puis il est retiré, parce qu'un repli qu'on ne retire jamais devient deux
   implémentations à maintenir.
3. **Le cache reste où il est.** Il enveloppe l'appel, avant comme après. C'est ce qui rend la
   bascule invisible.

Le socle embarqué n'est pas optionnel : les Blueprints sont **importés** dans le binaire, et la
surcouche distante ne fait que les mettre à jour. Une application doit fonctionner au premier
lancement, hors ligne, sans avoir jamais contacté le réseau.

## Vérifier une migration

La question n'est pas « est-ce que ça tourne » mais « est-ce que ça rend **la même chose** ».

```bash
# 1. le moteur Python, depuis le poste
aetherius run examples/mobile/reference/ukit-campus-annonces.blueprint.json

# 2. le moteur embarque, sous Node, sur le meme fichier
#    (voir docs/embedded.md, section « Executer un Blueprint »)

# 3. le moteur embarque, sur l'appareil : la meme carte dans l'application de demonstration
```

Puis le chemin dégradé, qui est celui qu'on ne teste jamais et qui décide de l'expérience réelle :
mode avion, source qui répond un statut inattendu, identifiants faux, sélecteur devenu introuvable.
Chacun doit produire un écran **différent**. S'ils produisent tous « aucun résultat », la migration
n'a rien apporté.

## Limites connues

- **Pas de calcul dans un Blueprint.** Distances, tris par proximité, agrégats, dédoublonnage :
  applicatifs. Le vocabulaire d'expressions n'a ni fonctions ni arithmétique sur collections, et le
  jour où il en aurait, il faudrait le réimplémenter à l'identique dans les deux moteurs.
- **Pas d'heure courante dans un prédicat.** Toute règle de péremption reste applicative.
- **Pas d'indexation dans `where`.** Un filtre « l'un des éléments de cette liste vaut X » n'est pas
  exprimable ; extraire le champ et filtrer côté application.
- **Pas de reformatage d'une date reçue.** Les filtres de date lisent `YYYY-MM-DD` et refusent le
  reste ; ils servent à *produire* un format, pas à en interpréter un.
- **Pas d'`upload`, de `drag` ni de `screenshot`** sur le moteur embarqué, et le `status` de
  `navigate` n'existe pas — refusés **à la validation**, jamais au milieu d'un run. Détails :
  [docs/embedded.md](embedded.md#ce-que-lact-ii-embarqué-ne-fait-pas).
- **Acts III et IV restent au moteur Python.** Un Blueprint `oracle` ou `phantom` est refusé sur
  l'appareil, avec un message qui le dit.
- **Un seul run Act II à la fois** : une WebView, un run. Le second est refusé bruyamment.
- **Une opération émise pendant un enchaînement de navigations se perd** sur l'appareil. Une
  authentification unifiée enchaîne plusieurs sauts, puis le client pose son propre fragment ; la
  première opération qui suit le clic part dans le vide, et l'échec arrive **en silence**. Le
  contournement est une pause explicite après le clic (voir ci-dessous) ; la limite du moteur est
  écrite dans [docs/embedded.md](embedded.md#sondes-du-jalon-3-g).

## Tester

Les cinq Blueprints de référence vivent dans
[`examples/mobile/reference/`](../examples/mobile/reference/) et sont validés contre le schéma par
la CI, comme tout ce qui vit sous `examples/`.

```bash
aetherius run examples/mobile/reference/ukit-campus-annonces.blueprint.json
aetherius run examples/mobile/reference/ukit-campus-restaurants.blueprint.json
aetherius run examples/mobile/reference/ukit-campus-affluence.blueprint.json
aetherius run examples/mobile/reference/ukit-celcat-semaine.blueprint.json

# identifiants requis : secrets bordeaux_user / bordeaux_pass dans .env (jamais dans le fichier)
aetherius run examples/mobile/reference/ukit-scolarite-sso.blueprint.json
```

Attendu, dans l'ordre : la liste des annonces publiées ; les restaurants moins la catégorie écartée,
puis les repas d'un jour ; les sites d'affluence et l'état d'ouverture de l'un d'eux ; la semaine de
cours d'un groupe ; enfin les champs du dossier administratif et le nombre de messages non lus.

Sur l'appareil, les mêmes fichiers sont des cartes de l'application de démonstration
([`examples/mobile/README.md`](../examples/mobile/README.md)) — c'est là que se joue le point 5 de
[CONTRIBUTING](../CONTRIBUTING.md#définition-de--terminé-), et les résultats des sondes sont
consignés dans [docs/embedded.md](embedded.md#sondes-du-jalon-3-g).
