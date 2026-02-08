-- Auton — Neon Postgres schema
-- Applied automatically on startup via run_migrations().

-- Enable pgvector extension for semantic memory
CREATE EXTENSION IF NOT EXISTS vector;

-- Conversation metadata
CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Individual messages within conversations
CREATE TABLE IF NOT EXISTS messages (
    id              SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT,
    name            TEXT,
    tool_call_id    TEXT,
    tool_calls      JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conv_id
    ON messages(conversation_id);

CREATE INDEX IF NOT EXISTS idx_messages_conv_created
    ON messages(conversation_id, created_at);

-- Tool call audit log
CREATE TABLE IF NOT EXISTS tool_call_logs (
    id              SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    tool_name       TEXT NOT NULL,
    arguments       JSONB NOT NULL DEFAULT '{}',
    result_text     TEXT,
    duration_ms     INTEGER,
    success         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_logs_conv_id
    ON tool_call_logs(conversation_id);

CREATE INDEX IF NOT EXISTS idx_tool_logs_tool_name
    ON tool_call_logs(tool_name);

-- LLM usage accounting / cost tracking
CREATE TABLE IF NOT EXISTS usage_logs (
    id              SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    model           TEXT NOT NULL,
    prompt_tokens   INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens   INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost            DOUBLE PRECISION,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usage_logs_conv_id
    ON usage_logs(conversation_id);

CREATE INDEX IF NOT EXISTS idx_usage_logs_model
    ON usage_logs(model);

-- Cron job definitions (managed by scheduler/service.py)
CREATE TABLE IF NOT EXISTS cron_jobs (
    id          TEXT PRIMARY KEY,
    cron_expr   TEXT NOT NULL,
    action_type TEXT NOT NULL,
    params      JSONB NOT NULL DEFAULT '{}',
    description TEXT NOT NULL DEFAULT '',
    human_desc  TEXT NOT NULL DEFAULT '',
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_run_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_cron_jobs_enabled
    ON cron_jobs(enabled);

-- Cron job execution history (for observability)
CREATE TABLE IF NOT EXISTS cron_job_runs (
    id          SERIAL PRIMARY KEY,
    job_id      TEXT NOT NULL REFERENCES cron_jobs(id) ON DELETE CASCADE,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    success     BOOLEAN,
    result      TEXT,
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_cron_runs_job_id
    ON cron_job_runs(job_id);

CREATE INDEX IF NOT EXISTS idx_cron_runs_started
    ON cron_job_runs(started_at DESC);

-- Long-term semantic memory (OpenRouter embeddings + pgvector)
CREATE TABLE IF NOT EXISTS agent_memory (
    id          SERIAL PRIMARY KEY,
    content     TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    embedding   vector(1536),
    metadata    JSONB NOT NULL DEFAULT '{}',
    source_conversation_id TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_embedding
    ON agent_memory USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_memory_category
    ON agent_memory(category);

CREATE INDEX IF NOT EXISTS idx_memory_created
    ON agent_memory(created_at DESC);

-- Agent decision logs (for observability and debugging)
CREATE TABLE IF NOT EXISTS agent_decision_logs (
    id              SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    iteration       INTEGER NOT NULL,
    event_type      TEXT NOT NULL,
    details         JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decision_logs_conv_id
    ON agent_decision_logs(conversation_id);

CREATE INDEX IF NOT EXISTS idx_decision_logs_event_type
    ON agent_decision_logs(event_type);

CREATE INDEX IF NOT EXISTS idx_decision_logs_created
    ON agent_decision_logs(created_at DESC);

-- ═══════════════════════════════════════════════════════════════
--  Multi-agent orchestration
-- ═══════════════════════════════════════════════════════════════

-- Add multi-agent tracking columns to conversations
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS parent_conversation_id TEXT;
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS agent_role TEXT;

CREATE INDEX IF NOT EXISTS idx_conversations_parent
    ON conversations(parent_conversation_id);

CREATE INDEX IF NOT EXISTS idx_conversations_agent_role
    ON conversations(agent_role);

-- Delegation tracking between orchestrator and worker agents
CREATE TABLE IF NOT EXISTS agent_delegations (
    id                      SERIAL PRIMARY KEY,
    parent_conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    child_conversation_id   TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    orchestrator_role       TEXT NOT NULL,
    worker_role             TEXT NOT NULL,
    task_instruction        TEXT NOT NULL,
    task_context            JSONB NOT NULL DEFAULT '{}',
    status                  TEXT NOT NULL DEFAULT 'pending',
    result_summary          TEXT,
    error_message           TEXT,
    iterations_used         INTEGER DEFAULT 0,
    tools_called            JSONB,
    cost                    DOUBLE PRECISION DEFAULT 0.0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at              TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_delegations_parent
    ON agent_delegations(parent_conversation_id);

CREATE INDEX IF NOT EXISTS idx_delegations_status
    ON agent_delegations(status);

CREATE INDEX IF NOT EXISTS idx_delegations_created
    ON agent_delegations(created_at DESC);
