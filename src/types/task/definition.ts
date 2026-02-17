// Task characteristics, definition, objective, result (§3, §4.1, §4.8)

export type Complexity = "trivial" | "simple" | "moderate" | "complex" | "extreme";
export type Criticality = "negligible" | "low" | "medium" | "high" | "critical";
export type Uncertainty = "deterministic" | "low" | "moderate" | "high" | "chaotic";
export type Verifiability = "exact" | "measurable" | "assessable" | "subjective" | "unverifiable";
export type Reversibility = "fully_reversible" | "partially_reversible" | "irreversible";
export type Granularity = "fine" | "coarse";

export interface TaskCharacteristics {
  complexity: Complexity;
  criticality: Criticality;
  uncertainty: Uncertainty;
  verifiability: Verifiability;
  reversibility: Reversibility;
  estimatedDuration?: number;
  estimatedCost?: number;
  resourceRequirements?: string[];
  constraints?: TaskConstraint[];
  contextuality?: number;
  subjectivity?: number;
  granularity?: Granularity;
}

export interface TaskConstraint {
  type: "temporal" | "resource" | "dependency" | "permission" | "quality" | "domain";
  description: string;
  hard: boolean;
  value?: unknown;
}

export type TaskStatus =
  | "pending"
  | "assigned"
  | "in_progress"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled"
  | "delegated";

export type TaskPriority = "lowest" | "low" | "normal" | "high" | "critical";

export interface Task {
  id: string;
  description: string;
  objective: TaskObjective;
  characteristics: TaskCharacteristics;
  priority: TaskPriority;
  status: TaskStatus;
  parentId?: string;
  subtaskIds: string[];
  dependencyIds: string[];
  contractId?: string;
  assigneeId?: string;
  delegatorId?: string;
  requiredPermissions: string[];
  createdAt: number;
  updatedAt: number;
  startedAt?: number;
  completedAt?: number;
  deadline?: number;
  result?: TaskResult;
  tags: string[];
  assigneeType?: "human" | "ai";
}

export interface TaskObjective {
  expectedOutput: string;
  successCriteria: SuccessCriterion[];
  verificationMethod: VerificationMethod;
}

export interface SuccessCriterion {
  metric: string;
  operator: "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "contains" | "matches" | "custom";
  target: unknown;
  weight: number;
}

export type VerificationMethod =
  | "direct_inspection"
  | "output_validation"
  | "third_party_audit"
  | "consensus"
  | "cryptographic_proof"
  | "delegator_review"
  | "automated_test";

export interface TaskResult {
  success: boolean;
  output: unknown;
  scores: Record<string, number>;
  verification?: VerificationRecord;
  executionTime: number;
  tokensUsed?: number;
  cost?: number;
  error?: string;
}

export interface VerificationRecord {
  method: VerificationMethod;
  verified: boolean;
  verifierId?: string;
  timestamp: number;
  evidence?: unknown;
  confidence: number;
}

export type DecompositionStrategy =
  | "sequential"
  | "parallel"
  | "hierarchical"
  | "pipeline"
  | "map_reduce"
  | "conditional";

export interface DecompositionPlan {
  rootTaskId: string;
  strategy: DecompositionStrategy;
  subtasks: Task[];
  dependencyGraph: Record<string, string[]>;
  estimatedTotalCost?: number;
  estimatedTotalDuration?: number;
}
