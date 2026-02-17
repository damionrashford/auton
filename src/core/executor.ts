// ============================================================================
// Delegation Executor — Full Orchestrator
// Implements the complete delegation lifecycle from the paper:
// Complexity floor → Decompose → Assign → Contract → Execute → Verify → Trust
// ============================================================================

import type { Task, TaskResult, DelegationContract, ResourceBudget } from "@/types/task/index.js";
import type { AgentProfile } from "@/types/agent.js";
import type { ToolExecutor } from "@/core/agent/index.js";
import { AgentLoop } from "@/core/agent/index.js";
import { TaskDecomposer } from "@/protocols/taskdecomposition/index.js";
import { TaskAssigner } from "@/protocols/taskassignment/index.js";
import { DelegationChainManager } from "@/core/delegation/index.js";
import { createContract } from "@/core/delegation/contract.js";
import { TaskVerifier } from "@/protocols/verification/index.js";
import { TrustReputationManager } from "@/protocols/trust/index.js";
import { Monitor } from "@/protocols/monitoring/index.js";
import { SecurityManager } from "@/protocols/security/index.js";
import { AdaptiveCoordinator } from "@/protocols/coordination/index.js";
import type { AIClient } from "@/core/ai/client.js";
import type { CoordinationTrigger } from "@/protocols/coordination/index.js";

import { shouldBypassDelegation, type ComplexityFloorConfig } from "@/core/delegation/floor.js";

export type { ComplexityFloorConfig } from "@/core/delegation/floor.js";
export { shouldBypassDelegation } from "@/core/delegation/floor.js";

// ---------------------------------------------------------------------------
// Executor Configuration
// ---------------------------------------------------------------------------

export interface DelegationExecutorConfig {
  /** Candidate agents for assignment */
  candidates: AgentProfile[];
  /** Delegator (usually the orchestrator or human proxy) */
  delegator: AgentProfile;
  /** Tool handlers for the executing agent */
  toolExecutor?: ToolExecutor;
  /** Optional AI client for AI-assisted decomposition */
  decompositionClient?: AIClient;
  /** Optional Trust & Reputation manager for post-completion updates */
  trustManager?: TrustReputationManager;
  /** Optional Verifier client for LLM-based verification */
  verifierClient?: AIClient;
  /** Complexity floor config */
  complexityFloor?: Partial<ComplexityFloorConfig>;
  /** Whether to decompose before assignment (when not bypassing) */
  decomposeFirst?: boolean;
  /** Default resource budget when creating contracts */
  defaultBudget?: ResourceBudget;
  /** Callback for coordination triggers */
  onCoordinationTrigger?: (trigger: CoordinationTrigger) => void;
}

// ---------------------------------------------------------------------------
// Delegation Executor
// ---------------------------------------------------------------------------

export class DelegationExecutor {
  private readonly config: DelegationExecutorConfig;
  private readonly taskAssigner: TaskAssigner;
  private readonly chainManager: DelegationChainManager;
  private readonly coordinator: AdaptiveCoordinator;
  private monitor: Monitor | undefined;
  private securityManager: SecurityManager | undefined;

  constructor(config: DelegationExecutorConfig) {
    this.config = {
      decomposeFirst: false,
      ...config,
    };

    this.taskAssigner = new TaskAssigner();
    this.chainManager = new DelegationChainManager();
    this.coordinator = new AdaptiveCoordinator();

    const onTrigger = config.onCoordinationTrigger ?? (() => {});
    this.monitor = new Monitor(undefined, (t) => {
      this.coordinator.processTrigger(t);
      onTrigger(t);
    });
    this.securityManager = new SecurityManager((t) => {
      this.coordinator.processTrigger(t);
      onTrigger(t);
    });
  }

  /**
   * Execute a task through the full delegation lifecycle.
   */
  async execute(task: Task): Promise<TaskResult> {
    const { candidates, delegator, trustManager, complexityFloor, decomposeFirst } =
      this.config;

    if (shouldBypassDelegation(task, complexityFloor)) {
      const assignee = this.taskAssigner.assign(task, candidates) ?? delegator;
      return this.runAgentLoop(task, assignee, undefined);
    }

    let taskToExecute = task;

    if (decomposeFirst && this.config.decompositionClient) {
      const decomposer = new TaskDecomposer(this.config.decompositionClient);
      const plan = await decomposer.decompose(task);
      if (plan.subtasks.length > 1) {
        const firstSubtask = plan.subtasks[0];
        taskToExecute = { ...firstSubtask, parentId: task.id };
      }
    }

    const assignee = this.taskAssigner.assign(taskToExecute, candidates);
    if (!assignee) {
      return {
        success: false,
        output: null,
        scores: {},
        executionTime: 0,
        error: "No suitable agent found for assignment",
      };
    }

    const contract = createContract(
      taskToExecute,
      delegator,
      assignee,
      this.config.defaultBudget
    );
    this.chainManager.delegate(delegator, assignee, contract);

    const result = await this.runAgentLoop(taskToExecute, assignee, contract);

    const verifier = new TaskVerifier(this.config.verifierClient);
    const verification = await verifier.verify(taskToExecute, result);
    result.verification = verification.record;
    result.success = result.success && verification.verified;

    if (trustManager) {
      const domain = taskToExecute.tags[0] ?? "default";
      trustManager.recordCompletion(
        assignee.id,
        taskToExecute.id,
        domain,
        result,
        taskToExecute.deadline
      );
    }

    return result;
  }

  private async runAgentLoop(
    task: Task,
    agent: AgentProfile,
    contract?: DelegationContract
  ): Promise<TaskResult> {
    const loop = new AgentLoop({
      agent,
      toolExecutor: this.config.toolExecutor,
      monitor: this.monitor,
      securityManager: this.securityManager,
      budget: contract?.budget,
    });

    return loop.run(task);
  }

  /** Get the coordinator for advanced usage */
  getCoordinator(): AdaptiveCoordinator {
    return this.coordinator;
  }

  /** Get the chain manager */
  getChainManager(): DelegationChainManager {
    return this.chainManager;
  }
}
