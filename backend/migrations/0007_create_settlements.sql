-- E3-S1: Settlement table (data-models.md sec 2.7). Append-only, immutable.
CREATE TABLE settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    decision_id INTEGER NOT NULL,
    payout_amount TEXT NOT NULL,
    payment_reference TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims (id),
    FOREIGN KEY (decision_id) REFERENCES decisions (id)
);

CREATE INDEX idx_settlements_claim_id ON settlements (claim_id);
CREATE INDEX idx_settlements_created_at ON settlements (created_at);
