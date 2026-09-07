import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as workbenchApi from "../../../src/api/workbenchApi";
import { WorkbenchPage } from "../../../src/pages/WorkbenchPage";
import { Role } from "../../../src/types/enums";
import { renderWithActor } from "../../utils/renderWithActor";

vi.mock("../../../src/api/workbenchApi");

const mockedFetchWorkbenchDetail = vi.mocked(workbenchApi.fetchWorkbenchDetail);
const mockedSubmitDecision = vi.mocked(workbenchApi.submitDecision);

afterEach(() => {
  vi.clearAllMocks();
});

function renderWorkbench(claimId = "4287") {
  return render(
    <MemoryRouter initialEntries={[`/workbench/${claimId}`]}>
      <Routes>
        <Route
          path="/workbench/:claimId"
          element={renderWithActor(Role.ASSESSOR, "assessor-3", <WorkbenchPage />)}
        />
        <Route path="/fraud-alerts" element={<div>fraud alert queue</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function detailFixture() {
  return {
    claim_id: 4287,
    claim_type: "MOTOR" as const,
    status: "MANUAL_REVIEW" as const,
    fraud_screening: {
      score: 65,
      threshold: 60,
      flagged: true,
      breakdown: [
        { rule_name: "HIGH_CLAIM_TO_SUM_RATIO", weight: 40 },
        { rule_name: "EARLY_FILING", weight: 25 },
      ],
    },
    assessment: {
      claim_amount: "75000.00",
      sum_insured: "100000.00",
      deductible: "5000.00",
      co_pay: "0.00",
      payable_amount: "70000.00",
    },
    suggested_reason_code: "HIGH_VALUE_REVIEW" as const,
  };
}

describe("WorkbenchPage", () => {
  it("F124/AC1: displays the fraud score and breakdown alongside the computed payable_amount", async () => {
    mockedFetchWorkbenchDetail.mockResolvedValue(detailFixture());

    renderWorkbench();

    expect(await screen.findByText(/score 65 \/ threshold 60/i)).toBeInTheDocument();
    expect(screen.getByText("HIGH_CLAIM_TO_SUM_RATIO")).toBeInTheDocument();
    expect(screen.getByText("+40")).toBeInTheDocument();
    expect(screen.getByText("70000.00")).toBeInTheDocument();
  });

  it("F126/AC3: submitting without selecting an outcome blocks the call with a validation message", async () => {
    mockedFetchWorkbenchDetail.mockResolvedValue(detailFixture());

    renderWorkbench();
    await screen.findByText(/score 65/i);

    fireEvent.click(screen.getByRole("button", { name: /submit decision/i }));

    expect(screen.getByText(/select an outcome/i)).toBeInTheDocument();
    expect(mockedSubmitDecision).not.toHaveBeenCalled();
  });

  it("F125/AC2: a successful submission shows a confirmation and removes the pending decision form", async () => {
    mockedFetchWorkbenchDetail.mockResolvedValue(detailFixture());
    mockedSubmitDecision.mockResolvedValue({
      claim_id: 4287,
      decision: {
        outcome: "AUTO_APPROVE",
        reason_code: "HIGH_VALUE_REVIEW",
        decided_by: "assessor-3",
        created_at: "2026-03-11T10:00:00Z",
      },
      claim_status: "AUTO_APPROVED",
    });

    renderWorkbench();
    await screen.findByText(/score 65/i);

    // AUTO_APPROVE/REJECT are the only outcomes an assessor can submit --
    // MANUAL_REVIEW has no corresponding ASSESSOR_* state-machine event
    // (backend/src/services/decision_engine.py), so it isn't exercised here.
    fireEvent.click(screen.getByRole("radio", { name: "AUTO_APPROVE" }));
    fireEvent.click(screen.getByRole("button", { name: /submit decision/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(/decision submitted/i);
    expect(screen.queryByRole("button", { name: /submit decision/i })).not.toBeInTheDocument();
    expect(mockedSubmitDecision).toHaveBeenCalledWith(
      { role: Role.ASSESSOR, actorId: "assessor-3" },
      4287,
      { outcome: "AUTO_APPROVE", reason_code: "HIGH_VALUE_REVIEW" },
    );
  });
});
