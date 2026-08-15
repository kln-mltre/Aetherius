/**
 * The Blueprints the demo ships with — imported as JSON, from `examples/`.
 *
 * They are the *same files* `aetherius run` plays on a machine, not copies: bundling anything else
 * would make this app prove something other than what it exists to prove.
 *
 * Three cards are different, and they are the point of milestones 3-F and 3-H: they declare
 * `delivered`, so the screen asks the **registry** for their Blueprint instead of using an import.
 * The first has a bundled baseline, deliberately broken, and its fix arrives from a manifest. The
 * other two have **no bundled document at all** — one is covered by the reserved prefix and must
 * arrive, the other is not and must never arrive.
 *
 * Each entry carries a `status`, and it is the point of the bench rather than decoration: this
 * screen exists to walk a checklist on a device, and after a few passes nobody remembers what has
 * already been observed. `done` means *seen on a phone*, not "the tests pass".
 */

import { DELIVERED, OUT_OF_SCOPE, PORTAL } from "./delivery";

import deviceIpCheck from "../device-ip-check.blueprint.json";
import icalErrorPageProbe from "../ical-error-page-probe.blueprint.json";
import icalLargeBodyProbe from "../ical-large-body-probe.blueprint.json";
import quotesLoginConfirm from "../quotes-login-confirm.blueprint.json";
import sessionCookieProbe from "../session-cookie-probe.blueprint.json";
import sessionPersistProbe from "../session-persist-probe.blueprint.json";
import unreachableProbe from "../unreachable-probe.blueprint.json";
import webviewQuotes from "../webview-quotes.blueprint.json";
import bordeauxCasLogin from "../../continuum/bordeaux-cas-login.blueprint.json";
import icalPlanning from "../../vector/ical-planning-text.blueprint.json";
import jsonplaceholderFlow from "../../vector/jsonplaceholder-flow.blueprint.json";
import quotesWatch from "../../vector/quotes-watch.blueprint.json";
import ukitPlanning from "../../vector/ukit-inf601a5-test.blueprint.json";

// Jalon 3-G — le cas d'usage mobile reel, entierement decrit en Blueprints.
import referenceAffluence from "../reference/ukit-campus-affluence.blueprint.json";
import referenceAnnonces from "../reference/ukit-campus-annonces.blueprint.json";
import referenceCelcat from "../reference/ukit-celcat-semaine.blueprint.json";
import referenceMessagerie from "../reference/ukit-scolarite-messagerie.blueprint.json";
import referenceRestaurants from "../reference/ukit-campus-restaurants.blueprint.json";
import referenceSso from "../reference/ukit-scolarite-sso.blueprint.json";

/**
 * `done` = observé sur un téléphone · `partial` = le chemin nominal est vu, des variantes restent ·
 * `todo` = à jouer · `blocked` = bloqué par un tiers indisponible.
 *
 * `partial` existe parce que plusieurs vérifications montent souvent sur le même Blueprint :
 * marquer « à faire » une carte qui vient de réussir serait aussi trompeur que la marquer finie.
 * `blocked` couvre un tiers indisponible **et** un tiers dont le client défait le moteur : dans les
 * deux cas la carte ne peut pas passer, et la raison n'est pas dans le Blueprint.
 */
export const STATUS = {
  done: { label: "verifie", color: "#4e8a5a" },
  partial: { label: "partiel", color: "#9d7bd8" },
  todo: { label: "a faire", color: "#d4af37" },
  blocked: { label: "bloque", color: "#d08a3e" },
};

export const BLUEPRINTS = [
  {
    key: "reference-sso",
    title: "Reference : le dossier administratif",
    hint: "Le remplacant de la WebView cachee, mode froid : CAS puis identite. Un mauvais mot de passe doit donner LOGIN_FAILED.",
    blueprint: referenceSso,
    // Memes noms que la carte CAS : le trousseau est deja rempli si elle a servi.
    secrets: ["bordeaux_user", "bordeaux_pass"],
    status: "done",
    note: "Les cinq champs lus sur iPhone, identiques a `aetherius run`, et un mauvais mot de passe donne bien LOGIN_FAILED en pastille.",
  },
  {
    key: "reference-messagerie",
    title: "Reference : la messagerie",
    hint: "Mode chaud : la messagerie rebondit d'elle-meme sur le CAS. Une pause laisse la cascade de redirections arriver avant qu'on interroge la page.",
    blueprint: referenceMessagerie,
    secrets: ["bordeaux_user", "bordeaux_pass"],
    status: "done",
    note: "Reception (788) et non_lus: 788 sur iPhone, identiques a `aetherius run`. Le diagnostic a montre que l'agent est vivant et l'element present : ce qui se perdait, c'etait l'operation emise PENDANT la cascade de redirections du login. D'ou la pause, visible dans le fichier.",
  },
  {
    key: "reference-annonces",
    title: "Reference : les annonces (CDN)",
    hint: "Le fichier editorial servi par jsDelivr, filtre par un predicat declaratif.",
    blueprint: referenceAnnonces,
    status: "done",
    note: "Sorties identiques a `aetherius run`, vues sur iPhone.",
  },
  {
    key: "reference-restaurants",
    title: "Reference : la restauration",
    hint: "Categorie ecartee par where sur un champ imbrique, date DD-MM-YYYY produite par format_date.",
    blueprint: referenceRestaurants,
    status: "done",
    note: "Sorties identiques a `aetherius run`, vues sur iPhone.",
  },
  {
    key: "reference-affluence",
    title: "Reference : l'affluence des BU",
    hint: "En-tetes imites, corps JSON, extraction imbriquee. Le filtre de categorie reste applicatif, et c'est le sujet.",
    blueprint: referenceAffluence,
    status: "done",
    note: "Sorties identiques a `aetherius run`, vues sur iPhone.",
  },
  {
    key: "reference-celcat",
    title: "Reference : l'emploi du temps",
    hint: "POST form-encode, cle repetee, borne de fin exclusive. Constantes magiques devenues des vars nommees.",
    blueprint: referenceCelcat,
    status: "done",
    note: "Vise le service de l'universite DIRECTEMENT : le relais qu'interroge l'application d'origine existe pour contourner une contrainte de navigateur, et une requete native n'y est pas soumise. Le relais etait d'ailleurs en panne (522) — un tiers mort produit un echec nomme, pas une liste vide.",
  },
  {
    key: "delivery-quotes",
    title: "Livraison : reparer sans republier",
    hint: "Le Blueprint embarque est casse (il demande une page renommee). Rafraichir le manifeste doit livrer la correction, et le run passer.",
    // Pas de `blueprint` : c'est le registre qui le rend, embarque ou distant.
    delivered: DELIVERED,
    // Campagne complete sur iPhone : socle casse, correction distante, cache qui survit a la mort de
    // l'application, CDN coupe, mode avion, fichier altere, publication d'une correction, et les
    // deux interrupteurs d'arret. La premiere passe a trouve le cache HTTP de la plateforme.
    status: "done",
    note: "Les neuf parcours vus sur telephone. Le fichier altere doit donner « integrity check failed » : purger avec « Revenir a l'embarque » avant, sinon le rafraichissement repond kept sans retelecharger.",
  },
  {
    key: "portail-ajoute",
    title: "Livraison : ajouter sans republier",
    hint: "Ce Blueprint n'est PAS dans l'application. Avant de rafraichir, le run doit echouer proprement (rien a jouer) ; apres, il tourne — il est entre par le prefixe reserve mobile.portail.",
    // Aucun `blueprint` et aucun socle : c'est tout le sujet du jalon 3-H.
    delivered: PORTAL,
    // Les sept parcours vus sur iPhone, dont les trois qui ne se verifient que la : survie a la mort
    // de l'application, desinstallation par retrait d'`allowNew`, et purge qui ne ressuscite pas.
    status: "done",
    note: "Le geste decisif est le dernier : rallumer allowNew laisse « absent » jusqu'au rafraichissement suivant. Une purge qui serait une mise en veille ne se verrait pas autrement.",
  },
  {
    key: "portail-hors-perimetre",
    title: "Livraison : ce que le prefixe refuse",
    hint: "Publie dans le MEME manifeste, mais hors du prefixe reserve. Il doit rester introuvable quoi qu'on fasse, et le rapport doit dire pourquoi. C'est le cas qui echoue qui prouve la borne.",
    delivered: OUT_OF_SCOPE,
    status: "done",
    note: "Le journal du serveur est la vraie preuve : ce fichier n'a JAMAIS ete telecharge. La garde mord a la lecture du manifeste, pas apres le telechargement.",
  },
  {
    key: "quotes-login-confirm",
    title: "Parcours applicatif : secrets + confirm",
    hint: "Identifiants du trousseau, modal de confirmation avant de les envoyer, echec nomme si le portail refuse.",
    blueprint: quotesLoginConfirm,
    // Ce que le Blueprint declare : l'ecran les demande une fois et les range dans SecureStore.
    secrets: ["quotes_user", "quotes_pass"],
    // Verifie sur iPhone : modal, secret masque dans le flux, redirection du login traversee,
    // connecte: 1, refus, et expiration pendant que l'application dort.
    status: "done",
    note: "Approuve, refuse et expiration en arriere-plan : les trois vus. Ne sert PAS a tester l'annulation (le modal recouvre l'ecran).",
  },
  {
    key: "bordeaux-cas-login",
    title: "Portail reel : CAS de l'universite",
    hint: "Sonde dure : identifiants du trousseau, portail authentifiant reel. De mauvais identifiants doivent donner LOGIN_FAILED.",
    blueprint: bordeauxCasLogin,
    secrets: ["bordeaux_user", "bordeaux_pass"],
    status: "done",
    note: "Bons identifiants -> peut_se_deconnecter: 1, et un mauvais mot de passe -> LOGIN_FAILED : les deux vus. Sert aussi a tester l'annulation (bascule WebView ON).",
  },
  {
    key: "unreachable-probe",
    title: "Reseau : une source injoignable",
    hint: "Concue pour echouer. Le titre doit etre « Service indisponible », et l'erreur doit tomber sur le step nav — pas sur l'attente qui suit. Relancer aussitot doit redonner exactement le meme echec.",
    blueprint: unreachableProbe,
    // Verifie sur iPhone : « Service indisponible », [error] sur nav, aucune ligne DIAGNOSTIC, et le
    // meme echec a chaque relance. La premiere passe visait le port 1 et rendait PAGE_ABSENTE — c'est
    // elle qui a trouve le filtre de react-native-webview.
    status: "done",
    note: "Remplace le mode avion : rien a changer sur le telephone. L'adresse est choisie — port 4, qui REFUSE la connexion. Un port bloque par politique (1, 7, 9…) fait rendre a WebKit une erreur 'cannot show URL' que react-native-webview avale : l'hote n'apprend rien et la sonde ne prouve rien. Une pastille PAGE_ABSENTE signifie que le defaut corrige en 0.5.3 est revenu ; le step DIAGNOSTIC dit alors sur quel document l'agent a atterri.",
  },
  {
    key: "session-persist-probe",
    title: "Session : survit-elle au redemarrage ?",
    hint: "Ouvre la page et compte le lien de deconnexion. 1 = la session tient, 0 = elle est partie.",
    blueprint: sessionPersistProbe,
    status: "done",
    note: "connecte: 1 avec la bascule, 0 sans : verifie. Apres avoir tue l'app, 0 est correct — c'est un cookie de session.",
  },
  {
    key: "webview-quotes",
    title: "Act II : la WebView",
    hint: "Navigation, attente du DOM, extraction typee et JS injecte, dans une WebView cachee.",
    blueprint: webviewQuotes,
    status: "done",
  },
  {
    key: "ukit-planning",
    title: "POST form : l'API de UKit",
    hint: "Corps encode en formulaire contre le vrai serveur ADE, cle repetee comprise.",
    blueprint: ukitPlanning,
    status: "done",
    note: "Ferme le point laisse ouvert par le jalon 3-C.",
  },
  {
    key: "device-ip-check",
    title: "Device IP check",
    hint: "Quelle IP a emis la requete ? Elle doit differer de celle du poste de dev.",
    blueprint: deviceIpCheck,
    status: "done",
    note: "Sans objet si le PC est sur le partage du telephone : meme IP des deux cotes.",
  },
  {
    key: "jsonplaceholder-flow",
    title: "Flux : if + for_each",
    hint: "Extraction JSONPath, branche conditionnelle, une iteration par utilisateur.",
    blueprint: jsonplaceholderFlow,
    status: "done",
  },
  {
    key: "quotes-watch",
    title: "Scraping HTML",
    hint: "Extraction CSS hors navigateur, sur une page reelle.",
    blueprint: quotesWatch,
    status: "done",
  },
  // Jalon 3-I — l'extraction `from: "text"`. Sur l'appareil, une lecture en octets emprunte un
  // chemin que Node n'a pas (blob -> base64 -> pont natif) : ces trois cartes sont la pour l'eprouver.
  {
    key: "ical-planning",
    title: "Texte : l'emploi du temps en iCal",
    hint: "Export ADE anonyme ramene tel quel par from: text. caracteres doit valoir exactement ce que rend `aetherius run`, et accents: true.",
    blueprint: icalPlanning,
    status: "done",
    note: "caracteres: 21461 sur iPhone, identique au moteur Python — 21 592 octets pour 21 461 caracteres, donc le pont d'octets (blob, base64, natif) et le decodeur UTF-8 embarque rendent ce que rend CPython.",
  },
  {
    key: "ical-large-body",
    title: "Texte : un corps de 80 Ko",
    hint: "Meme dialecte, corps quatre fois plus gros et second serveur. Un ecart d'un caractere avec le poste designe le pont d'octets de React Native.",
    blueprint: icalLargeBodyProbe,
    status: "done",
    note: "caracteres: 80712 sur iPhone, identique au poste. Le calendrier est republie de temps en temps : comparer les deux runs au meme moment, pas a une valeur ecrite ici.",
  },
  {
    key: "ical-error-page",
    title: "Texte : une page d'erreur n'est pas un calendrier",
    hint: "Concue pour echouer. Le run doit finir en echec sur le step shape (ICAL_INVALID) et la ligne DIAGNOSTIC ne doit jamais paraitre.",
    blueprint: icalErrorPageProbe,
    status: "done",
    note: "Echec au step shape, ICAL_INVALID, aucune ligne DIAGNOSTIC. La pastille dit « Reponse inattendue » (famille rejected) : c'est exact — la source a repondu, avec une page d'erreur. Le « Reessayer peut aboutir » qui l'accompagne vient de ce qu'`assert` leve une StatusAssertionError, comme le prefixe « Expected HTTP 1, got 0 » ; les deux sont anterieurs au jalon.",
  },
  {
    key: "session-cookie-probe",
    title: "Session : le magasin de la plateforme",
    hint: "carried doit valoir true ici, et false sous Node : c'est l'asymetrie assumee.",
    blueprint: sessionCookieProbe,
    // Rejouee une fois httpbin.org revenu : `carried: true` sur l'appareil, ce qui verifie que le
    // magasin de cookies de la plateforme porte la session **a travers une redirection** — la
    // promesse du jalon 3-C, qu'aucun test hors appareil ne peut montrer.
    status: "done",
    note: "carried: true sur l'appareil, false sous Node : l'asymetrie declaree, observee.",
  },
];
