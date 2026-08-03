/** L'action `confirm` sur un telephone : un rendez-vous, une seule surface. Voir `gateway.ts`. */

export { ConfirmGateway, defaultConfirmGateway, type ApprovalListener } from "./gateway.js";
export { AetheriusConfirm, type AetheriusConfirmProps } from "./modal.js";
export { useApprovalRequest, type ApprovalControls } from "./use-approval.js";
