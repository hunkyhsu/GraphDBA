--- 1. Alerts Table (16 fields)
CREATE TABLE IF NOT EXISTS alerts (
    alert_id UUID PRIMARY KEY,
    fingerprint TEXT NOT NULL,

    alertname TEXT NOT NULL,
    severity TEXT NOT NULL,
    instance TEXT,
    alert_summary TEXT NOT NULL,
    description TEXT,

    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,

    status TEXT DEFAULT 'RECEIVED' NOT NULL CHECK (
        status IN (
            'RECEIVED',
            'RUNNING',
            'WAITING_APPROVAL',
            'SOLVED',
            'RESOLVED',
            'ESCALATED',
            'FAILED'
        )
    ) ,

    escalation_reason TEXT,
    failure_reason TEXT,

    started_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    solved_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX idx_alerts_unique_active_fingerprint
ON alerts(fingerprint)
WHERE status NOT IN ('SOLVED', 'FAILED', 'ESCALATED');

--- 2. Hypotheses Table
CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id TEXT PRIMARY KEY,

    alert_id UUID NOT NULL REFERENCES alerts(alert_id) ON DELETE CASCADE,
    attempt_count INTEGER NOT NULL,

    root_cause TEXT NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL CHECK (
        confidence_score >= 0.0 AND confidence_score <= 1.0
    ),

    validation_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    expected_result TEXT NOT NULL,

    status TEXT NOT NULL CHECK (
        status IN (
            'pending',
            'verified',
            'rejected',
            'inconclusive'
        )
    ),

    feedback TEXT,
    metric_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    validated_at TIMESTAMPTZ
);

--- 3. Ticket Table
CREATE TABLE IF NOT EXISTS change_tickets (

    ticket_id UUID PRIMARY KEY,
    alert_id UUID NOT NULL REFERENCES alerts(alert_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    proposed_steps JSONB NOT NULL DEFAULT '{}'::jsonb,
    approved_steps JSONB,
    change_reason TEXT NOT NULL,
    rollback_sql TEXT,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),

    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    approval_comments TEXT,

    executed_at TIMESTAMPTZ,
    execution_duration_ms INTEGER,
    rollbacked_at TIMESTAMPTZ,
    error_message TEXT,

    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED', 'REJECTED', 'EXECUTING','SUCCESS','FAILED','ROLLED_BACK')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);