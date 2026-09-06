-- E3-S1: AdminOverride table (data-models.md sec 2.9). Append-only audit trail.
CREATE TABLE admin_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    admin_actor_id TEXT NOT NULL,
    command TEXT NOT NULL,
    reason_code TEXT NOT NULL CHECK (length(reason_code) >= 1),
    created_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims (id)
);

CREATE INDEX idx_admin_overrides_claim_id_created_at
    ON admin_overrides (claim_id, created_at);
