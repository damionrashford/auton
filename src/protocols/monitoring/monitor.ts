import type { MonitoringMode, ResourceBudget } from "@/types/task/index.js";
import type { CoordinationTrigger } from "@/protocols/coordination/index.js";
import type { MonitoringEvent, MonitoringEventType, TaskMetrics, MonitoringThresholds } from "@/protocols/monitoring/types.js";
import { DEFAULT_THRESHOLDS } from "@/protocols/monitoring/types.js";
import { checkHealth } from "@/protocols/monitoring/health.js";

export type {
  MonitoringEvent,
  MonitoringEventType,
  TaskMetrics,
  MonitoringThresholds,
  MonitoringConfig,
} from "@/protocols/monitoring/types.js";

export class Monitor {
  private metrics: Map<string, TaskMetrics> = new Map();
  private thresholds: MonitoringThresholds;
  private intervals: Map<string, ReturnType<typeof setInterval>> = new Map();
  private triggerCallback?: (trigger: CoordinationTrigger) => void;
  private eventIdCounter = 0;

  constructor(
    thresholds?: Partial<MonitoringThresholds>,
    onTrigger?: (trigger: CoordinationTrigger) => void
  ) {
    this.thresholds = { ...DEFAULT_THRESHOLDS, ...thresholds };
    this.triggerCallback = onTrigger;
  }

  startMonitoring(
    taskId: string,
    agentId: string,
    mode: MonitoringMode,
    budget?: ResourceBudget
  ): void {
    const metrics: TaskMetrics = {
      taskId,
      agentId,
      elapsedTime: 0,
      tokensUsed: 0,
      costIncurred: 0,
      toolCalls: 0,
      errorCount: 0,
      delegationCount: 0,
      progress: 0,
      lastHeartbeat: Date.now(),
      events: [],
    };

    this.metrics.set(taskId, metrics);
    this.recordEvent(taskId, agentId, "task_started", {});

    if (mode === "continuous" || mode === "periodic") {
      const interval = mode === "continuous" ? 5_000 : 30_000;
      const timer = setInterval(() => {
        checkHealth(
          taskId,
          this.metrics.get(taskId),
          this.thresholds,
          budget,
          (t) => this.triggerCallback?.(t)
        );
      }, interval);
      this.intervals.set(taskId, timer);
    }
  }

  stopMonitoring(taskId: string): void {
    const timer = this.intervals.get(taskId);
    if (timer) {
      clearInterval(timer);
      this.intervals.delete(taskId);
    }
  }

  recordEvent(
    taskId: string,
    agentId: string,
    type: MonitoringEventType,
    data: Record<string, unknown>
  ): void {
    const metrics = this.metrics.get(taskId);
    if (!metrics) return;

    const event: MonitoringEvent = {
      id: `evt_${(this.eventIdCounter++).toString(36)}`,
      taskId,
      agentId,
      type,
      timestamp: Date.now(),
      data,
    };

    metrics.events.push(event);
    metrics.lastHeartbeat = Date.now();

    switch (type) {
      case "tool_called":
        metrics.toolCalls++;
        break;
      case "error_occurred":
        metrics.errorCount++;
        break;
      case "token_usage":
        metrics.tokensUsed += (data.tokens as number) ?? 0;
        break;
      case "cost_incurred":
        metrics.costIncurred += (data.cost as number) ?? 0;
        break;
      case "delegation_created":
        metrics.delegationCount++;
        break;
      case "task_progress":
        metrics.progress = (data.progress as number) ?? metrics.progress;
        break;
      case "task_completed":
        metrics.progress = 1;
        this.stopMonitoring(taskId);
        break;
      case "task_failed":
        this.stopMonitoring(taskId);
        break;
    }

    metrics.elapsedTime = Date.now() - (metrics.events[0]?.timestamp ?? Date.now());
  }

  heartbeat(taskId: string): void {
    const metrics = this.metrics.get(taskId);
    if (metrics) {
      metrics.lastHeartbeat = Date.now();
      this.recordEvent(taskId, metrics.agentId, "heartbeat", {});
    }
  }

  getMetrics(taskId: string): TaskMetrics | undefined {
    return this.metrics.get(taskId);
  }

  getActiveMonitoring(): TaskMetrics[] {
    return Array.from(this.metrics.values());
  }

  dispose(): void {
    for (const timer of this.intervals.values()) {
      clearInterval(timer);
    }
    this.intervals.clear();
    this.metrics.clear();
  }
}
