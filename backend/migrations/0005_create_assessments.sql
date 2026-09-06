-- E3-S1: Assessment table (data-models.md sec 2.5). Append-only.
CREATE TABLE assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    claim_amount TEXT NOT NULL,
    sum_insured TEXT NOT NULL,
    deductible TEXT NOT NULL,
    co_pay TEXT NOT NULL,
    payable_amount TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims (id)
);

CREATE INDEX idx_assessments_claim_id_created_at ON assessments (claim_id, created_at);
