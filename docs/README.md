# AUTON — Documentation

TypeScript framework for AI agent delegation, multi-agent orchestration, and adaptive task decomposition. Based on the research paper [*Intelligent AI Delegation*](https://arxiv.org/abs/2602.11865) (Tomasev, Franklin, Osindero, 2026).

---

## Documentation

### Getting Started

- [**Installation & Quick Start**](./getting-started.md) — Install, first run, minimal example
- [**Architecture Overview**](./architecture.md) — High-level design, lifecycle, data flow

### Core Components

- [**AI Client**](./core/ai-client.md) — OpenAI-compatible HTTP client, streaming, tools
- [**Agent Loop**](./core/agent-loop.md) — LLM execution engine, tool calling, budgets
- [**Delegation Chain**](./core/delegation.md) — Privilege attenuation, contracts, chains
- [**Executor**](./core/executor.md) — Full orchestration pipeline

### Protocols

- [**Task Decomposition**](./protocols/task-decomposition.md) — Breaking tasks into subtask DAGs
- [**Task Assignment**](./protocols/task-assignment.md) — Matching tasks to agents
- [**Monitoring**](./protocols/monitoring.md) — Continuous/periodic monitoring, health checks
- [**Verification**](./protocols/verification.md) — Direct inspection, LLM evaluation
- [**Trust & Reputation**](./protocols/trust-reputation.md) — Ledger, web-of-trust
- [**Security**](./protocols/security.md) — Threat detection, tool validation
- [**Adaptive Coordination**](./protocols/coordination.md) — Triggers, replanning, escalation
- [**Permissions**](./protocols/permissions.md) — Just-in-time permissions, policies
- [**Optimization**](./protocols/optimization.md) — Multi-objective Pareto selection

### Integration

- [**MCP (Model Context Protocol)**](./mcp.md) — stdio, Streamable HTTP, SSE transports

### Reference

- [**API Reference**](./api-reference.md) — Exported classes, types, functions
- [**Type Definitions**](./types.md) — Task, Agent, Contract, and protocol types

---

## Paper

- **arXiv:** [https://arxiv.org/abs/2602.11865](https://arxiv.org/abs/2602.11865)
- **Local PDF:** [intelli-delegate.pdf](./intelli-delegate.pdf)
