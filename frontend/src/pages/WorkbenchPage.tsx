// E11-S3: assessor workbench detail + decision form, wired to
// GET /api/claims/{id}/workbench and POST /api/claims/{id}/decision (E9-S3).

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { fetchWorkbenchDetail, submitDecision, type WorkbenchDetailResponse } from "../api/workbenchApi";
import { ApiError } from "../api/httpClient";
import { useAuth } from "../context/AuthContext";
import { DecisionOutcome, ReasonCode } from "../types/enums";

export function WorkbenchPage() {
  const { claimId } = useParams<{ claimId: string }>();
  const { actor } = useAuth();

  const [detail, setDetail] = useState<WorkbenchDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [outcome, setOutcome] = useState<DecisionOutcome | "">("");
  const [reasonCode, setReasonCode] = useState<ReasonCode | "">("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [decided, setDecided] = useState(false);

  const load = useCallback(() => {
    if (!actor || !claimId) {
      return;
    }
    setLoading(true);
    setLoadError(null);
    fetchWorkbenchDetail(actor, Number(claimId))
      .then((response) => {
        setDetail(response);
        if (response.suggested_reason_code) {
          setReasonCode(response.suggested_reason_code);
        }
      })
      .catch(() => setLoadError("Could not load this claim's workbench detail."))
      .finally(() => setLoading(false));
  }, [actor, claimId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!actor || !detail) {
      return;
    }
    setSubmitError(null);

    if (!outcome) {
      setValidationError("Select an outcome before submitting.");
      return;
    }
    if (!reasonCode) {
      setValidationError("Select a reason code before submitting.");
      return;
    }
    setValidationError(null);

    setSubmitting(true);
    try {
      await submitDecision(actor, detail.claim_id, { outcome, reason_code: reasonCode });
      // The claim is no longer awaiting a decision -- remove it from this
      // (single-claim) pending view rather than re-fetching a now-decided
      // detail the decision form has no use for.
      setDecided(true);
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.message : "Could not submit the decision. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <p className="mx-auto max-w-3xl p-8 text-sm text-slate-700">Loading…</p>;
  }

  if (loadError || !detail) {
    return (
      <p role="alert" className="mx-auto max-w-3xl p-8 text-sm text-red-700">
        {loadError ?? "Claim not found."}
      </p>
    );
  }

  if (decided) {
    return (
      <div className="mx-auto max-w-3xl p-4 sm:p-8">
        <p role="status" className="rounded-md border border-green-200 bg-green-50 p-4 text-sm text-green-800">
          Decision submitted for claim #{detail.claim_id}. It has been removed from your
          pending workbench.
        </p>
        <Link to="/fraud-alerts" className="mt-4 inline-block text-sm font-medium text-amber-600 hover:underline">
          Back to fraud alert queue
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl p-4 sm:p-8">
      <h1 className="text-xl font-semibold text-navy-950">
        Assessor workbench &middot; Claim #{detail.claim_id}
      </h1>

      {detail.fraud_screening && (
        <section className="mt-6 rounded-md border border-slate-300 bg-white p-4">
          <h2 className="text-sm font-semibold text-navy-950">Fraud screening</h2>
          <p className="mt-1 text-sm text-navy-950">
            Score {detail.fraud_screening.score} / threshold {detail.fraud_screening.threshold}
            {detail.fraud_screening.flagged ? " (flagged)" : ""}
          </p>
          <ul className="mt-2 divide-y divide-slate-200">
            {detail.fraud_screening.breakdown.map((rule) => (
              <li key={rule.rule_name} className="flex justify-between py-1 text-sm">
                <span>{rule.rule_name}</span>
                <span>+{rule.weight}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {detail.assessment && (
        <section className="mt-6 rounded-md border border-slate-300 bg-white p-4">
          <h2 className="text-sm font-semibold text-navy-950">Assessment</h2>
          <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">Payable amount</p>
          <p className="text-2xl font-semibold text-green-700">
            {detail.assessment.payable_amount}
          </p>
          <dl className="mt-2 space-y-1 text-sm">
            <div className="flex justify-between border-b border-slate-100 py-1">
              <dt>Claim amount</dt>
              <dd>{detail.assessment.claim_amount}</dd>
            </div>
            <div className="flex justify-between border-b border-slate-100 py-1">
              <dt>Deductible</dt>
              <dd>-{detail.assessment.deductible}</dd>
            </div>
            <div className="flex justify-between py-1">
              <dt>Co-pay</dt>
              <dd>-{detail.assessment.co_pay}</dd>
            </div>
          </dl>
        </section>
      )}

      <form onSubmit={handleSubmit} noValidate className="mt-6 rounded-md border border-slate-300 bg-white p-4">
        <h2 className="text-sm font-semibold text-navy-950">Submit decision</h2>

        <fieldset className="mt-3">
          <legend className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Outcome
          </legend>
          <div className="mt-2 flex gap-2">
            {Object.values(DecisionOutcome).map((value) => (
              <label
                key={value}
                className={`flex-1 cursor-pointer rounded-md border px-3 py-2 text-center text-xs font-semibold ${
                  outcome === value
                    ? "border-navy-950 bg-navy-950 text-white"
                    : "border-slate-300 bg-white text-navy-800"
                }`}
              >
                <input
                  type="radio"
                  name="outcome"
                  value={value}
                  checked={outcome === value}
                  onChange={() => setOutcome(value)}
                  className="sr-only"
                />
                {value}
              </label>
            ))}
          </div>
        </fieldset>

        <label className="mt-4 block text-xs font-medium uppercase tracking-wide text-slate-500">
          Reason code
          <select
            value={reasonCode}
            onChange={(e) => setReasonCode(e.target.value as ReasonCode)}
            className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-sm text-navy-950"
          >
            <option value="">Select a reason code</option>
            {Object.values(ReasonCode).map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>

        {validationError && (
          <p role="alert" className="mt-3 text-sm text-red-700">
            {validationError}
          </p>
        )}
        {submitError && (
          <p role="alert" className="mt-3 text-sm text-red-700">
            {submitError}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="mt-4 w-full rounded-md bg-amber-500 px-4 py-2.5 text-sm font-semibold text-navy-950 hover:bg-amber-400 disabled:opacity-60"
        >
          {submitting ? "Submitting…" : "Submit decision"}
        </button>
      </form>
    </div>
  );
}
