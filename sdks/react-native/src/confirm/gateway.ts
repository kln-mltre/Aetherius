/**
 * La passerelle d'approbation d'une application mobile.
 *
 * Cote Python, il a fallu **quatre** surfaces pour poser une question a un humain — un modal de
 * Console, une invite de terminal, une route du daemon, et les boutons d'une notification. Sur un
 * telephone il y en a une seule, et elle est evidente : un modal. C'est ce qui rend `confirm` plus
 * naturel ici qu'ailleurs.
 *
 * Ce fichier n'est que la moitie « donnee » de cette surface : un registre observable. Un composant
 * monte s'y abonne et affiche ce qu'il annonce ; l'interface, elle, appartient a l'application.
 * Separer les deux est ce qui rend le rendez-vous testable sans moteur de rendu — et ce qui permet
 * a une application de brancher sa propre confirmation (biometrie, feuille du bas, ecran dedie)
 * sans reecrire la logique.
 */

import {
  ApprovalRegistry,
  type ApprovalRequest,
  type Decision,
  type Rendezvous,
} from "@aetherius/engine";

export type ApprovalListener = (request: ApprovalRequest | undefined) => void;

/**
 * Le journal de l'hote, lu a travers `globalThis` — meme posture que `timers.ts`.
 *
 * Ce paquet n'emprunte ni les types du DOM ni ceux de Node : `console` existe partout en pratique,
 * mais le declarer est ce qui empeche `process` ou `Buffer` de se glisser dans du code qui part sur
 * un telephone.
 */
const log = (globalThis as { console?: { warn(...args: unknown[]): void } }).console;

/**
 * Un `ApprovalRegistry` qui **annonce** ses demandes.
 *
 * Un seul emplacement visible a la fois : un run ne gare qu'un `confirm`, et deux runs qui garent
 * en meme temps sont deja refuses plus haut pour l'Act II (une seule WebView). Si deux runs
 * `vector` concurrents garent tous les deux, le second est affiche des que le premier est resolu —
 * la file est implicite et l'ordre d'arrivee, ce qui est le comportement qu'un utilisateur attend
 * d'un modal.
 */
export class ConfirmGateway extends ApprovalRegistry {
  private readonly listeners = new Set<ApprovalListener>();
  private readonly queue: ApprovalRequest[] = [];

  override open(request: ApprovalRequest): Rendezvous {
    // **Personne n'ecoute = run non surveille.** Un ecran qui n'a monte ni `<AetheriusConfirm />`
    // ni `useApprovalRequest` ne montrera jamais la question : garer cinq minutes devant lui serait
    // un blocage sans issue visible. On applique donc la politique `on_timeout` tout de suite —
    // refus par defaut —, exactement ce que fait un run de bibliotheque cote Python. La decision se
    // prend au moment ou la question est posee, le seul ou l'on sait qui ecoute.
    const effective = this.listeners.size > 0 ? request : { ...request, timeoutMs: 0 };
    const rendezvous = super.open(effective);
    this.queue.push(effective);
    this.announce();
    return rendezvous;
  }

  override close(request: ApprovalRequest): void {
    super.close(request);
    const index = this.queue.findIndex((pending) => pending.token === request.token);
    if (index !== -1) this.queue.splice(index, 1);
    this.announce();
  }

  /** La demande a afficher, ou `undefined` quand aucun run n'attend. */
  current(): ApprovalRequest | undefined {
    return this.queue[0];
  }

  /**
   * Repond a la demande courante. Rend `false` si elle a disparu entre-temps — un modal tape juste
   * apres l'expiration, exactement le cas que le jalon exige d'ignorer.
   */
  decide(decision: Decision): boolean {
    const request = this.current();
    if (request === undefined) return false;
    return this.resolve(request.runId, request.token, decision);
  }

  /** S'abonner. La valeur courante est livree tout de suite : un composant monte tard voit l'etat. */
  subscribe(listener: ApprovalListener): () => void {
    this.listeners.add(listener);
    this.deliver(listener, this.current());
    return () => {
      this.listeners.delete(listener);
    };
  }

  private announce(): void {
    const current = this.current();
    for (const listener of [...this.listeners]) this.deliver(listener, current);
  }

  /** Meme regle que le bus d'evenements : le bug d'un consommateur n'emporte jamais un run. */
  private deliver(listener: ApprovalListener, request: ApprovalRequest | undefined): void {
    try {
      listener(request);
    } catch (error) {
      log?.warn("[aetherius] approval listener threw", error);
    }
  }
}

/**
 * La passerelle par defaut, partagee par la facade et par `<AetheriusConfirm />`.
 *
 * Un emplacement au niveau module, pour la meme raison que l'hote WebView (`registry.ts`) : le
 * modal est un composant monte, sa vie appartient a l'arbre de l'application, pas a un run.
 */
export const defaultConfirmGateway = new ConfirmGateway();
