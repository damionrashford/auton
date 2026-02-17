import type { Permission } from "@/types/task/index.js";

export function resourceMatches(pattern: string, resource: string): boolean {
  if (pattern === "*") return true;
  if (pattern === resource) return true;
  if (pattern.endsWith("*")) {
    const prefix = pattern.slice(0, -1);
    return resource.startsWith(prefix);
  }
  return false;
}

export function isExpired(permission: Permission): boolean {
  return permission.expiresAt !== undefined && Date.now() > permission.expiresAt;
}

export function conditionsMet(permission: Permission): boolean {
  if (!permission.conditions || permission.conditions.length === 0) return true;

  for (const condition of permission.conditions) {
    switch (condition.type) {
      case "time_window": {
        const now = Date.now();
        const start = condition.parameters.start as number | undefined;
        const end = condition.parameters.end as number | undefined;
        if (start && now < start) return false;
        if (end && now > end) return false;
        break;
      }
      case "rate_limit":
        break;
    }
  }

  return true;
}
