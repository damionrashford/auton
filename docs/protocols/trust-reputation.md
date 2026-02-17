# Trust & Reputation

Immutable ledger, behavioral metrics, and web-of-trust (§4.6). Tracks agent reliability and builds trust scores over time.

## Concepts

### Trust Ledger Entry

Immutable record of a task completion:

```typescript
interface TrustLedgerEntry {
  id: string;
  agentId: string;
  taskId: string;
  domain: string;
  success: boolean;
  qualityScore: number;
  onTime: boolean;
  executionTime: number;
  violations: string[];
  cost: number;
  timestamp: number;
}
```

### Trust Endorsement (Web-of-Trust)

One agent endorsing another:

```typescript
interface TrustEndorsement {
  fromAgentId: string;
  toAgentId: string;
  trustLevel: number;  // 0-1
  domain?: string;
  reason: string;
  timestamp: number;
}
```

## Usage

```typescript
import { TrustReputationManager } from "auton";

const manager = new TrustReputationManager({
  decayRate: 0.05,
  minTasksForReliability: 5,
  directObservationWeight: 0.7,
  initialTrustScore: 0.5,
  violationPenalty: 0.15,
  consistencyBonus: 0.05,
});

// Record completion
manager.recordCompletion(agentId, taskId, "research", result, deadline);

// Record violation
manager.recordViolation(agentId, taskId, "research", "Budget exceeded");

// Add endorsement
manager.addEndorsement({
  fromAgentId: "agent-1",
  toAgentId: "agent-2",
  trustLevel: 0.8,
  domain: "code",
  reason: "Consistently delivered quality",
  timestamp: Date.now(),
});

// Compute trust
const score = manager.computeTrustScore(agentId);
const rep = manager.computeReputation(agentId);

// Should we trust for a task?
const { trusted, score, reason } = manager.shouldTrust(agentId, 0.6);
```

## Trust Score Computation

- **Direct** — Weighted mix of success rate, avg quality, on-time rate, consistency, violations
- **Web-of-trust** — Weighted average of endorsements (weighted by endorser reliability)
- **Combined** — `direct * directObservationWeight + wot * (1 - directObservationWeight)`

## Reputation Metrics

```typescript
interface ReputationMetrics {
  totalCompleted: number;
  totalFailed: number;
  successRate: number;
  avgQuality: number;
  avgResponseTime: number;
  onTimeRate: number;
  violations: number;
  webOfTrustScore: number;
  consistency: number;
  domainScores: Record<string, DomainScore>;
  lastUpdated: number;
}
```

## See Also

- [Task Assignment](./task-assignment.md) — Uses trust scores when ranking
- [Executor](../core/executor.md) — Records completions via trustManager
