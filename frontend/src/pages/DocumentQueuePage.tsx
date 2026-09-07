// E11-S1 — document verification queue UI. Wired to the E9-S2 endpoints
// (GET /api/claims/documents/pending, PATCH /api/claims/{id}/documents/{type}).
// Route-level access control (ASSESSOR/ADMIN only, CUSTOMER denied) is
// handled by <RoleGuard> in App.tsx (AC3); this component assumes it only
// ever renders for an authenticated ASSESSOR/ADMIN actor.

import { useCallback, useEffect, useState } from "react";

import {
  fetchPendingDocuments,
  verifyDocument,
  type PendingDocsClaim,
} from "../api/documentsApi";
import { useAuth } from "../context/AuthContext";
import { ClaimType, type DocumentType } from "../types/enums";

type ClaimTypeFilter = ClaimType | "ALL";

const FILTERS: Array<{ label: string; value: ClaimTypeFilter }> = [
  { label: "All types", value: "ALL" },
  { label: "Motor", value: ClaimType.MOTOR },
  { label: "Health", value: ClaimType.HEALTH },
  { label: "Life", value: ClaimType.LIFE },
];

function pendingKey(claimId: number, documentType: DocumentType): string {
  return `${claimId}:${documentType}`;
}

export function DocumentQueuePage() {
  const { actor } = useAuth();
  const [filter, setFilter] = useState<ClaimTypeFilter>("ALL");
  const [claims, setClaims] = useState<PendingDocsClaim[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    if (!actor) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetchPendingDocuments(
        actor,
        filter === "ALL" ? undefined : filter,
      );
      setClaims(response.claims);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the document queue.");
    } finally {
      setLoading(false);
    }
  }, [actor, filter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleVerify(claimId: number, documentType: DocumentType) {
    if (!actor) {
      return;
    }
    const key = pendingKey(claimId, documentType);
    setVerifying((prev) => new Set(prev).add(key));
    setError(null);
    try {
      await verifyDocument(actor, claimId, documentType);
      // AC2: a claim with its last outstanding item verified drops off the
      // queue "on the next refresh" -- re-run the GET immediately.
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to verify document.");
    } finally {
      setVerifying((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  }

  return (
    <div className="mx-auto max-w-5xl p-8">
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
        Internal Portal
      </p>
      <h1 className="mt-1 text-2xl font-semibold text-navy-950">
        Document verification queue
      </h1>
      <p className="mt-1 font-mono text-xs text-slate-500">
        GET /api/claims/documents/pending
      </p>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Filter by claim type" className="flex gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              aria-pressed={filter === f.value}
              onClick={() => setFilter(f.value)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
                filter === f.value
                  ? "border-navy-950 bg-navy-950 text-white"
                  : "border-slate-300 bg-white text-navy-800"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-md bg-amber-500 px-4 py-2 text-sm font-semibold text-navy-950"
        >
          Refresh queue
        </button>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-md bg-red-100 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {loading && claims.length === 0 ? (
        <p className="mt-6 text-sm text-slate-700">Loading queue…</p>
      ) : claims.length === 0 ? (
        <p className="mt-6 rounded-md border border-dashed border-slate-400 bg-white p-8 text-center text-sm text-slate-700">
          No claims currently in DOCS_PENDING for this filter.
        </p>
      ) : (
        <div className="mt-6 overflow-x-auto rounded-md border border-slate-300">
          <table className="min-w-full divide-y divide-slate-300 text-left text-sm">
            <thead className="bg-navy-950 text-slate-300">
              <tr>
                <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wide">
                  Claim
                </th>
                <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wide">
                  Type
                </th>
                <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wide">
                  Outstanding documents
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-300 bg-white">
              {claims.map((claim) => (
                <tr key={claim.claim_id}>
                  <td className="px-4 py-3 align-top font-medium text-navy-950">
                    {claim.claim_id}
                  </td>
                  <td className="px-4 py-3 align-top text-slate-700">{claim.claim_type}</td>
                  <td className="px-4 py-3 align-top">
                    <div className="flex flex-wrap gap-2">
                      {claim.outstanding_documents.map((docType) => {
                        const key = pendingKey(claim.claim_id, docType);
                        return (
                          <button
                            key={docType}
                            type="button"
                            disabled={verifying.has(key)}
                            onClick={() => void handleVerify(claim.claim_id, docType)}
                            className="rounded-full border border-slate-300 bg-slate-100 px-3 py-1 text-xs text-navy-800 disabled:opacity-50"
                          >
                            Mark {docType.replaceAll("_", " ")} verified
                          </button>
                        );
                      })}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
