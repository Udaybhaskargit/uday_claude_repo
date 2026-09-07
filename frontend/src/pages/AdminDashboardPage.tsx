// E11-S4 — admin dashboard UI. Wired to the E9-S4 admin endpoints
// (GET /api/admin/claims, GET /api/admin/payouts,
// POST /api/admin/claims/{id}/override, GET /api/admin/claims/{id}/overrides).
// Route-level access control (ADMIN-only) is handled by <RoleGuard> in
// App.tsx; this component assumes it only ever renders for an authenticated
// ADMIN actor.

import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  fetchAdminClaims,
  fetchClaimOverrides,
  fetchPayouts,
  submitOverride,
  type AdminClaimSummary,
  type AdminOverrideSummary,
  type PayoutSummary,
} from "../api/adminApi";
import { useAuth } from "../context/AuthContext";
import { AdminOverrideCommand, ClaimStatus, ClaimType } from "../types/enums";

type StatusFilter = ClaimStatus | "ALL";
type ProductFilter = ClaimType | "ALL";

export function AdminDashboardPage() {
  const { actor } = useAuth();

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [productFilter, setProductFilter] = useState<ProductFilter>("ALL");
  const [claims, setClaims] = useState<AdminClaimSummary[]>([]);
  const [claimsError, setClaimsError] = useState<string | null>(null);

  const [payouts, setPayouts] = useState<PayoutSummary[]>([]);
  const [payoutsError, setPayoutsError] = useState<string | null>(null);

  const [selectedClaimId, setSelectedClaimId] = useState<number | null>(null);
  const [overrides, setOverrides] = useState<AdminOverrideSummary[]>([]);

  const [command, setCommand] = useState<AdminOverrideCommand>(
    AdminOverrideCommand.FORCE_APPROVE,
  );
  const [reasonCode, setReasonCode] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const loadClaims = useCallback(async () => {
    if (!actor) {
      return;
    }
    setClaimsError(null);
    try {
      const response = await fetchAdminClaims(
        actor,
        statusFilter === "ALL" ? undefined : statusFilter,
        productFilter === "ALL" ? undefined : productFilter,
      );
      setClaims(response.claims);
    } catch (err) {
      setClaimsError(err instanceof Error ? err.message : "Failed to load claim queue.");
    }
  }, [actor, statusFilter, productFilter]);

  // AC1: changing either filter re-fetches and re-renders the table
  // in place -- no navigation/reload involved.
  useEffect(() => {
    void loadClaims();
  }, [loadClaims]);

  useEffect(() => {
    if (!actor) {
      return;
    }
    fetchPayouts(actor)
      .then((response) => setPayouts(response.payouts))
      .catch((err: unknown) => {
        setPayoutsError(err instanceof Error ? err.message : "Failed to load payout trail.");
      });
  }, [actor]);

  const loadOverrides = useCallback(
    async (claimId: number) => {
      if (!actor) {
        return;
      }
      const response = await fetchClaimOverrides(actor, claimId);
      setOverrides(response.overrides);
    },
    [actor],
  );

  function selectClaim(claimId: number) {
    setSelectedClaimId(claimId);
    setFormError(null);
    setSuccessMessage(null);
    void loadOverrides(claimId);
  }

  async function handleOverrideSubmit(event: FormEvent) {
    event.preventDefault();
    if (!actor || selectedClaimId === null) {
      return;
    }
    // AC3: block submission (no API call) without a reason code.
    if (!reasonCode.trim()) {
      setFormError("A reason code is required before submitting an override.");
      return;
    }
    setFormError(null);
    setSuccessMessage(null);
    setSubmitting(true);
    try {
      await submitOverride(actor, selectedClaimId, command, reasonCode.trim());
      setReasonCode("");
      setSuccessMessage(`Override recorded for claim ${selectedClaimId}.`);
      // AC4: the new override appears in the claim's audit history.
      await loadOverrides(selectedClaimId);
      await loadClaims();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to submit override.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl p-8">
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
        Internal Portal
      </p>
      <h1 className="mt-1 text-2xl font-semibold text-navy-950">Admin dashboard</h1>

      <section className="mt-8">
        <h2 className="text-lg font-semibold text-navy-950">
          Claim queue{" "}
          <span className="font-mono text-xs text-slate-500">
            GET /api/admin/claims?status=&amp;product=
          </span>
        </h2>
        <div className="mt-3 flex flex-wrap gap-4">
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
            Status
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
              className="rounded-md border border-slate-300 p-2 text-sm"
            >
              <option value="ALL">All statuses</option>
              {Object.values(ClaimStatus).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
            Product
            <select
              value={productFilter}
              onChange={(e) => setProductFilter(e.target.value as ProductFilter)}
              className="rounded-md border border-slate-300 p-2 text-sm"
            >
              <option value="ALL">All products</option>
              {Object.values(ClaimType).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
        </div>

        {claimsError && (
          <p role="alert" className="mt-3 rounded-md bg-red-100 p-3 text-sm text-red-700">
            {claimsError}
          </p>
        )}

        {claims.length === 0 ? (
          <p className="mt-4 rounded-md border border-dashed border-slate-400 bg-white p-6 text-center text-sm text-slate-700">
            No claims match the selected filters.
          </p>
        ) : (
          <div className="mt-4 overflow-x-auto rounded-md border border-slate-300">
            <table className="min-w-full divide-y divide-slate-300 text-left text-sm">
              <thead className="bg-navy-950 text-slate-300">
                <tr>
                  <th className="px-4 py-2 text-xs font-semibold uppercase">Claim</th>
                  <th className="px-4 py-2 text-xs font-semibold uppercase">Type</th>
                  <th className="px-4 py-2 text-xs font-semibold uppercase">Status</th>
                  <th className="px-4 py-2 text-xs font-semibold uppercase">Amount</th>
                  <th className="px-4 py-2 text-xs font-semibold uppercase">Updated</th>
                  <th className="px-4 py-2 text-xs font-semibold uppercase">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-300 bg-white">
                {claims.map((claim) => (
                  <tr
                    key={claim.claim_id}
                    className={
                      claim.claim_id === selectedClaimId ? "bg-amber-500/10" : undefined
                    }
                  >
                    <td className="px-4 py-2 font-medium text-navy-950">{claim.claim_id}</td>
                    <td className="px-4 py-2 text-slate-700">{claim.claim_type}</td>
                    <td className="px-4 py-2 text-slate-700">{claim.status}</td>
                    <td className="px-4 py-2 text-slate-700">{claim.claim_amount}</td>
                    <td className="px-4 py-2 text-slate-700">{claim.updated_at}</td>
                    <td className="px-4 py-2">
                      <button
                        type="button"
                        onClick={() => selectClaim(claim.claim_id)}
                        className="rounded-md border border-navy-950 px-3 py-1 text-xs font-medium text-navy-950"
                      >
                        Select for override
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="mt-10 grid gap-8 md:grid-cols-2">
        <div>
          <h2 className="text-lg font-semibold text-navy-950">
            Payout audit trail{" "}
            <span className="ml-1 rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-600">
              Read-only
            </span>
          </h2>
          <p className="mt-1 font-mono text-xs text-slate-500">GET /api/admin/payouts</p>

          {payoutsError && (
            <p role="alert" className="mt-3 rounded-md bg-red-100 p-3 text-sm text-red-700">
              {payoutsError}
            </p>
          )}

          {payouts.length === 0 ? (
            <p className="mt-4 rounded-md border border-dashed border-slate-400 bg-white p-6 text-center text-sm text-slate-700">
              No settlements recorded yet.
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto rounded-md border border-slate-300">
              <table className="min-w-full divide-y divide-slate-300 text-left text-sm">
                <thead className="bg-navy-950 text-slate-300">
                  <tr>
                    <th className="px-3 py-2 text-xs font-semibold uppercase">Created</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase">Claim</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase">Amount</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase">Reference</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-300 bg-white">
                  {payouts.map((payout) => (
                    <tr key={payout.settlement_id}>
                      <td className="px-3 py-2 text-slate-700">{payout.created_at}</td>
                      <td className="px-3 py-2 text-slate-700">{payout.claim_id}</td>
                      <td className="px-3 py-2 text-slate-700">{payout.payout_amount}</td>
                      <td className="px-3 py-2 text-slate-700">{payout.payment_reference}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div>
          <h2 className="text-lg font-semibold text-navy-950">
            Override action{" "}
            <span className="font-mono text-xs text-slate-500">
              POST /api/admin/claims/{"{id}"}/override
            </span>
          </h2>
          <div className="mt-3 rounded-md border border-slate-300 bg-white p-5">
            {selectedClaimId === null ? (
              <p className="text-sm text-slate-700">
                Select a claim from the queue above to override it.
              </p>
            ) : (
              <form onSubmit={(e) => void handleOverrideSubmit(e)} className="space-y-4">
                <p className="text-sm text-slate-700">
                  Overriding claim <strong>{selectedClaimId}</strong>.
                </p>
                <label className="block text-xs font-medium text-navy-950">
                  Command
                  <select
                    value={command}
                    onChange={(e) => setCommand(e.target.value as AdminOverrideCommand)}
                    className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-sm"
                  >
                    {Object.values(AdminOverrideCommand).map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-xs font-medium text-navy-950">
                  Reason code
                  <input
                    value={reasonCode}
                    onChange={(e) => setReasonCode(e.target.value)}
                    placeholder="e.g. Manual goodwill approval after phone review"
                    className="mt-1 block w-full rounded-md border border-slate-300 p-2 text-sm"
                  />
                </label>
                {formError && (
                  <p role="alert" className="text-xs font-semibold text-red-600">
                    {formError}
                  </p>
                )}
                {successMessage && (
                  <p className="rounded-md bg-green-100 p-2 text-xs text-green-700">
                    {successMessage}
                  </p>
                )}
                <button
                  type="submit"
                  disabled={submitting}
                  className="rounded-md bg-amber-500 px-4 py-2 text-sm font-semibold text-navy-950 disabled:opacity-50"
                >
                  Submit override
                </button>
              </form>
            )}
          </div>

          <h2 className="mt-6 text-lg font-semibold text-navy-950">
            Override history{" "}
            <span className="font-mono text-xs text-slate-500">
              GET /api/admin/claims/{"{id}"}/overrides
            </span>
          </h2>
          {selectedClaimId === null ? (
            <p className="mt-3 text-sm text-slate-700">
              Select a claim above to see its override history.
            </p>
          ) : overrides.length === 0 ? (
            <p className="mt-3 rounded-md border border-dashed border-slate-400 bg-white p-4 text-center text-sm text-slate-700">
              No overrides recorded for this claim yet.
            </p>
          ) : (
            <div className="mt-3 overflow-x-auto rounded-md border border-slate-300">
              <table className="min-w-full divide-y divide-slate-300 text-left text-sm">
                <thead className="bg-navy-950 text-slate-300">
                  <tr>
                    <th className="px-3 py-2 text-xs font-semibold uppercase">Created</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase">Admin</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase">Command</th>
                    <th className="px-3 py-2 text-xs font-semibold uppercase">Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-300 bg-white">
                  {overrides.map((override) => (
                    <tr key={override.override_id}>
                      <td className="px-3 py-2 text-slate-700">{override.created_at}</td>
                      <td className="px-3 py-2 text-slate-700">{override.admin_actor_id}</td>
                      <td className="px-3 py-2 text-slate-700">{override.command}</td>
                      <td className="px-3 py-2 text-slate-700">{override.reason_code}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
