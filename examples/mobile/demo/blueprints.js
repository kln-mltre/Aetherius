/**
 * The Blueprints the demo ships with — imported as JSON, from `examples/`.
 *
 * They are the *same files* `aetherius run` plays on a machine, not copies: bundling anything else
 * would make this app prove something other than what it exists to prove. Delivering Blueprints
 * properly (a bundled asset, a download, a cache, a kill switch) is milestone 3-F; until then, an
 * import is honest and enough.
 *
 * Each entry carries a `status`, and it is the point of the bench rather than decoration: this
 * screen exists to walk a checklist on a device, and after a few passes nobody remembers what has
 * already been observed. `done` means *seen on a phone*, not "the tests pass".
 */

import deviceIpCheck from "../device-ip-check.blueprint.json";
import quotesLoginConfirm from "../quotes-login-confirm.blueprint.json";
import sessionCookieProbe from "../session-cookie-probe.blueprint.json";
import sessionPersistProbe from "../session-persist-probe.blueprint.json";
import webviewQuotes from "../webview-quotes.blueprint.json";
import bordeauxCasLogin from "../../continuum/bordeaux-cas-login.blueprint.json";
import jsonplaceholderFlow from "../../vector/jsonplaceholder-flow.blueprint.json";
import quotesWatch from "../../vector/quotes-watch.blueprint.json";
import ukitPlanning from "../../vector/ukit-inf601a5-test.blueprint.json";

/**
 * `done` = observé sur un téléphone · `partial` = le chemin nominal est vu, des variantes restent ·
 * `todo` = à jouer · `blocked` = bloqué par un tiers indisponible.
 *
 * `partial` existe parce que plusieurs vérifications montent souvent sur le même Blueprint :
 * marquer « à faire » une carte qui vient de réussir serait aussi trompeur que la marquer finie.
 */
export const STATUS = {
  done: { label: "verifie", color: "#4e8a5a" },
  partial: { label: "partiel", color: "#9d7bd8" },
  todo: { label: "a faire", color: "#d4af37" },
  blocked: { label: "bloque", color: "#d08a3e" },
};

export const BLUEPRINTS = [
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
