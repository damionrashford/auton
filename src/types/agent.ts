// ============================================================================
// Agent Types — Based on §3 & §4.2 of "Intelligent AI Delegation"
// Agent profiles, capabilities, delegation relationships
// ============================================================================

import type { ToolDefinition } from "@/types/ai.js";
import type { Permission, AutonomyLevel, MonitoringMode } from "@/types/task/index.js";

// ---------------------------------------------------------------------------
// Agent Profile
// ---------------------------------------------------------------------------

export type AgentType = "human" | "ai";

export interface AgentProfile {
  id: string;
  name: string;
  type: AgentType;
  /** Agent's capabilities */
  capabilities: AgentCapability[];
  /** Tools available to this agent */
  tools: ToolDefinition[];
  /** Model configuration (for AI agents) */
  modelConfig?: ModelConfig;
  /** Base permissions this agent always has */
  basePermissions: Permission[];
  /** Maximum autonomy level this agent can be granted */
  maxAutonomyLevel: AutonomyLevel;
  /** Preferred monitoring mode when acting as delegatee */
  preferredMonitoringMode: MonitoringMode;
  /** Trust score (computed by Trust & Reputation protocol) */
  trustScore: number;
  /** Reputation metrics */
  reputation: ReputationMetrics;
  /** Whether this agent can delegate to others */
  canDelegate: boolean;
  /** Maximum delegation depth from this agent */
  maxDelegationDepth: number;
  /** Span of control — max concurrent delegatees this agent can oversee (§2.3) */
  maxConcurrentDelegatees?: number;
  /** Domain specializations */
  domains: string[];
  /** Rate limits */
  rateLimits?: RateLimits;
  /** Agent status */
  status: AgentStatus;
  metadata: Record<string, unknown>;
}

export type AgentStatus = "available" | "busy" | "offline" | "suspended" | "degraded";

// ---------------------------------------------------------------------------
// Capabilities
// ---------------------------------------------------------------------------

export interface AgentCapability {
  /** Capability identifier (e.g., "code_generation", "web_search", "data_analysis") */
  name: string;
  /** Proficiency level 0-1 */
  proficiency: number;
  /** Domains where this capability applies */
  domains?: string[];
  /** Maximum complexity this capability can handle */
  maxComplexity?: number;
  /** Historical success rate for this capability */
  successRate?: number;
  /** Average execution time (ms) */
  avgExecutionTime?: number;
}

// ---------------------------------------------------------------------------
// Model Configuration (for AI agents)
// ---------------------------------------------------------------------------

export interface ModelConfig {
  /** Model identifier (e.g., "gpt-4o", "grok-4-1-fast-reasoning") */
  model: string;
  /** Base URL for the OpenAI-compatible endpoint */
  baseURL: string;
  /** API key */
  apiKey: string;
  /** Default temperature */
  temperature?: number;
  /** System prompt */
  systemPrompt?: string;
  /** Max tokens per response */
  maxTokens?: number;
  /** Whether to use streaming */
  stream?: boolean;
  /** Additional headers */
  headers?: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Reputation Metrics (§4.6)
// ---------------------------------------------------------------------------

export interface ReputationMetrics {
  /** Total tasks completed */
  totalCompleted: number;
  /** Total tasks failed */
  totalFailed: number;
  /** Success rate (0-1) */
  successRate: number;
  /** Average quality score (0-1) */
  avgQuality: number;
  /** Average response time (ms) */
  avgResponseTime: number;
  /** On-time completion rate (0-1) */
  onTimeRate: number;
  /** Number of contract violations */
  violations: number;
  /** Trust score from web-of-trust (0-1) */
  webOfTrustScore: number;
  /** Behavioral consistency (0-1) */
  consistency: number;
  /** Per-domain performance */
  domainScores: Record<string, DomainScore>;
  /** Timestamp of last update */
  lastUpdated: number;
}

export interface DomainScore {
  domain: string;
  tasksCompleted: number;
  successRate: number;
  avgQuality: number;
}

// ---------------------------------------------------------------------------
// Rate Limits
// ---------------------------------------------------------------------------

export interface RateLimits {
  /** Max requests per minute */
  requestsPerMinute?: number;
  /** Max tokens per minute */
  tokensPerMinute?: number;
  /** Max concurrent tasks */
  maxConcurrentTasks?: number;
  /** Max cost per hour */
  maxCostPerHour?: number;
}

// ---------------------------------------------------------------------------
// Agent Registry
// ---------------------------------------------------------------------------

export interface AgentRegistry {
  agents: Map<string, AgentProfile>;
  /** Find agents matching required capabilities */
  findByCapability(capability: string, minProficiency?: number): AgentProfile[];
  /** Find agents available for a domain */
  findByDomain(domain: string): AgentProfile[];
  /** Get agent by ID */
  get(id: string): AgentProfile | undefined;
  /** Register a new agent */
  register(agent: AgentProfile): void;
  /** Update agent profile */
  update(id: string, updates: Partial<AgentProfile>): void;
  /** Remove an agent */
  remove(id: string): void;
}

// ---------------------------------------------------------------------------
// Delegation Relationship
// ---------------------------------------------------------------------------

export interface DelegationEdge {
  delegatorId: string;
  delegateeId: string;
  contractId: string;
  taskId: string;
  depth: number;
  timestamp: number;
  /** Mutual delegation — bidirectional relationship (§2.2) */
  bidirectional?: boolean;
}

export interface DelegationChainInfo {
  /** Root delegator (usually human) */
  rootDelegatorId: string;
  /** Ordered chain of delegation */
  chain: DelegationEdge[];
  /** Current depth */
  depth: number;
  /** Maximum allowed depth */
  maxDepth: number;
  /** Accumulated permissions (attenuated through chain) */
  effectivePermissions: Permission[];
}
