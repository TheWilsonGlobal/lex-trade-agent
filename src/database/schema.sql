-- ============================================================================
-- Lex-Trade-Agent Persistent Compliance Memory Database Schema (SQLite)
-- ============================================================================

-- Table: episodes
-- Records complete historical compliance audit episodes for semantic lookup and precedent reuse.
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shipment_id TEXT NOT NULL,
    query_text TEXT NOT NULL,
    action_plan TEXT,              -- JSON serialized list of reasoning steps
    tool_calls TEXT,               -- JSON serialized list of executed tool invocations & results
    verdict TEXT,                  -- JSON serialized final compliance determination summary
    risk_level TEXT NOT NULL,      -- 'LOW', 'MEDIUM', 'DUAL_USE_RESTRICTED', 'CRITICAL_HIGH'
    created_at REAL NOT NULL       -- Unix timestamp
);

-- Indexes for rapid lookup by shipment identifier and risk category
CREATE INDEX IF NOT EXISTS idx_episodes_shipment_id ON episodes (shipment_id);
CREATE INDEX IF NOT EXISTS idx_episodes_risk_level ON episodes (risk_level);
CREATE INDEX IF NOT EXISTS idx_episodes_created_at ON episodes (created_at);

-- Table: audit_logs
-- Immutable step-by-step telemetry audit trail ensuring non-repudiation and regulatory accountability.
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shipment_id TEXT NOT NULL,
    step_name TEXT NOT NULL,       -- e.g. 'tool_screen_entity', 'tool_lookup_hs_code'
    payload TEXT NOT NULL,         -- JSON serialized input arguments and output results
    timestamp REAL NOT NULL        -- Unix timestamp
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_shipment_id ON audit_logs (shipment_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs (timestamp);
