# AGENTS.md — Guidelines for AI Coding Assistants

AUTON is a TypeScript framework for AI agent delegation, multi-agent orchestration, and adaptive task decomposition. This file provides context and instructions for AI coding agents working on this codebase.

---

## Project Overview

- **Language:** TypeScript (ES2022)
- **Runtime:** Node.js ≥ 18
- **Module:** ESM only
- **Dependencies:** Zero runtime dependencies; dev: `@types/node`, `tsc-alias`
- **Paper:** Based on [Intelligent AI Delegation](https://arxiv.org/abs/2602.11865) (Tomasev, Franklin, Osindero, 2026)

---

## Build & Commands

| Command | Purpose |
|---------|---------|
| `npm run build` | Compile TypeScript → `dist/` and rewrite `@/` path aliases |
| `npm run check` | Type-check only (`tsc --noEmit`) |
| `npm install` | Install dependencies |

**Important:** The build uses `tsc` followed by `tsc-alias` to resolve `@/*` imports to relative paths in the output. Do not remove `tsc-alias` from the build pipeline.

---

## Path Aliases

- **`@/*`** maps to **`./src/*`**
- Use `@/` for all internal imports (e.g. `@/types/task/index.js`, `@/core/agent/loop.js`)
- Never use `../` or `../../` — use `@/` for consistency

---

## Codebase Structure

```
src/
├── core/           # AI client, agent loop, delegation, executor
├── protocols/      # taskdecomposition, taskassignment, monitoring, trust, etc.
├── types/         # ai, agent, task type definitions
├── mcp/           # Model Context Protocol (stdio, HTTP, SSE transports)
├── index.ts       # Public API exports
└── factory.ts     # createDelegationFramework
```

- **Single-word file/folder names** where possible (e.g. `taskdecomposition`, `taskassignment`)
- **Max ~225 lines per file** — split into submodules if larger
- **Exports:** Public API is defined in `src/index.ts`; only export what's listed there

---

## Coding Conventions

- **Strict TypeScript:** `strict`, `noUnusedLocals`, `noUnusedParameters`, `noImplicitReturns`
- **File extensions in imports:** Use `.js` in import paths (ESM resolution)
- **Types:** Prefer `import type` for type-only imports
- **Docs:** Update `docs/` when changing public APIs or architecture

---

## Documentation

- **`docs/`** — Full framework documentation
- **`docs/README.md`** — Doc index
- **`docs/getting-started.md`** — Installation and minimal examples
- **`docs/api-reference.md`** — Exported API surface
- **`docs/types.md`** — Type definitions

Keep docs in sync with code changes.

---

## PR / Commit Guidelines

- Run `npm run build` and `npm run check` before committing
- Ensure no new `../` or `./` cross-folder imports — use `@/`
- Add or update tests if the project gains a test suite
- Update `docs/` when adding or changing public APIs

---

## Key Concepts (for context)

- **Delegation chain:** Privilege attenuation, contracts, permission narrowing
- **Complexity floor:** Bypass full pipeline for trivial tasks
- **Agent loop:** LLM execution with tool calling, budgets, monitoring
- **Protocols:** Decomposition, assignment, verification, trust, security, coordination, permissions, optimization
