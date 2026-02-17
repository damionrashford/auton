// §4.8 — Verifiable Task Completion Protocol

import type { Task, TaskResult, VerificationRecord } from "@/types/task/index.js";
import type { AIClient } from "@/core/ai/client.js";
import type { VerificationResult, VerificationDetail, ChildAttestation } from "@/protocols/verification/types.js";
import {
  evaluateCriterion,
  extractValue,
  llmEvaluate,
  buildResult,
} from "@/protocols/verification/evaluator.js";

export type { VerificationResult, VerificationDetail, ChildAttestation } from "@/protocols/verification/types.js";

export class TaskVerifier {
  constructor(private client?: AIClient) {}

  async verifyChain(
    parentTask: Task,
    parentResult: TaskResult,
    childAttestations: ChildAttestation[]
  ): Promise<VerificationResult> {
    const parentVerification = await this.verify(parentTask, parentResult);

    const details: VerificationDetail[] = [
      {
        criterion: { metric: "parent_verification", operator: "eq", target: true, weight: 0.5 },
        passed: parentVerification.verified,
        actualValue: parentVerification.verified,
        score: parentVerification.verified ? 1 : 0,
        message: parentVerification.verified
          ? "Parent task verified"
          : "Parent task verification failed",
      },
    ];

    let allChildrenVerified = true;
    for (const att of childAttestations) {
      const childOk = att.parentVerified && att.verificationRecord.verified;
      if (!childOk) allChildrenVerified = false;
      details.push({
        criterion: {
          metric: `child_${att.taskId}`,
          operator: "eq",
          target: true,
          weight: 0.5 / Math.max(1, childAttestations.length),
        },
        passed: childOk,
        actualValue: att.verificationRecord.verified,
        score: childOk ? 1 : 0,
        message: `Child ${att.taskId} (${att.delegateeId}): ${childOk ? "verified" : "not verified"}`,
      });
    }

    const verified = parentVerification.verified && allChildrenVerified;
    const confidence = parentVerification.confidence * (childAttestations.length > 0 ? 0.9 : 1);

    const baseEvidence =
      parentVerification.record.evidence && typeof parentVerification.record.evidence === "object"
        ? { ...(parentVerification.record.evidence as Record<string, unknown>) }
        : {};

    return {
      ...parentVerification,
      verified,
      confidence,
      details,
      record: {
        ...parentVerification.record,
        verified,
        confidence,
        evidence: { ...baseEvidence, childAttestations },
      },
    };
  }

  async verify(task: Task, result: TaskResult): Promise<VerificationResult> {
    const method = task.objective.verificationMethod;

    switch (method) {
      case "direct_inspection":
        return this.directInspection(task, result);
      case "output_validation":
        return this.outputValidation(task, result);
      case "automated_test":
        return this.automatedTest(task, result);
      case "delegator_review":
        return this.delegatorReview(task, result);
      case "consensus":
        return this.consensusVerification(task, result);
      case "third_party_audit":
        return this.thirdPartyAudit(task, result);
      default:
        return this.directInspection(task, result);
    }
  }

  private directInspection(task: Task, result: TaskResult): VerificationResult {
    const details: VerificationDetail[] = [];
    for (const criterion of task.objective.successCriteria) {
      details.push(evaluateCriterion(criterion, result, extractValue));
    }
    return buildResult("direct_inspection", details);
  }

  private outputValidation(task: Task, result: TaskResult): VerificationResult {
    const details: VerificationDetail[] = [];

    if (result.output === undefined || result.output === null) {
      details.push({
        criterion: { metric: "output_exists", operator: "neq", target: null, weight: 1 },
        passed: false,
        actualValue: result.output,
        score: 0,
        message: "No output produced",
      });
    } else {
      details.push({
        criterion: { metric: "output_exists", operator: "neq", target: null, weight: 0.2 },
        passed: true,
        actualValue: typeof result.output,
        score: 1,
        message: "Output produced",
      });
    }

    for (const criterion of task.objective.successCriteria) {
      details.push(evaluateCriterion(criterion, result, extractValue));
    }
    return buildResult("output_validation", details);
  }

  private async automatedTest(task: Task, result: TaskResult): Promise<VerificationResult> {
    const details: VerificationDetail[] = [];
    for (const criterion of task.objective.successCriteria) {
      details.push(evaluateCriterion(criterion, result, extractValue));
    }
    if (this.client) {
      details.push(await llmEvaluate(this.client, task, result));
    }
    return buildResult("automated_test", details);
  }

  private delegatorReview(task: Task, result: TaskResult): VerificationResult {
    const details: VerificationDetail[] = [];
    for (const criterion of task.objective.successCriteria) {
      details.push(evaluateCriterion(criterion, result, extractValue));
    }
    const autoResult = buildResult("delegator_review", details);
    autoResult.confidence = Math.min(autoResult.confidence, 0.6);
    autoResult.record.verified = false;
    return autoResult;
  }

  private async consensusVerification(task: Task, result: TaskResult): Promise<VerificationResult> {
    const details: VerificationDetail[] = [];
    for (const criterion of task.objective.successCriteria) {
      details.push(evaluateCriterion(criterion, result, extractValue));
    }

    if (this.client) {
      const evaluations = await Promise.all([
        llmEvaluate(this.client, task, result, 0.2),
        llmEvaluate(this.client, task, result, 0.5),
        llmEvaluate(this.client, task, result, 0.8),
      ]);
      const avgScore = evaluations.reduce((s, e) => s + e.score, 0) / evaluations.length;
      const consensus = evaluations.filter((e) => e.passed).length >= 2;
      details.push({
        criterion: { metric: "consensus", operator: "gte", target: 0.5, weight: 0.3 },
        passed: consensus,
        actualValue: avgScore,
        score: avgScore,
        message: `Consensus: ${evaluations.filter((e) => e.passed).length}/3 agreed (avg: ${avgScore.toFixed(2)})`,
      });
    }

    const verResult = buildResult("consensus", details);
    verResult.confidence = this.client ? 0.85 : 0.5;
    return verResult;
  }

  private thirdPartyAudit(task: Task, result: TaskResult): VerificationResult {
    const details: VerificationDetail[] = [];
    for (const criterion of task.objective.successCriteria) {
      details.push(evaluateCriterion(criterion, result, extractValue));
    }
    const verResult = buildResult("third_party_audit", details);
    verResult.confidence = 0.4;
    verResult.record.verified = false;
    return verResult;
  }

  confirmVerification(
    record: VerificationRecord,
    approved: boolean,
    verifierId: string
  ): VerificationRecord {
    return {
      ...record,
      verified: approved,
      verifierId,
      confidence: approved ? Math.max(record.confidence, 0.9) : 0,
      timestamp: Date.now(),
    };
  }
}
