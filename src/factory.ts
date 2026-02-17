import type { AgentProfile } from "@/types/agent.js";
import type { ToolExecutor } from "@/core/agent/index.js";
import { AgentLoop } from "@/core/agent/index.js";
import { Monitor } from "@/protocols/monitoring/index.js";
import { AdaptiveCoordinator } from "@/protocols/coordination/index.js";
import { SecurityManager } from "@/protocols/security/index.js";
import type { CoordinationTrigger } from "@/protocols/coordination/index.js";

export interface DelegationFrameworkConfig {
  agent: AgentProfile;
  toolExecutor?: ToolExecutor;
  enableMonitoring?: boolean;
  enableSecurity?: boolean;
  onCoordinationTrigger?: (trigger: CoordinationTrigger) => void;
}

export function createDelegationFramework(config: DelegationFrameworkConfig): {
  agentLoop: AgentLoop;
  monitor: Monitor | undefined;
  securityManager: SecurityManager | undefined;
  coordinator: AdaptiveCoordinator;
} {
  const coordinator = new AdaptiveCoordinator();
  const onTrigger = config.onCoordinationTrigger ?? (() => {});

  const monitor = config.enableMonitoring
    ? new Monitor(undefined, (t) => {
        coordinator.processTrigger(t);
        onTrigger(t);
      })
    : undefined;

  const securityManager = config.enableSecurity
    ? new SecurityManager((t) => {
        coordinator.processTrigger(t);
        onTrigger(t);
      })
    : undefined;

  const agentLoop = new AgentLoop({
    agent: config.agent,
    toolExecutor: config.toolExecutor,
    monitor,
    securityManager,
  });

  return { agentLoop, monitor, securityManager, coordinator };
}
