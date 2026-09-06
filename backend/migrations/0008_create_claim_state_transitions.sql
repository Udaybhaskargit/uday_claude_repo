-- E3-S1: ClaimStateTransition table (data-models.md sec 2.8). Append-only audit trail.
CREATE TABLE claim_state_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    event TEXT NOT NULL,
    actor_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims (id)
);

CREATE INDEX idx_claim_state_transitions_claim_id_created_at
    ON claim_state_transitions (claim_id, created_at);
