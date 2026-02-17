export interface MonitoringEvent {
  id: string;
  taskId: string;
  agentId: string;
  type: MonitoringEventType;
  timestamp: number;
  data: Record<string, unknown>;
}

export type MonitoringEventType =
  | "task_started"
  | "task_progress"
  | "task_completed"
  | "task_failed"
  | "tool_called"
  | "delegation_created"
  | "token_usage"
  | "cost_incurred"
  | "error_occurred"
  | "heartbeat"
  | "checkpoint";

export interface TaskMetrics {
  taskId: string;
  agentId: string;
  elapsedTime: number;
  tokensUsed: number;
  costIncurred: number;
  toolCalls: number;
  errorCount: number;
  delegationCount: number;
  progress: number;
  lastHeartbeat: number;
  events: MonitoringEvent[];
}

export interface MonitoringConfig {
  target?: "outcome" | "process";
  observability?: "direct" | "indirect";
  transparency?: "black_box" | "white_box";
  privacy?: "full" | "cryptographic";
  topology?: "direct" | "transitive";
}

export interface MonitoringThresholds {
  heartbeatTimeout: number;
  maxErrorRate: number;
  budgetWarningThreshold: number;
  budgetCriticalThreshold: number;
  minQualityScore: number;
  maxExecutionTime: number;
}

export const DEFAULT_THRESHOLDS: MonitoringThresholds = {
  heartbeatTimeout: 30_000,
  maxErrorRate: 5,
  budgetWarningThreshold: 0.8,
  budgetCriticalThreshold: 0.95,
  minQualityScore: 0.5,
  maxExecutionTime: 600_000,
};
