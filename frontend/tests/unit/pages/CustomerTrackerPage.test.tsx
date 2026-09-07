import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as claimsApi from "../../../src/api/claimsApi";
import { CustomerTrackerPage } from "../../../src/pages/CustomerTrackerPage";
import { Role } from "../../../src/types/enums";
import { renderWithActor } from "../../utils/renderWithActor";

vi.mock("../../../src/api/claimsApi");

const mockedFetchClaim = vi.mocked(claimsApi.fetchClaim);
const mockedReopenClaim = vi.mocked(claimsApi.reopenClaim);

afterEach(() => {
  vi.clearAllMocks();
});

function renderTracker(claimId = "4231") {
  return render(
    <MemoryRouter initialEntries={[`/claims/${claimId}`]}>
      <Routes>
        <Route
          path="/claims/:claimId"
          element={renderWithActor(Role.CUSTOMER, "cust-1001", <CustomerTrackerPage />)}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("CustomerTrackerPage", () => {
  it("F111/AC1: lists each outstanding document type distinctly from verified ones", async () => {
    mockedFetchClaim.mockResolvedValue({
      claim_id: 4231,
      claim_type: "MOTOR",
      status: "DOCS_PENDING",
      incident_date: "2026-03-10",
      claim_amount: "42500.00",
      missing_documents: ["POLICE_FIR"],
      decision: null,
      settlement: null,
      parent_claim_id: null,
    });

    renderTracker();

    const policeFirRow = (await screen.findByText("Police FIR")).closest("li");
    expect(policeFirRow).toHaveTextContent("Outstanding");

    const invoiceRow = screen.getByText("Repair invoice").closest("li");
    expect(invoiceRow).toHaveTextContent("Verified");
  });

  it("F112/AC2: shows human-readable reason text, not just the raw code", async () => {
    mockedFetchClaim.mockResolvedValue({
      claim_id: 4287,
      claim_type: "MOTOR",
      status: "MANUAL_REVIEW",
      incident_date: "2026-03-10",
      claim_amount: "75000.00",
      missing_documents: [],
      decision: {
        outcome: "MANUAL_REVIEW",
        reason_code: "HIGH_VALUE_REVIEW",
        decided_by: "system",
        created_at: "2026-03-11T09:04:00Z",
      },
      settlement: null,
      parent_claim_id: null,
    });

    renderTracker("4287");

    expect(await screen.findByText("HIGH_VALUE_REVIEW", { exact: false })).toBeInTheDocument();
    expect(
      screen.getByText(/sent for manual review due to the claim's high value/i),
    ).toBeInTheDocument();
  });

  it("F113/AC3: a SETTLED claim shows the payout amount and a Dispute this claim action", async () => {
    mockedFetchClaim.mockResolvedValue({
      claim_id: 4106,
      claim_type: "HEALTH",
      status: "SETTLED",
      incident_date: "2026-03-10",
      claim_amount: "20000.00",
      missing_documents: [],
      decision: {
        outcome: "AUTO_APPROVE",
        reason_code: "AUTO_APPROVED_LOW_RISK",
        decided_by: "system",
        created_at: "2026-03-11T09:04:00Z",
      },
      settlement: {
        payout_amount: "17100.00",
        payment_reference: "STUB-PAY-0000004106-01",
        created_at: "2026-03-12T09:00:00Z",
      },
      parent_claim_id: null,
    });

    renderTracker("4106");

    expect(await screen.findByText("17100.00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /dispute this claim/i })).toBeInTheDocument();
  });

  it("F114/AC4: a non-SETTLED claim shows no dispute action", async () => {
    mockedFetchClaim.mockResolvedValue({
      claim_id: 4390,
      claim_type: "HEALTH",
      status: "DOCS_PENDING",
      incident_date: "2026-03-10",
      claim_amount: "18000.00",
      missing_documents: ["HOSPITAL_BILL", "DISCHARGE_SUMMARY"],
      decision: null,
      settlement: null,
      parent_claim_id: null,
    });

    renderTracker("4390");

    await screen.findByText("Claim #4390");
    expect(
      screen.queryByRole("button", { name: /dispute this claim/i }),
    ).not.toBeInTheDocument();
  });

  it("F115/AC1 (E10-S3): clicking Dispute this claim shows a confirmation dialog before any API call", async () => {
    mockedFetchClaim.mockResolvedValue({
      claim_id: 4106,
      claim_type: "HEALTH",
      status: "SETTLED",
      incident_date: "2026-03-10",
      claim_amount: "20000.00",
      missing_documents: [],
      decision: null,
      settlement: {
        payout_amount: "17100.00",
        payment_reference: "STUB-PAY-0000004106-01",
        created_at: "2026-03-12T09:00:00Z",
      },
      parent_claim_id: null,
    });

    renderTracker("4106");
    fireEvent.click(await screen.findByRole("button", { name: /dispute this claim/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(mockedReopenClaim).not.toHaveBeenCalled();
  });

  it("F116/AC2 (E10-S3): confirming a successful reopen shows the new sub-claim id and a tracker link", async () => {
    mockedFetchClaim.mockResolvedValue({
      claim_id: 4106,
      claim_type: "HEALTH",
      status: "SETTLED",
      incident_date: "2026-03-10",
      claim_amount: "20000.00",
      missing_documents: [],
      decision: null,
      settlement: {
        payout_amount: "17100.00",
        payment_reference: "STUB-PAY-0000004106-01",
        created_at: "2026-03-12T09:00:00Z",
      },
      parent_claim_id: null,
    });
    mockedReopenClaim.mockResolvedValue({
      sub_claim_id: 5001,
      parent_claim_id: 4106,
      status: "INTAKE",
    });

    renderTracker("4106");
    fireEvent.click(await screen.findByRole("button", { name: /dispute this claim/i }));
    fireEvent.click(screen.getByRole("button", { name: /yes, dispute/i }));

    expect(await screen.findByText(/claim #5001/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /track it here/i })).toHaveAttribute(
      "href",
      "/claims/5001",
    );
  });

  it("F117/AC3 (E10-S3): a failed reopen shows a user-facing error and leaves the displayed status unchanged", async () => {
    const { ApiError } = await import("../../../src/api/httpClient");
    mockedFetchClaim.mockResolvedValue({
      claim_id: 4106,
      claim_type: "HEALTH",
      status: "SETTLED",
      incident_date: "2026-03-10",
      claim_amount: "20000.00",
      missing_documents: [],
      decision: null,
      settlement: {
        payout_amount: "17100.00",
        payment_reference: "STUB-PAY-0000004106-01",
        created_at: "2026-03-12T09:00:00Z",
      },
      parent_claim_id: null,
    });
    mockedReopenClaim.mockRejectedValue(
      new ApiError(409, {
        error: { code: "INVALID_STATE_TRANSITION", message: "Claim is not SETTLED." },
      }),
    );

    renderTracker("4106");
    fireEvent.click(await screen.findByRole("button", { name: /dispute this claim/i }));
    fireEvent.click(screen.getByRole("button", { name: /yes, dispute/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/claim is not settled/i);
    expect(screen.getByText("SETTLED")).toBeInTheDocument();
  });
});
