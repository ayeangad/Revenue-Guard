-- Revenue Guard schema. Postgres-compatible; SQLite fallback uses same DDL (minus enums).
CREATE TABLE IF NOT EXISTS stores (
  store_id TEXT PRIMARY KEY,
  name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS environments (
  env_id TEXT PRIMARY KEY,
  store_id TEXT NOT NULL REFERENCES stores(store_id),
  kind TEXT NOT NULL CHECK (kind IN ('dev','staging','prod'))
);
CREATE TABLE IF NOT EXISTS deployments (
  deploy_id TEXT PRIMARY KEY,
  env TEXT NOT NULL,
  version TEXT NOT NULL,
  sha TEXT NOT NULL,
  component TEXT NOT NULL,
  t_offset_s REAL NOT NULL,
  state TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS incidents (
  incident_id TEXT PRIMARY KEY,
  store_id TEXT NOT NULL,
  journey TEXT NOT NULL,
  state TEXT NOT NULL,
  started_at TEXT,
  diagnosis TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY,
  incident_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  tool_args_hash TEXT NOT NULL DEFAULT '',
  observed_at TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  extracted_claim TEXT NOT NULL,
  reliability TEXT NOT NULL DEFAULT 'medium'
);
-- Idempotency: one row per (idempotency_key); repeats return stored result.
CREATE TABLE IF NOT EXISTS agent_actions (
  idempotency_key TEXT PRIMARY KEY,
  action TEXT NOT NULL,
  target TEXT NOT NULL,
  result TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY,
  incident_id TEXT NOT NULL,
  summary TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','APPROVED','REJECTED')),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS validation_runs (
  validation_id TEXT PRIMARY KEY,
  incident_id TEXT NOT NULL,
  passed INTEGER NOT NULL,
  detail TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS investigation_runs (
  run_id TEXT PRIMARY KEY,
  incident_id TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_v TEXT NOT NULL,
  tool_calls INTEGER NOT NULL DEFAULT 0,
  outcome TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
