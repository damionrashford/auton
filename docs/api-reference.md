# API Reference

Complete list of exported classes, types, and functions.

## Core

| Export | Type | Description |
|--------|------|-------------|
| `AIClient` | class | OpenAI-compatible HTTP client |
| `AIError` | class | HTTP/API error with status and body |
| `AgentLoop` | class | LLM execution engine with tools |
| `createAgentLoop` | function | Factory for AgentLoop |
| `DelegationChainManager` | class | Delegation chains, privilege attenuation |
| `generateId` | function | Unique ID generator |
| `DelegationError` | class | Delegation-specific errors |
| `DelegationExecutor` | class | Full orchestration pipeline |
| `shouldBypassDelegation` | function | Complexity floor check |
| `createDelegationFramework` | function | Pre-wired framework factory |

## Protocols

| Export | Type | Description |
|--------|------|-------------|
| `TaskDecomposer` | class | Task decomposition (AI or manual) |
| `TaskAssigner` | class | Task-to-agent assignment |
| `MultiObjectiveOptimizer` | class | Pareto optimization |
| `DELEGATION_OBJECTIVES` | const | Default optimization objectives |
| `AdaptiveCoordinator` | class | Trigger processing, replanning |
| `Monitor` | class | Task monitoring |
| `TrustReputationManager` | class | Trust ledger, reputation |
| `PermissionManager` | class | Permission policies, JIT granting |
| `TaskVerifier` | class | Result verification |
| `SecurityManager` | class | Threat detection |

## MCP

| Export | Type | Description |
|--------|------|-------------|
| `MCPClient` | class | MCP client |
| `connectWithAutoDetect` | function | Connect with auto transport detection |
| `MCPStreamableHTTPTransport` | class | Streamable HTTP transport |
| `MCPStdioTransport` | class | stdio transport |
| `MCPSSETransport` | class | SSE transport |
| `MCPTransport` | interface | Transport contract |

## AI Types

`SystemMessage`, `UserMessage`, `AssistantMessage`, `ToolMessage`, `ChatMessage`, `ToolDefinition`, `ToolCall`, `ToolChoice`, `ResponseFormat`, `ChatCompletionRequest`, `ChatCompletionResponse`, `ChatCompletionChunk`, `UsageStats`, `AIClientConfig`, etc.

## Task Types

`Task`, `TaskObjective`, `SuccessCriterion`, `VerificationMethod`, `TaskResult`, `VerificationRecord`, `TaskCharacteristics`, `DecompositionPlan`, `DecompositionStrategy`, `DelegationContract`, `ResourceBudget`, `MonitoringMode`, `AutonomyLevel`, `Permission`, `PermissionCondition`, etc.

## Agent Types

`AgentProfile`, `AgentCapability`, `ModelConfig`, `ReputationMetrics`, `DomainScore`, `DelegationEdge`, `DelegationChainInfo`, etc.

## Protocol Types

`AssignmentScore`, `AssignmentWeights`, `OptimizationObjective`, `Solution`, `OptimizationResult`, `CoordinationTrigger`, `CoordinationAction`, `MonitoringEvent`, `TaskMetrics`, `TrustLedgerEntry`, `TrustEndorsement`, `PermissionRequest`, `PermissionDecision`, `VerificationResult`, `ThreatDetection`, `SecurityRule`, etc.

## MCP Types

`MCPTool`, `MCPCallToolResult`, `MCPResource`, `MCPReadResourceResult`, `MCPPrompt`, `MCPGetPromptResult`, `MCPToolResultContent`

---

For detailed type definitions, see [Types](./types.md).
