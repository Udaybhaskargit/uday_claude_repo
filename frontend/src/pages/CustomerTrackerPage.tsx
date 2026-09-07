// E10-S2: claim tracker read model, wired to GET /api/claims/{id} (E9-S1).
// E10-S3: dispute action (reopen a SETTLED claim), wired to POST
// /api/claims/{id}/reopen -- lives on this page since the "Dispute this
// claim" button only ever appears on a claim's own tracker view.

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { fetchClaim, reopenClaim, type ClaimDetailResponse } from "../api/claimsApi";
import { ApiError } from "../api/httpClient";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ReasonCodeText } from "../components/ReasonCodeText";
import { StatusBadge } from "../components/StatusBadge";
import { useAuth } from "../context/AuthContext";
import { DOCUMENT_CHECKLISTS } from "../constants/documentChecklists";
import { ClaimStatus } from "../types/enums";

export function CustomerTrackerPage() {
  const { claimId } = useParams<{ claimId: string }>();
  const { actor } = useAuth();

  const [claim, setClaim] = useState<ClaimDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [disputeSubmitting, setDisputeSubmitting] = useState(false);
  const [disputeError, setDisputeError] = useState<string | null>(null);
  const [subClaimId, setSubClaimId] = useState<number | null>(null);

  const load = useCallback(() => {
    if (!actor || !claimId) {
      return;
    }
    setLoading(true);
    setLoadError(null);
    fetchClaim(actor, Number(claimId))
      .then(setClaim)
      .catch(() => setLoadError("Could not load this claim. Please try again."))
      .finally(() => setLoading(false));
  }, [actor, claimId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleConfirmDispute() {
    if (!actor || !claim) {
      return;
    }
    setConfirmOpen(false);
    setDisputeSubmitting(true);
    setDisputeError(null);
    try {
      const response = await reopenClaim(actor, claim.claim_id);
      setSubClaimId(response.sub_claim_id);
    } catch (err) {
      setDisputeError(
        err instanceof ApiError
          ? err.message
          : "Could not submit the dispute. Please try again.",
      );
      // The claim itself is re-read from `claim` state, which was never
      // touched by this failed call, so its displayed status is unchanged.
    } finally {
      setDisputeSubmitting(false);
    }
  }

  if (loading) {
    return <p className="mx-auto max-w-2xl p-8 text-sm text-slate-700">Loading…</p>;
  }

  if (loadError || !claim) {
    return (
      <p role="alert" className="mx-auto max-w-2xl p-8 text-sm text-red-700">
        {loadError ?? "Claim not found."}
      </p>
    );
  }

  const fullChecklist = DOCUMENT_CHECKLISTS[claim.claim_type];
  const outstanding = new Set(claim.missing_documents);

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      <h1 className="text-xl font-semibold text-navy-950">
        Claim #{claim.claim_id}
      </h1>
      <div className="mt-2">
        <StatusBadge status={claim.status} />
      </div>

      <dl className="mt-6 grid grid-cols-2 gap-4 text-sm">
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Claim type</dt>
          <dd className="text-navy-950">{claim.claim_type}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Incident date</dt>
          <dd className="text-navy-950">{claim.incident_date}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Claim amount</dt>
          <dd className="text-navy-950">{claim.claim_amount}</dd>
        </div>
      </dl>

      <section className="mt-6">
        <h2 className="text-sm font-semibold text-navy-950">Documents</h2>
        <ul className="mt-2 divide-y divide-slate-200 rounded-md border border-slate-300">
          {fullChecklist.map((doc) => {
            const isOutstanding = outstanding.has(doc.type);
            return (
              <li
                key={doc.type}
                className="flex items-center justify-between px-3 py-2 text-sm"
              >
                <span className="text-navy-950">{doc.label}</span>
                <span
                  className={
                    isOutstanding
                      ? "font-medium text-amber-600"
                      : "font-medium text-green-700"
                  }
                >
                  {isOutstanding ? "Outstanding" : "Verified"}
                </span>
              </li>
            );
          })}
        </ul>
      </section>

      {claim.decision && (
        <section className="mt-6 rounded-md border border-slate-300 bg-white p-4">
          <h2 className="text-sm font-semibold text-navy-950">Decision</h2>
          <p className="mt-1 text-sm text-navy-950">
            {claim.decision.outcome} &middot; {claim.decision.reason_code}
          </p>
          <p className="mt-1 text-sm text-slate-700">
            <ReasonCodeText code={claim.decision.reason_code as never} />
          </p>
        </section>
      )}

      {claim.settlement && (
        <section className="mt-6 rounded-md border border-green-200 bg-green-50 p-4">
          <h2 className="text-sm font-semibold text-navy-950">Payout</h2>
          <p className="mt-1 text-2xl font-semibold text-green-700">
            {claim.settlement.payout_amount}
          </p>
          <p className="mt-1 font-mono text-xs text-slate-500">
            {claim.settlement.payment_reference}
          </p>
        </section>
      )}

      {claim.status === ClaimStatus.SETTLED && subClaimId === null && (
        <button
          type="button"
          onClick={() => setConfirmOpen(true)}
          disabled={disputeSubmitting}
          className="mt-6 rounded-md bg-red-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-red-500 disabled:opacity-60"
        >
          Dispute this claim
        </button>
      )}

      {disputeError && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {disputeError}
        </p>
      )}

      {subClaimId !== null && (
        <p className="mt-6 rounded-md border border-slate-300 bg-white p-4 text-sm text-navy-950">
          Dispute filed as claim #{subClaimId}.{" "}
          <Link to={`/claims/${subClaimId}`} className="font-medium text-amber-600 hover:underline">
            Track it here
          </Link>
        </p>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="Dispute this claim?"
        message="This will open a new sub-claim linked to this one for review. This claim's own record will not be changed."
        confirmLabel="Yes, dispute"
        onConfirm={handleConfirmDispute}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
