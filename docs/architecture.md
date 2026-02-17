# Architecture Overview

## Design Principles

The framework implements the **AUTON (Intelligent AI Delegation)** lifecycle from the paper ([arXiv:2602.11865](https://arxiv.org/abs/2602.11865)):

1. **Contract-first decomposition** — Every subtask has measurable success criteria before delegation
2. **Privilege attenuation** — Permissions narrow with each delegation hop; delegatees never gain more than delegators hold
3. **Adaptive coordination** — Monitor → Detect → Evaluate → Replan → Execute
4. **Trust calibration** — Immutable ledger, web-of-trust, behavioral metrics

## Delegation Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DELEGATION EXECUTOR                               │
├─────────────────────────────────────────────────────────────────────────┤
│  1. Complexity Floor     → Bypass full pipeline for trivial tasks        │
│  2. Task Decomposition   → Break into subtask DAG (AI or manual)        │
│  3. Task Assignment     → Match to agent (capability, trust, availability)│
│  4. Contract Creation   → Deliverables, budget, permissions             │
│  5. Delegation Chain    → Record edge, attenuate permissions            │
│  6. Agent Loop          → Execute with tools, monitoring, security       │
│  7. Verification        → Direct inspection, output validation, LLM     │
│  8. Trust Update        → Record completion in ledger                   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Map

| Layer | Components | Responsibility |
|-------|------------|----------------|
| **Core** | `AIClient`, `AgentLoop`, `DelegationChainManager`, `Executor` | Execution, chains, orchestration |
| **Protocols** | `TaskDecomposer`, `TaskAssigner`, `Monitor`, `TaskVerifier`, `TrustReputationManager`, `SecurityManager`, `AdaptiveCoordinator`, `PermissionManager`, `MultiObjectiveOptimizer` | Decomposition, assignment, monitoring, verification, trust, security, coordination, permissions, optimization |
| **Types** | `Task`, `AgentProfile`, `DelegationContract`, `Permission`, etc. | Domain models |
| **MCP** | `MCPClient`, transports (stdio, HTTP, SSE) | Model Context Protocol integration |

## Data Flow

```
Task → [Complexity Floor?] → Decompose → Assign → Contract → Delegate → Execute
                                                                          ↓
Result ← Verify ← Trust Update ← Agent Loop (LLM + tools)
```

- **Monitor** and **SecurityManager** emit triggers (e.g., budget overrun, threat) → **AdaptiveCoordinator** processes them → replan, reassign, escalate
- **TrustReputationManager** maintains an immutable ledger; **TaskAssigner** uses trust scores when ranking candidates

## Key Concepts

### Task Characteristics (§3)

- **Complexity** — trivial | simple | moderate | complex | extreme
- **Criticality** — impact of failure
- **Uncertainty** — outcome predictability
- **Verifiability** — how measurable the result is
- **Reversibility** — whether effects can be undone

### Delegation Contract (§4.1)

- Deliverables, acceptance criteria, granted permissions
- Resource budget (tokens, cost, duration)
- Monitoring mode, autonomy level
- Escalation policy

### Privilege Attenuation (§4.7)

Each delegation hop can only *narrow* permissions. A delegatee never receives more than the delegator holds; actions are intersected.

### Verification Methods (§4.8)

- `direct_inspection` — Evaluate criteria against output
- `output_validation` — Schema/format checks
- `automated_test` — LLM-based quality assessment
- `delegator_review` — Human confirmation
- `consensus` — Multiple verifiers
- `third_party_audit` — External verification (stub)

## See Also

- [Core Components](./core/) — AI client, agent loop, delegation, executor
- [Protocols](./protocols/) — Decomposition, assignment, monitoring, verification, trust, security, coordination
