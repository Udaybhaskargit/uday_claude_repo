-- E3-S1: Decision table (data-models.md sec 2.6). Append-only.
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims (id)
);

CREATE INDEX idx_decisions_claim_id_created_at ON decisions (claim_id, created_at);
