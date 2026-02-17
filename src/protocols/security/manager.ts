import type { CoordinationTrigger } from "@/protocols/coordination/index.js";
import type {
  SecurityRule,
  SecurityContext,
  ThreatDetection,
} from "@/protocols/security/types.js";
import { createDefaultRules } from "@/protocols/security/rules.js";

const INJECTION_PATTERNS = [
  /ignore\s+(previous|above|all)\s+instructions/i,
  /system\s*:\s*you\s+are/i,
  /\boverride\b.*\bpermission/i,
  /\bescalate\b.*\bprivilege/i,
  /\bsudo\b/i,
  /\brm\s+-rf\b/i,
  /\bdrop\s+table\b/i,
  /\bdelete\s+from\b.*\bwhere\s+1\s*=\s*1/i,
];

export type {
  ThreatCategory,
  DelegateeThreat,
  DelegatorThreat,
  EcosystemThreat,
  ThreatType,
  ThreatDetection,
  SecurityRule,
  SecurityContext,
  ToolCallRecord,
  DelegationRecord,
  ResourceUsageRecord,
} from "@/protocols/security/types.js";

export class SecurityManager {
  private rules: SecurityRule[] = [];
  private detections: ThreatDetection[] = [];
  private triggerCallback?: (trigger: CoordinationTrigger) => void;
  private detectionIdCounter = 0;

  constructor(onTrigger?: (trigger: CoordinationTrigger) => void) {
    this.triggerCallback = onTrigger;
    const getNextId = () => `threat_${(this.detectionIdCounter++).toString(36)}`;
    this.rules.push(...createDefaultRules(getNextId));
  }

  scan(context: SecurityContext): ThreatDetection[] {
    const newDetections: ThreatDetection[] = [];

    for (const rule of this.rules) {
      if (!rule.enabled) continue;
      const detection = rule.check(context);
      if (detection) {
        this.detections.push(detection);
        newDetections.push(detection);

        if (detection.severity === "high" || detection.severity === "critical") {
          this.triggerCallback?.({
            type: "security_alert",
            severity: detection.severity === "critical" ? "critical" : "warning",
            taskId: detection.taskId,
            agentId: detection.agentId,
            message: `Security threat: ${detection.threatType} — ${detection.description}`,
            data: detection,
            timestamp: Date.now(),
          });
        }
      }
    }

    return newDetections;
  }

  validateToolCall(
    agentId: string,
    toolName: string,
    args: string,
    _permissions: string[]
  ): ThreatDetection | null {
    for (const pattern of INJECTION_PATTERNS) {
      if (pattern.test(args)) {
        const detection: ThreatDetection = {
          id: `threat_${(this.detectionIdCounter++).toString(36)}`,
          threatType: "prompt_injection",
          category: "malicious_delegator",
          severity: "high",
          agentId,
          description: `Potential prompt injection in tool call arguments: ${toolName}`,
          evidence: [{ toolName, pattern: pattern.source, args: args.slice(0, 200) }],
          timestamp: Date.now(),
          mitigated: false,
        };
        this.detections.push(detection);
        return detection;
      }
    }
    return null;
  }

  addRule(rule: SecurityRule): void {
    this.rules.push(rule);
  }

  getDetections(agentId?: string): ThreatDetection[] {
    if (agentId) return this.detections.filter((d) => d.agentId === agentId);
    return [...this.detections];
  }

  mitigate(detectionId: string): void {
    const detection = this.detections.find((d) => d.id === detectionId);
    if (detection) detection.mitigated = true;
  }
}
