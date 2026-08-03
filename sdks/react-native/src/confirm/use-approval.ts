/**
 * `useApprovalRequest` — la primitive de la surface de confirmation.
 *
 * C'est ici que s'arrete une application qui veut son propre design : le hook rend la demande en
 * attente et deux fonctions pour y repondre, rien de plus. `<AetheriusConfirm />` n'est qu'un
 * habillage par defaut construit dessus.
 */

import { useCallback, useEffect, useState } from "react";

import type { ApprovalRequest } from "@aetherius/engine";

import { defaultConfirmGateway, type ConfirmGateway } from "./gateway.js";

export interface ApprovalControls {
  /** La demande en attente, ou `undefined` quand aucun run n'attend de decision. */
  readonly request: ApprovalRequest | undefined;
  /** Approuve, avec une valeur optionnelle (le cas « fournir une valeur »). */
  readonly approve: (value?: unknown) => void;
  readonly reject: () => void;
}

export function useApprovalRequest(gateway: ConfirmGateway = defaultConfirmGateway): ApprovalControls {
  const [request, setRequest] = useState<ApprovalRequest | undefined>(() => gateway.current());

  useEffect(() => gateway.subscribe(setRequest), [gateway]);

  const decide = useCallback(
    (approved: boolean, value?: unknown) => {
      // `decidedBy` remonte dans `{{ steps.<id>.decided_by }}` et dans l'evenement
      // `input_provided` : c'est la trace de *qui* a repondu, la ou Python ecrit
      // console/api/cli/notification.
      gateway.decide({ approved, value, decidedBy: "modal" });
    },
    [gateway],
  );

  return {
    request,
    approve: useCallback((value?: unknown) => decide(true, value), [decide]),
    reject: useCallback(() => decide(false), [decide]),
  };
}
