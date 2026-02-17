// ============================================================================
// Intelligent AI Delegation Framework
// TypeScript, zero dependencies, OpenAI-compatible
// Based on "Intelligent AI Delegation" (Tomasev, Franklin, Osindero, 2026)
// ============================================================================

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type {
  SystemMessage,
  UserMessage,
  AssistantMessage,
  ToolMessage,
  ChatMessage,
  TextContentPart,
  ImageContentPart,
  ContentPart,
  FunctionDefinition,
  ToolDefinition,
  ToolCall,
  ToolChoice,
  JsonSchema,
  ResponseFormat,
  ChatCompletionRequest,
  ChatCompletionChoice,
  FinishReason,
  ChatCompletionResponse,
  UsageStats,
  LogprobsResult,
  LogprobToken,
  ChatCompletionChunk,
  ChatCompletionChunkChoice,
  DeltaMessage,
  DeltaToolCall,
  AIClientConfig,
} from "@/types/ai.js";

export type {
  Complexity,
  Criticality,
  Uncertainty,
  Verifiability,
  Reversibility,
  TaskCharacteristics,
  TaskConstraint,
  TaskStatus,
  TaskPriority,
  Task,
  TaskObjective,
  SuccessCriterion,
  VerificationMethod,
  TaskResult,
  VerificationRecord,
  Granularity,
  DecompositionStrategy,
  DecompositionPlan,
  DelegationContract,
  ResourceBudget,
  MonitoringMode,
  AutonomyLevel,
  EscalationPolicy,
  EscalationTrigger,
  Permission,
  PermissionCondition,
} from "@/types/task/index.js";

export type {
  AgentType,
  AgentProfile,
  AgentCapability,
  ModelConfig,
  ReputationMetrics,
  DomainScore,
  RateLimits,
  AgentRegistry,
  DelegationEdge,
  DelegationChainInfo,
} from "@/types/agent.js";

// ---------------------------------------------------------------------------
// Core
// ---------------------------------------------------------------------------

export { AIClient, AIError } from "@/core/ai/index.js";
export {
  DelegationChainManager,
  generateId,
  DelegationError,
  type DelegationErrorCode,
} from "@/core/delegation/index.js";
export {
  AgentLoop,
  createAgentLoop,
  type ToolHandler,
  type ToolExecutor,
  type AgentLoopConfig,
  type CreateAgentLoopOptions,
} from "@/core/agent/index.js";
export {
  DelegationExecutor,
  shouldBypassDelegation,
  type ComplexityFloorConfig,
  type DelegationExecutorConfig,
} from "@/core/executor.js";

// ---------------------------------------------------------------------------
// Protocols
// ---------------------------------------------------------------------------

export { TaskDecomposer } from "@/protocols/taskdecomposition/index.js";
export {
  TaskAssigner,
  type AssignmentScore,
  type AssignmentWeights,
} from "@/protocols/taskassignment/index.js";
export {
  MultiObjectiveOptimizer,
  DELEGATION_OBJECTIVES,
  type OptimizationObjective,
  type Solution,
  type OptimizationResult,
} from "@/protocols/optimization/index.js";
export {
  AdaptiveCoordinator,
  type ExternalTriggerType,
  type InternalTriggerType,
  type TriggerType,
  type CoordinationTrigger,
  type CoordinationAction,
  type CoordinationRule,
  type CoordinationContext,
  type CoordinatorStabilityConfig,
} from "@/protocols/coordination/index.js";
export {
  Monitor,
  type MonitoringEvent,
  type MonitoringEventType,
  type TaskMetrics,
  type MonitoringThresholds,
  type MonitoringConfig,
} from "@/protocols/monitoring/index.js";
export {
  TrustReputationManager,
  type TrustLedgerEntry,
  type TrustEndorsement,
  type TrustConfig,
} from "@/protocols/trust/index.js";
export {
  PermissionManager,
  type PermissionRequest,
  type PermissionDecision,
  type PermissionPolicy,
  type PermissionAuditEntry,
} from "@/protocols/permissions/index.js";
export {
  TaskVerifier,
  type VerificationResult,
  type VerificationDetail,
  type ChildAttestation,
} from "@/protocols/verification/index.js";
export {
  SecurityManager,
  type ThreatCategory,
  type DelegateeThreat,
  type DelegatorThreat,
  type EcosystemThreat,
  type ThreatType,
  type ThreatDetection,
  type SecurityRule,
  type SecurityContext,
  type ToolCallRecord,
  type DelegationRecord,
  type ResourceUsageRecord,
} from "@/protocols/security/index.js";

// ---------------------------------------------------------------------------
// MCP (Model Context Protocol)
// ---------------------------------------------------------------------------

export {
  MCPClient,
  connectWithAutoDetect,
  type MCPClientConfig,
} from "@/mcp/client.js";
export {
  MCPStreamableHTTPTransport,
  MCPStdioTransport,
  MCPSSETransport,
  type MCPStreamableHTTPTransportOptions,
  type MCPStdioTransportConfig,
  type MCPSSETransportOptions,
} from "@/mcp/index.js";
export type { MCPTransport } from "@/mcp/transportinterface.js";
export type {
  MCPTool,
  MCPCallToolResult,
  MCPResource,
  MCPReadResourceResult,
  MCPPrompt,
  MCPGetPromptResult,
  MCPToolResultContent,
} from "@/mcp/types.js";

export {
  createDelegationFramework,
  type DelegationFrameworkConfig,
} from "@/factory.js";
