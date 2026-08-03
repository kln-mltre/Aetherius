/**
 * `useAetheriusRun` — le flux d'evenements branche sur un ecran.
 *
 * Les evenements du moteur portent deja tout ce qu'il faut pour afficher une progression etape par
 * etape : c'est precisement ce qu'une application reimplemente aujourd'hui a la main, avec des etats
 * ad hoc qui derivent de ce que le moteur sait deja. Ce hook est le raccourci, et il tient en une
 * page — s'il fallait plus, ce serait le signe que le flux n'est pas assez expressif.
 *
 * Il ne cache rien : `result` est le `Result` du moteur, `failure` la traduction `describeFailure`,
 * `events` la liste brute. Une application qui veut son propre etat appelle `client.run` directement.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { describeFailure, type Failure, type Result, type RunEvent } from "@aetherius/engine";

import type { Aetherius, BlueprintSource, RunOptions } from "../aetherius.js";

export interface RunState {
  readonly running: boolean;
  /** Les evenements du run courant, dans l'ordre d'emission. */
  readonly events: readonly RunEvent[];
  /** Le `Result`, quand le run est alle au bout — y compris s'il a echoue. */
  readonly result: Result | undefined;
  /** L'echec traduit, des deux canaux (`Result` en echec ou exception levee). */
  readonly failure: Failure | undefined;
  /** Lance un run. Ne leve pas : l'echec passe par `failure`, ce qu'attend un gestionnaire d'UI. */
  readonly run: (source: BlueprintSource, options?: RunOptions) => Promise<void>;
  /** Annule le run en cours. */
  readonly cancel: () => void;
  readonly reset: () => void;
}

export function useAetheriusRun(client: Aetherius): RunState {
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<readonly RunEvent[]>([]);
  const [result, setResult] = useState<Result | undefined>(undefined);
  const [failure, setFailure] = useState<Failure | undefined>(undefined);

  // L'identifiant vit dans une ref : `cancel` doit atteindre le run en cours sans dependre d'un
  // rendu, et un etat perime annulerait le mauvais run — ou aucun.
  const current = useRef<string | undefined>(undefined);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      // Quitter l'ecran annule le run : sans cela, une WebView cachee survit a l'ecran qui l'a
      // demandee, et un telephone la porte jusqu'a ce que l'application meure.
      if (current.current !== undefined) client.cancel(current.current);
    };
  }, [client]);

  const reset = useCallback(() => {
    setEvents([]);
    setResult(undefined);
    setFailure(undefined);
  }, []);

  const run = useCallback(
    async (source: BlueprintSource, options: RunOptions = {}) => {
      // Un suffixe aleatoire, pas seulement l'horloge : deux runs lances dans la meme milliseconde
      // partageraient leur identifiant, et `cancel` annulerait le mauvais.
      const runId = options.runId ?? `run-${Date.now().toString(36)}-${randomSuffix()}`;
      current.current = runId;
      setRunning(true);
      reset();

      const collected: RunEvent[] = [];
      try {
        const outcome = await client.run(source, {
          ...options,
          runId,
          onEvent: (event) => {
            collected.push(event);
            options.onEvent?.(event);
            if (mounted.current) setEvents([...collected]);
          },
        });
        if (!mounted.current) return;
        setResult(outcome);
        setFailure(describeFailure(outcome));
      } catch (error) {
        if (!mounted.current) return;
        // Un Blueprint refuse, une WebView absente, un bug du moteur : la meme traduction que pour
        // un run echoue, pour qu'un ecran n'ait qu'un chemin d'affichage.
        setFailure(describeFailure(error));
      } finally {
        current.current = undefined;
        if (mounted.current) setRunning(false);
      }
    },
    [client, reset],
  );

  const cancel = useCallback(() => {
    if (current.current !== undefined) client.cancel(current.current);
  }, [client]);

  return { running, events, result, failure, run, cancel, reset };
}

function randomSuffix(): string {
  return Math.floor(Math.random() * 0x1000000)
    .toString(36)
    .padStart(5, "0");
}
