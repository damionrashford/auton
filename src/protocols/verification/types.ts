import type { VerificationRecord, VerificationMethod, SuccessCriterion } from "@/types/task/index.js";

export interface VerificationResult {
  verified: boolean;
  confidence: number;
  method: VerificationMethod;
  details: VerificationDetail[];
  overallScore: number;
  record: VerificationRecord;
}

export interface VerificationDetail {
  criterion: SuccessCriterion;
  passed: boolean;
  actualValue: unknown;
  score: number;
  message: string;
}

export interface ChildAttestation {
  taskId: string;
  delegateeId: string;
  verificationRecord: VerificationRecord;
  parentVerified: boolean;
}
