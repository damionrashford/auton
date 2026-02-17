# Verification

Verifiable task completion protocol (§4.8). Supports direct inspection, output validation, automated testing (LLM), delegator review, consensus, and third-party audit.

## Verification Methods

| Method | Description |
|--------|-------------|
| `direct_inspection` | Evaluate each success criterion against output |
| `output_validation` | Check output exists + criteria |
| `automated_test` | Criteria + optional LLM quality assessment |
| `delegator_review` | Criteria + marks for human confirmation |
| `consensus` | Multiple LLM evaluations, majority vote |
| `third_party_audit` | Stub for external verification |

## Usage

```typescript
import { TaskVerifier, type ChildAttestation } from "auton";

const verifier = new TaskVerifier(aiClient);  // Optional for LLM methods

const result = await verifier.verify(task, taskResult);

// Chain verification (parent + child attestations)
const chainResult = await verifier.verifyChain(
  parentTask,
  parentResult,
  childAttestations
);

// Confirm delegator review
const updated = verifier.confirmVerification(record, true, "delegator-1");
```

## Verification Result

```typescript
interface VerificationResult {
  verified: boolean;
  confidence: number;
  method: VerificationMethod;
  details: VerificationDetail[];
  overallScore: number;
  record: VerificationRecord;
}

interface VerificationDetail {
  criterion: SuccessCriterion;
  passed: boolean;
  actualValue: unknown;
  score: number;
  message: string;
}
```

## Success Criteria Operators

- `eq`, `neq` — Equality
- `gt`, `gte`, `lt`, `lte` — Numeric comparison
- `contains` — String contains
- `matches` — Regex match
- `custom` — External evaluation (score ≥ 0.5 = pass)

## Chain Verification

When a parent aggregates results from sub-delegatees, it can submit child attestations. The verifier checks:

1. Parent result meets criteria
2. All child attestations are verified by their respective delegators

## See Also

- [Task Types](../types.md#task-objective) — SuccessCriterion, VerificationMethod
- [Executor](../core/executor.md) — Uses TaskVerifier in pipeline
