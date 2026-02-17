# Task Assignment

Matches tasks to agents based on capabilities, trust, availability, domain match, cost efficiency, and historical performance (§4.2).

## Scoring Dimensions

| Dimension | Weight (default) | Description |
|-----------|------------------|-------------|
| Capability match | 0.30 | How well agent capabilities match task requirements |
| Trust score | 0.20 | Agent's trust score from reputation |
| Availability | 0.15 | available=1, busy=0.7, offline=0 |
| Domain match | 0.15 | Overlap of task tags with agent domains |
| Cost efficiency | 0.10 | Inverse of cost per task |
| Historical performance | 0.10 | Trust score / historical success |

## Usage

```typescript
import { TaskAssigner, type AssignmentWeights } from "auton";

const assigner = new TaskAssigner({
  capabilityMatch: 0.35,
  trustScore: 0.25,
  availability: 0.15,
  domainMatch: 0.10,
  costEfficiency: 0.10,
  historicalPerformance: 0.05,
});

// Rank all candidates
const scores = assigner.rankCandidates(task, candidates);

// Select best agent
const agent = assigner.assign(task, candidates);

// With span-of-control (max concurrent delegatees)
const agent = assigner.assign(task, candidates, {
  delegator: orchestrator,
  currentDelegateeCount: 2,
});

// Batch assignment (greedy, respects max concurrent per agent)
const assignments = assigner.assignBatch(tasks, candidates, 3);
// Map<taskId, agentId>
```

## Assignment Score

```typescript
interface AssignmentScore {
  agentId: string;
  totalScore: number;
  breakdown: {
    capabilityMatch: number;
    trustScore: number;
    availabilityScore: number;
    domainMatch: number;
    costEfficiency: number;
    historicalPerformance: number;
  };
}
```

## Capability Matching

- If task has no `requiredPermissions` or `tags`, uses average capability proficiency
- Otherwise, matches task tags and required permissions to agent capabilities
- Supports capability `domains` for domain-based matching

## See Also

- [Trust & Reputation](./trust-reputation.md) — Source of trust scores
- [Optimization](./optimization.md) — Multi-objective selection
