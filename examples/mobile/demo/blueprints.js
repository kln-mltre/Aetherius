/**
 * The Blueprints the demo ships with — imported as JSON, from `examples/`.
 *
 * They are the *same files* `aetherius run` plays on a machine, not copies: bundling anything else
 * would make this app prove something other than what it exists to prove. Delivering Blueprints
 * properly (a bundled asset, a download, a cache, a kill switch) is milestone 3-F; until then, an
 * import is honest and enough.
 */

import deviceIpCheck from "../device-ip-check.blueprint.json";
import sessionCookieProbe from "../session-cookie-probe.blueprint.json";
import jsonplaceholderFlow from "../../vector/jsonplaceholder-flow.blueprint.json";
import quotesWatch from "../../vector/quotes-watch.blueprint.json";

export const BLUEPRINTS = [
  {
    key: "device-ip-check",
    title: "Device IP check",
    hint: "Quelle IP a emis la requete ? Elle doit differer de celle du poste de dev.",
    blueprint: deviceIpCheck,
  },
  {
    key: "jsonplaceholder-flow",
    title: "Flux : if + for_each",
    hint: "Extraction JSONPath, branche conditionnelle, une iteration par utilisateur.",
    blueprint: jsonplaceholderFlow,
  },
  {
    key: "quotes-watch",
    title: "Scraping HTML",
    hint: "Extraction CSS hors navigateur, sur une page reelle.",
    blueprint: quotesWatch,
  },
  {
    key: "session-cookie-probe",
    title: "Session : le magasin de la plateforme",
    hint: "carried doit valoir true ici, et false sous Node : c'est l'asymetrie assumee.",
    blueprint: sessionCookieProbe,
  },
];
