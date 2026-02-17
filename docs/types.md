# Type Definitions

Core domain types used across the framework.

## Task

### Task

```typescript
interface Task {
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
```

### Task Characteristics

- `complexity` — trivial | simple | moderate | complex | extreme
- `criticality` — negligible | low | medium | high | critical
- `uncertainty` — deterministic | low | moderate | high | chaotic
- `verifiability` — exact | measurable | assessable | subjective | unverifiable
- `reversibility` — fully_reversible | partially_reversible | irreversible
- `estimatedDuration`, `estimatedCost`, `constraints`, `contextuality`, `subjectivity`, `granularity`

### Task Objective

```typescript
interface TaskObjective {
  expectedOutput: string;
  successCriteria: SuccessCriterion[];
  verificationMethod: VerificationMethod;
}

interface SuccessCriterion {
  metric: string;
  operator: "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "contains" | "matches" | "custom";
  target: unknown;
  weight: number;
}
```

### Task Result

```typescript
interface TaskResult {
  success: boolean;
  output: unknown;
  scores: Record<string, number>;
  verification?: VerificationRecord;
  executionTime: number;
  tokensUsed?: number;
  cost?: number;
  error?: string;
}
```

## Agent

### Agent Profile

```typescript
interface AgentProfile {
  id: string;
  name: string;
  type: "human" | "ai";
  capabilities: AgentCapability[];
  tools: ToolDefinition[];
  modelConfig?: ModelConfig;
  basePermissions: Permission[];
  maxAutonomyLevel: AutonomyLevel;
  preferredMonitoringMode: MonitoringMode;
  trustScore: number;
  reputation: ReputationMetrics;
  canDelegate: boolean;
  maxDelegationDepth: number;
  maxConcurrentDelegatees?: number;
  domains: string[];
  rateLimits?: RateLimits;
  status: AgentStatus;
  metadata: Record<string, unknown>;
}
```

### Agent Capability

```typescript
interface AgentCapability {
  name: string;
  proficiency: number;  // 0-1
  domains?: string[];
  maxComplexity?: number;
  successRate?: number;
  avgExecutionTime?: number;
}
```

### Model Config

```typescript
interface ModelConfig {
  model: string;
  baseURL: string;
  apiKey: string;
  temperature?: number;
  systemPrompt?: string;
  maxTokens?: number;
  stream?: boolean;
  headers?: Record<string, string>;
}
```

## Delegation Contract

```typescript
interface DelegationContract {
  id: string;
  taskId: string;
  delegatorId: string;
  delegateeId: string;
  deliverables: string[];
  acceptanceCriteria: SuccessCriterion[];
  grantedPermissions: Permission[];
  budget: ResourceBudget;
  monitoringMode: MonitoringMode;
  autonomyLevel: AutonomyLevel;
  deadline?: number;
  escalationPolicy: EscalationPolicy;
  createdAt: number;
  status: "active" | "completed" | "violated" | "cancelled";
  compensationTerms?: string;
  renegotiationClause?: boolean;
  privacyClauses?: Record<string, unknown>;
}

interface ResourceBudget {
  maxTokens?: number;
  maxCost?: number;
  maxDuration?: number;
  maxApiCalls?: number;
  maxDelegationDepth?: number;
}
```

## Permission

```typescript
interface Permission {
  id: string;
  resource: string;
  actions: string[];
  conditions?: PermissionCondition[];
  expiresAt?: number;
  delegatable: boolean;
  grantChain: string[];
}

interface PermissionCondition {
  type: "time_window" | "rate_limit" | "approval_required" | "context_match" | "semantic";
  parameters: Record<string, unknown>;
}
```

## Autonomy & Monitoring

- **AutonomyLevel** — `atomic_execution` | `bounded_autonomy` | `guided_autonomy` | `open_delegation`
- **MonitoringMode** — `continuous` | `periodic` | `event_triggered` | `on_completion`

## Decomposition

- **DecompositionStrategy** — `sequential` | `parallel` | `hierarchical` | `pipeline` | `map_reduce` | `conditional`
- **DecompositionPlan** — `rootTaskId`, `strategy`, `subtasks`, `dependencyGraph`, `estimatedTotalCost`, `estimatedTotalDuration`

---

For protocol-specific types, see the respective protocol docs.
