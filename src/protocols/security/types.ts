import type { Task } from "@/types/task/index.js";
import type { AgentProfile } from "@/types/agent.js";

export type ThreatCategory = "malicious_delegatee" | "malicious_delegator" | "ecosystem";

export type DelegateeThreat =
  | "data_exfiltration"
  | "data_poisoning"
  | "verification_subversion"
  | "resource_exhaustion"
  | "unauthorized_access"
  | "backdoor_implanting";

export type DelegatorThreat =
  | "harmful_delegation"
  | "vulnerability_probing"
  | "prompt_injection"
  | "model_extraction"
  | "reputation_sabotage";

export type EcosystemThreat =
  | "sybil_attack"
  | "collusion"
  | "agent_trap"
  | "agentic_virus"
  | "protocol_exploitation"
  | "cognitive_monoculture";

export type ThreatType = DelegateeThreat | DelegatorThreat | EcosystemThreat;

export interface ThreatDetection {
  id: string;
  threatType: ThreatType;
  category: ThreatCategory;
  severity: "low" | "medium" | "high" | "critical";
  agentId?: string;
  taskId?: string;
  description: string;
  evidence: unknown[];
  timestamp: number;
  mitigated: boolean;
}

export interface SecurityRule {
  id: string;
  name: string;
  description: string;
  detectsThreats: ThreatType[];
  check: (context: SecurityContext) => ThreatDetection | null;
  enabled: boolean;
}

export interface SecurityContext {
  task?: Task;
  agent?: AgentProfile;
  recentToolCalls: ToolCallRecord[];
  recentDelegations: DelegationRecord[];
  resourceUsage: ResourceUsageRecord;
  allAgents: AgentProfile[];
}

export interface ToolCallRecord {
  agentId: string;
  toolName: string;
  arguments: string;
  timestamp: number;
  taskId: string;
}

export interface DelegationRecord {
  delegatorId: string;
  delegateeId: string;
  taskId: string;
  timestamp: number;
}

export interface ResourceUsageRecord {
  agentId: string;
  tokensUsed: number;
  apiCalls: number;
  delegationsCreated: number;
  uniqueResourcesAccessed: Set<string>;
  timeWindow: number;
}
