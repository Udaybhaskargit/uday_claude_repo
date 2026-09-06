-- E3-S1: FraudScreening table (data-models.md sec 2.4). Append-only.
CREATE TABLE fraud_screenings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    breakdown TEXT NOT NULL,
    threshold INTEGER NOT NULL,
    flagged INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims (id)
);

CREATE INDEX idx_fraud_screenings_claim_id ON fraud_screenings (claim_id);
CREATE INDEX idx_fraud_screenings_claim_id_created_at
    ON fraud_screenings (claim_id, created_at);
