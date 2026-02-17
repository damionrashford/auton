export type DelegationErrorCode =
  | "DEPTH_EXCEEDED"
  | "UNAUTHORIZED_DELEGATION"
  | "PERMISSION_DENIED"
  | "CONTRACT_VIOLATED"
  | "BUDGET_EXCEEDED";

export class DelegationError extends Error {
  constructor(message: string, public readonly code: DelegationErrorCode) {
    super(message);
    this.name = "DelegationError";
  }
}
