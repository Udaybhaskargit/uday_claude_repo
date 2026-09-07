// E10-S1: FNOL submission form, wired to POST /api/claims (E9-S1).

import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { submitFnol } from "../api/claimsApi";
import { ApiError } from "../api/httpClient";
import { useAuth } from "../context/AuthContext";
import { DOCUMENT_CHECKLISTS } from "../constants/documentChecklists";
import { ClaimType } from "../types/enums";

interface FieldErrors {
  policyNumber?: string;
  incidentDate?: string;
  claimAmount?: string;
}

export function CustomerFnolPage() {
  const { actor } = useAuth();
  const navigate = useNavigate();

  const [policyNumber, setPolicyNumber] = useState("");
  const [incidentDate, setIncidentDate] = useState("");
  const [claimType, setClaimType] = useState<ClaimType>(ClaimType.MOTOR);
  const [claimAmount, setClaimAmount] = useState("");
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const checklist = useMemo(() => DOCUMENT_CHECKLISTS[claimType], [claimType]);

  function validate(): FieldErrors {
    const errors: FieldErrors = {};
    if (!policyNumber.trim()) {
      errors.policyNumber = "Policy number is required.";
    }
    if (!incidentDate.trim()) {
      errors.incidentDate = "Incident date is required.";
    }
    const amount = Number(claimAmount);
    if (!claimAmount.trim() || Number.isNaN(amount) || amount <= 0) {
      errors.claimAmount = "Enter a claim amount greater than zero.";
    }
    return errors;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!actor) {
      return;
    }
    setApiError(null);

    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      return;
    }

    setSubmitting(true);
    try {
      const response = await submitFnol(actor, {
        policy_number: policyNumber.trim(),
        claim_type: claimType,
        incident_date: incidentDate,
        // Sent as the raw validated string, not round-tripped through
        // Number(), to match the project's Decimal-as-string discipline for
        // money (the backend parses this directly via Decimal(...)).
        claim_amount: claimAmount.trim(),
      });
      navigate(`/claims/${response.claim_id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setApiError(err.message);
      } else {
        setApiError("Could not submit the claim. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl p-4 sm:p-8">
      <h1 className="text-xl font-semibold text-navy-950">File a new claim</h1>
      <p className="mt-1 text-sm text-slate-700">POST /api/claims</p>

      <form onSubmit={handleSubmit} noValidate className="mt-6 space-y-5">
        <div className="field">
          <label htmlFor="policy_number" className="block text-sm font-medium text-navy-950">
            Policy number
          </label>
          <input
            id="policy_number"
            value={policyNumber}
            onChange={(e) => setPolicyNumber(e.target.value)}
            placeholder="POL-MOTOR-0001"
            className="mt-1 block w-full rounded-md border border-slate-300 p-2"
          />
          {fieldErrors.policyNumber && (
            <p role="alert" className="mt-1 text-xs text-red-700">
              {fieldErrors.policyNumber}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor="incident_date" className="block text-sm font-medium text-navy-950">
            Incident date
          </label>
          <input
            id="incident_date"
            type="date"
            value={incidentDate}
            onChange={(e) => setIncidentDate(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 p-2"
          />
          {fieldErrors.incidentDate && (
            <p role="alert" className="mt-1 text-xs text-red-700">
              {fieldErrors.incidentDate}
            </p>
          )}
        </div>

        <fieldset className="field">
          <legend className="block text-sm font-medium text-navy-950">Claim type</legend>
          <div className="mt-1 flex flex-wrap gap-2">
            {Object.values(ClaimType).map((type) => (
              <label
                key={type}
                className={`cursor-pointer rounded-full border px-3 py-1.5 text-xs font-medium ${
                  claimType === type
                    ? "border-navy-950 bg-navy-950 text-white"
                    : "border-slate-300 bg-white text-navy-800"
                }`}
              >
                <input
                  type="radio"
                  name="claim_type"
                  value={type}
                  checked={claimType === type}
                  onChange={() => setClaimType(type)}
                  className="sr-only"
                />
                {type.charAt(0) + type.slice(1).toLowerCase()}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="field">
          <label htmlFor="claim_amount" className="block text-sm font-medium text-navy-950">
            Claim amount (INR)
          </label>
          <input
            id="claim_amount"
            type="number"
            step="0.01"
            min="0"
            value={claimAmount}
            onChange={(e) => setClaimAmount(e.target.value)}
            placeholder="40000.00"
            className="mt-1 block w-full rounded-md border border-slate-300 p-2"
          />
          {fieldErrors.claimAmount && (
            <p role="alert" className="mt-1 text-xs text-red-700">
              {fieldErrors.claimAmount}
            </p>
          )}
        </div>

        <fieldset className="rounded-md border border-slate-300 p-4">
          <legend className="px-1 text-sm font-medium text-navy-950">
            Documents you&rsquo;ll need
          </legend>
          <p className="text-xs text-slate-500">
            Presentational self-check only -- the server generates this checklist
            after your claim is created.
          </p>
          <div className="mt-3 divide-y divide-slate-200">
            {checklist.map((item) => (
              <label
                key={item.type}
                className="flex items-center justify-between gap-3 py-2"
              >
                <span>
                  <span className="text-sm text-navy-950">{item.label}</span>{" "}
                  <span className="font-mono text-xs text-slate-500">{item.type}</span>
                </span>
                <input
                  type="checkbox"
                  checked={!!checked[item.type]}
                  onChange={(e) =>
                    setChecked((prev) => ({ ...prev, [item.type]: e.target.checked }))
                  }
                />
              </label>
            ))}
          </div>
        </fieldset>

        {apiError && (
          <p role="alert" className="text-sm text-red-700">
            {apiError}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-amber-500 px-4 py-2.5 text-sm font-semibold text-navy-950 hover:bg-amber-400 disabled:opacity-60"
        >
          {submitting ? "Submitting…" : "Submit claim"}
        </button>
      </form>
    </div>
  );
}
