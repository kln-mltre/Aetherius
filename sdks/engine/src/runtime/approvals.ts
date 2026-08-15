/**
 * Rendez-vous human-in-the-loop, miroir de `src/aetherius/core/runtime/approvals.py`.
 *
 * L'action `confirm` gare le run jusqu'a ce qu'un humain decide. Cote Python, le worker bloque sur
 * un `threading.Event` ; ici il attend une promesse — rien ne peut bloquer la boucle JS. La
 * semantique observable est la meme : le run reste **vivant et gare**, son statut ne change pas, et
 * le delai est **obligatoire**, donc un run gare finit toujours par etre libere.
 *
 * Une passerelle absente du `RunContext` veut dire *non surveille* : `confirm` applique sa politique
 * `on_timeout` tout de suite, sans jamais garer. C'est ce que fait une bibliotheque sans surface.
 *
 * Le jeton lie une decision a sa demande **dans le processus** — il n'y a pas de daemon a l'autre
 * bout, donc il ne porte aucune autorite reseau. Il empeche une surface de resoudre le mauvais run,
 * et une decision perimee de reveiller le suivant.
 */

import type { AbortSignalLike } from "../http.js";

export interface ApprovalRequest {
  readonly runId: string;
  /** Jeton opaque exige pour resoudre : lie a `runId`, mint a l'ouverture. */
  readonly token: string;
  readonly message: string;
  readonly stepId?: string;
  readonly title?: string;
  readonly timeoutMs: number;
}

export interface Decision {
  readonly approved: boolean;
  /** Valeur fournie par l'humain, le cas echeant (le cas « saisis une valeur »). */
  readonly value?: unknown;
  /** Quelle surface a repondu (`modal`/`timeout`/…), pour la trace. */
  readonly decidedBy?: string;
}

export function createApprovalRequest(
  runId: string,
  message: string,
  options: { stepId?: string; title?: string; timeoutMs: number },
): ApprovalRequest {
  return {
    runId,
    token: newToken(),
    message,
    ...(options.stepId !== undefined ? { stepId: options.stepId } : {}),
    ...(options.title !== undefined ? { title: options.title } : {}),
    timeoutMs: options.timeoutMs,
  };
}

/**
 * Le point d'attente d'un worker gare.
 *
 * Deux ecrivains possibles, et le **premier gagne** : la decision humaine, ou l'echeance. Une
 * seconde decision est un non-evenement, jamais un double effet.
 *
 * L'echeance est tenue **en heure murale**, pas seulement par un minuteur. Sur un telephone, une
 * application mise en arriere-plan voit ses minuteurs geles : au retour, le minuteur se declenche en
 * retard et une decision tapee entre-temps arriverait *apres* l'expiration. Comparer l'horloge au
 * moment de resoudre est ce qui rend « une decision arrivee apres l'expiration est ignoree » vrai
 * sur un appareil, et pas seulement en test.
 */
export class Rendezvous {
  private settled = false;
  private decision: Decision | null = null;
  private wake: (() => void) | undefined;
  private readonly deadline: number;
  private timedOut = false;

  constructor(readonly request: ApprovalRequest) {
    this.deadline = Date.now() + request.timeoutMs;
  }

  /**
   * L'echeance est-elle passee ? Une surface s'en sert pour cesser d'afficher sa demande.
   *
   * Le minuteur fait foi **en plus** de l'horloge : un `setTimeout` peut se declencher une fraction
   * de milliseconde avant que `Date.now()` n'atteigne l'echeance, et l'attente rendait alors `null`
   * en annoncant `expired: false` — deux reponses contradictoires sur le meme rendez-vous.
   */
  get expired(): boolean {
    return this.timedOut || Date.now() >= this.deadline;
  }

  /**
   * Attend la decision. Rend `null` a l'expiration.
   *
   * *signal* est celui du run : une annulation libere le worker gare au lieu d'attendre l'echeance —
   * sans quoi quitter un ecran laisserait un run parque jusqu'a cinq minutes.
   */
  wait(signal?: AbortSignalLike): Promise<Decision | null> {
    if (this.settled) return Promise.resolve(this.decision);

    return new Promise<Decision | null>((resolve) => {
      let timer: ReturnType<typeof setTimeout> | undefined;
      const finish = (): void => {
        if (timer !== undefined) clearTimeout(timer);
        signal?.removeEventListener?.("abort", onAbort);
        this.wake = undefined;
        resolve(this.decision);
      };
      const onAbort = (): void => {
        // L'annulation ne decide rien : elle libere l'attente, et l'executeur levera au step suivant.
        this.settled = true;
        finish();
      };

      this.wake = finish;
      const remaining = Math.max(0, this.deadline - Date.now());
      timer = setTimeout(() => {
        this.timedOut = true;
        this.settled = true;
        finish();
      }, remaining);

      if (signal?.aborted === true) onAbort();
      else signal?.addEventListener?.("abort", onAbort);
    });
  }

  /** Livre une decision. Rend `false` si le rendez-vous est deja resolu ou expire. */
  resolve(decision: Decision): boolean {
    if (this.settled || this.expired) return false;
    this.settled = true;
    this.decision = decision;
    this.wake?.();
    return true;
  }
}

/**
 * Le canal de decision qu'un run consulte pour ses steps `confirm`.
 *
 * Interface, et pas classe concrete, parce qu'une application peut vouloir la sienne : biometrie,
 * file d'attente, decision differee. Le moteur ne connait que ces trois methodes.
 */
export interface ApprovalGateway {
  open(request: ApprovalRequest): Rendezvous;
  close(request: ApprovalRequest): void;
  /** Signale le worker gare de *runId*. Rend `false` pour un run inconnu ou un jeton faux. */
  resolve(runId: string, token: string, decision: Decision): boolean;
}

/**
 * Registre en memoire indexe par `runId`, la passerelle par defaut.
 *
 * Un run ne gare qu'un `confirm` a la fois : un emplacement par run suffit. `@aetherius/react-native`
 * en derive sa passerelle observable, celle qu'un modal monte ecoute.
 */
export class ApprovalRegistry implements ApprovalGateway {
  private readonly pending = new Map<string, Rendezvous>();

  open(request: ApprovalRequest): Rendezvous {
    const rendezvous = new Rendezvous(request);
    this.pending.set(request.runId, rendezvous);
    return rendezvous;
  }

  close(request: ApprovalRequest): void {
    const current = this.pending.get(request.runId);
    if (current !== undefined && current.request.token === request.token) {
      this.pending.delete(request.runId);
    }
  }

  resolve(runId: string, token: string, decision: Decision): boolean {
    const rendezvous = this.pending.get(runId);
    // Le controle du jeton *est* l'autorisation : un jeton perime ou forge ne resout rien.
    if (rendezvous === undefined || rendezvous.request.token !== token) return false;
    return rendezvous.resolve(decision);
  }

  /** La demande en attente pour *runId*, s'il y en a une. */
  request(runId: string): ApprovalRequest | undefined {
    return this.pending.get(runId)?.request;
  }
}

interface CryptoLike {
  getRandomValues?: (array: Uint8Array) => Uint8Array;
}

/**
 * 32 caracteres hexadecimaux, tires du generateur de l'hote quand il en a un.
 *
 * Meme posture que `newRunId` : `crypto` n'est pas garanti sur un moteur JS mobile, donc le repli est
 * explicite plutot que suppose. Le jeton corrige une erreur de programmation (resoudre le mauvais
 * run), il ne protege pas d'un attaquant : il ne quitte jamais le processus.
 */
function newToken(): string {
  const host = (globalThis as { crypto?: CryptoLike }).crypto;
  const bytes = new Uint8Array(16);
  if (host?.getRandomValues !== undefined) host.getRandomValues(bytes);
  else for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);

  let out = "";
  for (const byte of bytes) out += byte.toString(16).padStart(2, "0");
  return out;
}
