-- E3-S1: Policy table (data-models.md sec 2.1).
CREATE TABLE policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_number TEXT NOT NULL,
    product_type TEXT NOT NULL,
    status TEXT NOT NULL,
    sum_insured TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    expiry_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_policies_policy_number ON policies (policy_number);
CREATE INDEX idx_policies_status ON policies (status);
