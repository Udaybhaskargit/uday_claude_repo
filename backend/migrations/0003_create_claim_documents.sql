-- E3-S1: ClaimDocument table (data-models.md sec 2.3).
CREATE TABLE claim_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    document_type TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'MISSING',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES claims (id)
);

CREATE INDEX idx_claim_documents_claim_id ON claim_documents (claim_id);
CREATE UNIQUE INDEX idx_claim_documents_claim_id_document_type
    ON claim_documents (claim_id, document_type);
