// E11-S2: fraud alert queue, wired to GET /api/claims/fraud-alerts (E9-S3).

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiRequest } from "../api/httpClient";
import { QueueTable } from "../components/QueueTable";
import { useAuth } from "../context/AuthContext";

interface FraudAlertClaim {
  claim_id: number;
  claim_type: string;
  fraud_score: number;
  triggered_rules: string[];
}

interface FraudAlertsResponse {
  claims: FraudAlertClaim[];
}

export function FraudQueuePage() {
  const { actor } = useAuth();
  const [claims, setClaims] = useState<FraudAlertClaim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!actor) {
      return;
    }
    setLoading(true);
    setError(null);
    apiRequest<FraudAlertsResponse>("/api/claims/fraud-alerts", { actor })
      .then((response) => setClaims(response.claims))
      .catch(() => setError("Could not load the fraud alert queue. Please try again."))
      .finally(() => setLoading(false));
  }, [actor]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-4xl p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-navy-950">Fraud alert queue</h1>
        <button
          type="button"
          onClick={load}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-navy-950 hover:bg-slate-100"
        >
          Refresh
        </button>
      </div>

      {loading && <p className="mt-4 text-sm text-slate-700">Loading…</p>}
      {error && (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      )}

      {!loading && !error && (
        <div className="mt-4">
          <QueueTable
            rows={claims}
            rowKey={(row) => row.claim_id}
            emptyMessage="No claims are currently flagged by fraud screening."
            columns={[
              { header: "Claim", render: (row) => `#${row.claim_id} (${row.claim_type})` },
              { header: "Fraud score", render: (row) => row.fraud_score },
              {
                header: "Triggered rules",
                render: (row) =>
                  row.triggered_rules.length > 0 ? row.triggered_rules.join(", ") : "—",
              },
              {
                header: "",
                render: (row) => (
                  <Link
                    to={`/workbench/${row.claim_id}`}
                    className="font-medium text-amber-600 hover:underline"
                  >
                    Open workbench
                  </Link>
                ),
              },
            ]}
          />
        </div>
      )}
    </div>
  );
}
