# Auton

[![npm version](https://img.shields.io/npm/v/auton.svg)](https://www.npmjs.com/package/auton)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Node.js ≥18](https://img.shields.io/badge/node-%3E%3D18-green.svg)](https://nodejs.org)

**AUTON** is a TypeScript framework for **AI agent delegation**, **multi-agent orchestration**, and **adaptive task decomposition**. Build autonomous AI systems that decompose complex tasks, assign work to specialized agents, and verify results—with zero dependencies and full OpenAI compatibility.

> Based on the research paper [*Intelligent AI Delegation*](https://arxiv.org/abs/2602.11865) (Tomasev, Franklin, Osindero, 2026).

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Documentation](#documentation)
- [Requirements](#requirements)
- [Paper & References](#paper--references)
- [License](#license)

---

## Features

- **Task decomposition** — Break complex tasks into subtask DAGs (AI-assisted or manual)
- **Task assignment** — Match tasks to agents by capabilities, trust, and availability
- **Delegation chains** — Privilege attenuation, permission narrowing, contract-first design
- **Agent loop** — LLM execution with tool calling, streaming, and token budgets
- **Verification** — Direct inspection, output validation, LLM-based evaluation
- **Trust & reputation** — Immutable ledger, web-of-trust, behavioral metrics
- **MCP support** — Model Context Protocol (stdio, Streamable HTTP, SSE transports)
- **Complexity floor** — Bypass full pipeline for trivial tasks

---

## Installation

```bash
npm install auton
```

---

## Quick Start

```typescript
import {
  createDelegationFramework,
  DelegationExecutor,
} from "auton";

// Pre-wired framework with monitoring and security
const { agentLoop, monitor, coordinator } = createDelegationFramework({
  agent: myAgentProfile,
  toolExecutor: myTools,
  enableMonitoring: true,
  enableSecurity: true,
});

// Or full multi-agent orchestration
const executor = new DelegationExecutor({
  candidates: [agent1, agent2],
  delegator: orchestratorAgent,
  toolExecutor: myTools,
  trustManager: trustRepo,
  decomposeFirst: true,
});

const result = await executor.execute(task);
```

---

## Architecture

| Module | Description |
|--------|-------------|
| `core/ai` | OpenAI-compatible HTTP client (streaming, tools, structured output) |
| `core/agent` | Agent loop with tool execution, system prompts |
| `core/delegation` | Chain manager, privilege attenuation, contracts |
| `core/executor` | Full orchestration pipeline |
| `protocols/taskdecomposition` | AI-assisted and manual decomposition |
| `protocols/taskassignment` | Capability/trust/availability scoring |
| `protocols/optimization` | Multi-objective Pareto optimization |
| `protocols/coordination` | Adaptive triggers, replanning, escalation |
| `protocols/monitoring` | Continuous/periodic monitoring, health checks |
| `protocols/trust` | Trust ledger, reputation, web-of-trust |
| `protocols/permissions` | Just-in-time permissions, policies |
| `protocols/verification` | Direct inspection, LLM evaluation |
| `protocols/security` | Threat detection, tool validation |
| `mcp` | Model Context Protocol (stdio, Streamable HTTP, SSE) |

---

## Documentation

Full documentation is in the [`docs/`](./docs/README.md) folder:

- [Getting Started](./docs/getting-started.md)
- [Architecture](./docs/architecture.md)
- [Core Components](./docs/core/) — AI Client, Agent Loop, Delegation, Executor
- [Protocols](./docs/protocols/) — Decomposition, Assignment, Monitoring, Verification, Trust, Security, Coordination, Permissions, Optimization
- [MCP Integration](./docs/mcp.md)
- [API Reference](./docs/api-reference.md)
- [Type Definitions](./docs/types.md)

---

## Requirements

- **Node.js** ≥ 18
- **TypeScript** (for type definitions)

---

## Paper & References

- **arXiv:** [https://arxiv.org/abs/2602.11865](https://arxiv.org/abs/2602.11865)
- **Local PDF:** [intelli-delegate.pdf](./docs/intelli-delegate.pdf)

---

## License

MIT
