// Mirrors backend/src/services/fnol_intake_service.py's CHECKLISTS mapping
// exactly (POLICE_FIR/INVOICE for MOTOR, HOSPITAL_BILL/DISCHARGE_SUMMARY for
// HEALTH, DEATH_CERTIFICATE for LIFE) -- the backend only ever returns the
// *outstanding* subset via `missing_documents`, so the UI needs its own copy
// of the full per-type checklist to compute which items are verified.

import { ClaimType, DocumentType } from "../types/enums";

export interface ChecklistDoc {
  type: DocumentType;
  label: string;
}

export const DOCUMENT_CHECKLISTS: Record<ClaimType, ChecklistDoc[]> = {
  [ClaimType.MOTOR]: [
    { type: DocumentType.POLICE_FIR, label: "Police FIR" },
    { type: DocumentType.INVOICE, label: "Repair invoice" },
  ],
  [ClaimType.HEALTH]: [
    { type: DocumentType.HOSPITAL_BILL, label: "Hospital bill" },
    { type: DocumentType.DISCHARGE_SUMMARY, label: "Discharge summary" },
  ],
  [ClaimType.LIFE]: [{ type: DocumentType.DEATH_CERTIFICATE, label: "Death certificate" }],
};
