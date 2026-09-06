-- E3-S1: Claim table (data-models.md sec 2.2).
CREATE TABLE claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id INTEGER NOT NULL,
    claim_type TEXT NOT NULL,
    incident_date TEXT NOT NULL,
    claim_amount TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'INTAKE',
    parent_claim_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (policy_id) REFERENCES policies (id),
    FOREIGN KEY (parent_claim_id) REFERENCES claims (id)
);

CREATE INDEX idx_claims_policy_id ON claims (policy_id);
CREATE INDEX idx_claims_status ON claims (status);
CREATE INDEX idx_claims_claim_type ON claims (claim_type);
CREATE INDEX idx_claims_parent_claim_id ON claims (parent_claim_id);
CREATE INDEX idx_claims_policy_id_incident_date ON claims (policy_id, incident_date);
