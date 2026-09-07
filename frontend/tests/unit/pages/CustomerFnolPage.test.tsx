import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as claimsApi from "../../../src/api/claimsApi";
import { CustomerFnolPage } from "../../../src/pages/CustomerFnolPage";
import { Role } from "../../../src/types/enums";
import { renderWithActor } from "../../utils/renderWithActor";

vi.mock("../../../src/api/claimsApi");

const mockedSubmitFnol = vi.mocked(claimsApi.submitFnol);

afterEach(() => {
  vi.clearAllMocks();
});

function TrackerStub() {
  const { claimId } = useParams<{ claimId: string }>();
  return <div data-testid="navigated-tracker">tracker for {claimId}</div>;
}

function renderFnolPage() {
  return render(
    <MemoryRouter initialEntries={["/claims/new"]}>
      <Routes>
        <Route
          path="/claims/new"
          element={renderWithActor(Role.CUSTOMER, "cust-1001", <CustomerFnolPage />)}
        />
        <Route path="/claims/:claimId" element={<TrackerStub />} />
      </Routes>
    </MemoryRouter>,
  );
}

function fillRequiredFields() {
  fireEvent.change(screen.getByLabelText(/policy number/i), {
    target: { value: "POL-MOTOR-0001" },
  });
  fireEvent.change(screen.getByLabelText(/incident date/i), {
    target: { value: "2026-03-10" },
  });
  fireEvent.change(screen.getByLabelText(/claim amount/i), {
    target: { value: "40000" },
  });
}

describe("CustomerFnolPage", () => {
  it("F107/AC1: renders all form fields (mobile-width reachability is verified by a Playwright viewport check)", () => {
    renderFnolPage();

    expect(screen.getByLabelText(/policy number/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/incident date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/claim amount/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /submit claim/i })).toBeInTheDocument();
  });

  it("F108/AC2: selecting HEALTH shows exactly Hospital bill and Discharge summary, not motor/life labels", () => {
    renderFnolPage();

    fireEvent.click(screen.getByText("Health"));

    expect(screen.getByText("Hospital bill")).toBeInTheDocument();
    expect(screen.getByText("Discharge summary")).toBeInTheDocument();
    expect(screen.queryByText("Police FIR")).not.toBeInTheDocument();
    expect(screen.queryByText("Repair invoice")).not.toBeInTheDocument();
    expect(screen.queryByText("Death certificate")).not.toBeInTheDocument();
  });

  it("F109/AC3: submitting with a missing required field shows inline validation and makes no API call", () => {
    renderFnolPage();

    // Only fill claim amount -- leave policy number and incident date blank.
    fireEvent.change(screen.getByLabelText(/claim amount/i), {
      target: { value: "40000" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit claim/i }));

    expect(screen.getByText(/policy number is required/i)).toBeInTheDocument();
    expect(screen.getByText(/incident date is required/i)).toBeInTheDocument();
    expect(mockedSubmitFnol).not.toHaveBeenCalled();
  });

  it("F110/AC4: a successful submission navigates to the claim tracker for the new claim id", async () => {
    mockedSubmitFnol.mockResolvedValue({
      claim_id: 777,
      status: "DOCS_PENDING",
      checklist: [
        { document_type: "POLICE_FIR", verification_status: "MISSING" },
        { document_type: "INVOICE", verification_status: "MISSING" },
      ],
    });

    renderFnolPage();
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: /submit claim/i }));

    await waitFor(() =>
      expect(screen.getByTestId("navigated-tracker")).toHaveTextContent("tracker for 777"),
    );
    expect(mockedSubmitFnol).toHaveBeenCalledWith(
      { role: Role.CUSTOMER, actorId: "cust-1001" },
      {
        policy_number: "POL-MOTOR-0001",
        claim_type: "MOTOR",
        incident_date: "2026-03-10",
        // Sent as the raw validated string (no Number()/toFixed() round
        // trip), matching the project's Decimal-as-string discipline for
        // money -- see CustomerFnolPage.tsx's handleSubmit.
        claim_amount: "40000",
      },
    );
  });
});
