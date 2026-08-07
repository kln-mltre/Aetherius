/**
 * Chercher un fichier de livraison, avec un delai et une borne de taille.
 *
 * Rien d'ambitieux : ce jalon livre le **client** et le **format**, pas une infrastructure. Un depot
 * de fichiers statiques derriere un CDN suffit, et c'est un motif deja eprouve pour du contenu
 * editorial d'application.
 *
 * Trois precautions qui n'en sont pas : `fetch` n'a pas de delai propre (il est construit avec
 * `AbortController`, comme dans le client de l'Act I), un corps sans borne serait une facon simple
 * de faire tomber une application depuis le reseau, et **le cache HTTP de la plateforme est
 * contourne** (voir ci-dessous).
 */

import { hostAbortController, type FetchLike } from "@aetherius/engine";

import { startTimer, stopTimer } from "../timers.js";

/**
 * Ce qu'on demande a tous les intermediaires de ne pas faire.
 *
 * Le manifeste est le **plan de controle** de la livraison : il porte l'interrupteur d'arret. Une
 * reponse servie depuis un cache veut donc dire un interrupteur qui n'arrete rien et une correction
 * qui n'arrive pas — pendant une duree que personne ne controle.
 */
const NO_CACHE = { "Cache-Control": "no-cache, no-store", Pragma: "no-cache" };

/**
 * Rend l'URL unique pour la plateforme.
 *
 * Les en-tetes ci-dessus sont la bonne reponse HTTP ; elles ne suffisent pas. `fetch` passe par
 * `NSURLCache` sur iOS et par le cache OkHttp sur Android, tous deux indexes par URL, et un hote
 * statique qui ne renvoie qu'un `Last-Modified` (`python3 -m http.server`, un depot brut) leur
 * laisse le droit d'inventer une **fraicheur heuristique**. Trouve sur un appareil, et le symptome
 * ne ressemblait pas a sa cause : le serveur coupe, l'application repondait « manifeste lu ».
 *
 * Le prix est connu et assume : chaque rafraichissement traverse le cache de bord d'un CDN. Pour un
 * document de quelques centaines d'octets qui decide d'un retour arriere, c'est le bon echange.
 *
 * L'horloge seule ne suffit pas a rendre le jeton unique : deux requetes emises dans la meme
 * milliseconde produisaient la MEME URL, donc le contournement cessait de contourner. Sur un
 * appareil le cas ne se voyait pas (deux rafraichissements sont separes par un geste humain), mais
 * un rafraichissement en boucle ou une resolution servie depuis un cache local le rencontre. Un
 * compteur monotone est ajoute au temps : le jeton reste court, lisible dans un journal de serveur,
 * et unique par construction plutot que par chance.
 */
let sequence = 0;

function uncached(url: string): string {
  sequence += 1;
  const token = `${Date.now().toString(36)}-${sequence.toString(36)}`;
  return `${url}${url.includes("?") ? "&" : "?"}_aeth=${token}`;
}

/**
 * Le texte servi par *url*.
 *
 * @throws {Error} transport, statut non 2xx, ou corps au-dela de la borne. L'appelant
 * (`refresh`) en fait une **raison**, jamais une exception qui remonterait a l'application.
 */
export async function fetchText(
  fetcher: FetchLike,
  url: string,
  timeoutMs: number,
  maxBytes: number,
): Promise<string> {
  const Controller = hostAbortController();
  const controller = Controller === undefined ? undefined : new Controller();
  // Un hote sans `AbortController` n'a **pas** de delai plutot qu'un delai qui ne se declenche
  // jamais : meme posture que `VectorClient`.
  const timer =
    controller === undefined ? undefined : startTimer(() => controller.abort(), timeoutMs);

  try {
    const response = await fetcher(uncached(url), {
      method: "GET",
      headers: NO_CACHE,
      redirect: "follow",
      ...(controller !== undefined ? { signal: controller.signal } : {}),
    });
    if (response.status < 200 || response.status >= 300) {
      throw new Error(`HTTP ${response.status} for ${url}`);
    }

    const announced = Number(response.headers.get("content-length") ?? Number.NaN);
    if (Number.isFinite(announced) && announced > maxBytes) {
      throw new Error(`${url} announces ${announced} bytes, over the ${maxBytes} limit`);
    }

    const text = await response.text();
    // La borne compte des caracteres, pas des octets : c'est une **borne**, pas une comptabilite.
    if (text.length > maxBytes) {
      throw new Error(`${url} is larger than the ${maxBytes} limit`);
    }
    return text;
  } finally {
    if (timer !== undefined) stopTimer(timer);
  }
}
