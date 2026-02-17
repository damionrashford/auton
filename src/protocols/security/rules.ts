import type { SecurityRule, SecurityContext, ThreatDetection } from "@/protocols/security/types.js";

export function createDefaultRules(getNextId: () => string): SecurityRule[] {
  return [
    {
      id: "resource_exhaustion",
      name: "Resource Exhaustion Detection",
      description: "Detects agents consuming excessive resources",
      detectsThreats: ["resource_exhaustion"],
      check: (ctx) => checkResourceExhaustion(ctx, getNextId),
      enabled: true,
    },
    {
      id: "unauthorized_access",
      name: "Unauthorized Access Pattern",
      description: "Detects agents accessing resources outside their permissions",
      detectsThreats: ["unauthorized_access"],
      check: (ctx) => checkUnauthorizedAccess(ctx, getNextId),
      enabled: true,
    },
    {
      id: "sybil_detection",
      name: "Sybil Attack Detection",
      description: "Detects suspiciously similar agents that may be sybil identities",
      detectsThreats: ["sybil_attack"],
      check: (ctx) => checkSybilAttack(ctx, getNextId),
      enabled: true,
    },
    {
      id: "delegation_depth",
      name: "Excessive Delegation Depth",
      description: "Detects suspiciously deep delegation chains",
      detectsThreats: ["agent_trap"],
      check: (ctx) => checkDelegationDepth(ctx, getNextId),
      enabled: true,
    },
    {
      id: "data_exfiltration",
      name: "Data Exfiltration Pattern",
      description: "Detects patterns suggesting data exfiltration via tool calls",
      detectsThreats: ["data_exfiltration"],
      check: (ctx) => checkDataExfiltration(ctx, getNextId),
      enabled: true,
    },
  ];
}

function checkResourceExhaustion(
  ctx: SecurityContext,
  getNextId: () => string
): ThreatDetection | null {
  const usage = ctx.resourceUsage;
  const timeMinutes = usage.timeWindow / 60_000;
  if (timeMinutes <= 0) return null;

  const callsPerMinute = usage.apiCalls / timeMinutes;
  const tokensPerMinute = usage.tokensUsed / timeMinutes;

  if (callsPerMinute > 60 || tokensPerMinute > 100_000) {
    return {
      id: getNextId(),
      threatType: "resource_exhaustion",
      category: "malicious_delegatee",
      severity: callsPerMinute > 120 ? "critical" : "high",
      agentId: usage.agentId,
      description: `Excessive resource usage: ${callsPerMinute.toFixed(0)} calls/min, ${tokensPerMinute.toFixed(0)} tokens/min`,
      evidence: [{ callsPerMinute, tokensPerMinute, timeWindow: usage.timeWindow }],
      timestamp: Date.now(),
      mitigated: false,
    };
  }
  return null;
}

function checkUnauthorizedAccess(
  ctx: SecurityContext,
  getNextId: () => string
): ThreatDetection | null {
  if (!ctx.agent || ctx.resourceUsage.uniqueResourcesAccessed.size === 0) return null;

  const permittedResources = new Set(ctx.agent.basePermissions.map((p) => p.resource));
  const unauthorized: string[] = [];

  for (const resource of ctx.resourceUsage.uniqueResourcesAccessed) {
    let permitted = false;
    for (const pr of permittedResources) {
      if (resource === pr || pr === "*" || (pr.endsWith("*") && resource.startsWith(pr.slice(0, -1)))) {
        permitted = true;
        break;
      }
    }
    if (!permitted) unauthorized.push(resource);
  }

  if (unauthorized.length > 0) {
    return {
      id: getNextId(),
      threatType: "unauthorized_access",
      category: "malicious_delegatee",
      severity: unauthorized.length > 3 ? "critical" : "high",
      agentId: ctx.agent.id,
      description: `Agent accessed ${unauthorized.length} unauthorized resources`,
      evidence: unauthorized.map((r) => ({ resource: r })),
      timestamp: Date.now(),
      mitigated: false,
    };
  }
  return null;
}

function checkSybilAttack(ctx: SecurityContext, getNextId: () => string): ThreatDetection | null {
  if (ctx.allAgents.length < 3) return null;

  const capFingerprints = new Map<string, typeof ctx.allAgents>();
  for (const agent of ctx.allAgents) {
    const fingerprint = agent.capabilities
      .map((c) => `${c.name}:${c.proficiency.toFixed(1)}`)
      .sort()
      .join("|");
    const group = capFingerprints.get(fingerprint) ?? [];
    group.push(agent);
    capFingerprints.set(fingerprint, group);
  }

  for (const [, group] of capFingerprints) {
    if (group.length >= 3) {
      return {
        id: getNextId(),
        threatType: "sybil_attack",
        category: "ecosystem",
        severity: group.length >= 5 ? "critical" : "medium",
        description: `${group.length} agents with identical capability profiles detected`,
        evidence: group.map((a) => ({ agentId: a.id, name: a.name })),
        timestamp: Date.now(),
        mitigated: false,
      };
    }
  }
  return null;
}

function checkDelegationDepth(ctx: SecurityContext, getNextId: () => string): ThreatDetection | null {
  const taskDelegations = new Map<string, number>();
  for (const d of ctx.recentDelegations) {
    taskDelegations.set(d.taskId, (taskDelegations.get(d.taskId) ?? 0) + 1);
  }

  for (const [taskId, count] of taskDelegations) {
    if (count > 5) {
      return {
        id: getNextId(),
        threatType: "agent_trap",
        category: "ecosystem",
        severity: count > 10 ? "critical" : "high",
        taskId,
        description: `Task ${taskId} has been delegated ${count} times — possible agent trap`,
        evidence: [{ taskId, delegationCount: count }],
        timestamp: Date.now(),
        mitigated: false,
      };
    }
  }
  return null;
}

function checkDataExfiltration(ctx: SecurityContext, getNextId: () => string): ThreatDetection | null {
  const suspiciousPatterns = [
    /https?:\/\/[^/]*\.(ru|cn|tk|ml|ga|cf)\b/i,
    /webhook\.site/i,
    /requestbin/i,
    /ngrok\.io/i,
    /base64['"]/i,
  ];

  const suspicious = ctx.recentToolCalls.filter((tc) =>
    suspiciousPatterns.some((p) => p.test(tc.arguments))
  );

  if (suspicious.length >= 2) {
    return {
      id: getNextId(),
      threatType: "data_exfiltration",
      category: "malicious_delegatee",
      severity: "critical",
      agentId: suspicious[0].agentId,
      description: `${suspicious.length} tool calls with suspicious external data patterns`,
      evidence: suspicious.map((tc) => ({ toolName: tc.toolName, timestamp: tc.timestamp })),
      timestamp: Date.now(),
      mitigated: false,
    };
  }
  return null;
}
