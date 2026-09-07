import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as adminApi from "../../../src/api/adminApi";
import { AdminDashboardPage } from "../../../src/pages/AdminDashboardPage";
import { Role } from "../../../src/types/enums";
import { renderWithActor } from "../../utils/renderWithActor";

vi.mock("../../../src/api/adminApi");

const mockedFetchAdminClaims = vi.mocked(adminApi.fetchAdminClaims);
const mockedFetchPayouts = vi.mocked(adminApi.fetchPayouts);
const mockedFetchClaimOverrides = vi.mocked(adminApi.fetchClaimOverrides);
const mockedSubmitOverride = vi.mocked(adminApi.submitOverride);

const ADMIN_ACTOR = { role: Role.ADMIN, actorId: "admin-1" };

afterEach(() => {
  vi.clearAllMocks();
});

function setup() {
  mockedFetchAdminClaims.mockResolvedValue({
    claims: [
      {
        claim_id: 4455,
        claim_type: "MOTOR",
        status: "MANUAL_REVIEW",
        claim_amount: "90000.00",
        updated_at: "2026-09-05T08:02:00Z",
      },
    ],
  });
  mockedFetchPayouts.mockResolvedValue({
    payouts: [
      {
        settlement_id: 9,
        claim_id: 4106,
        payout_amount: "35000.00",
        payment_reference: "STUB-PAY-0000004106-01",
        created_at: "2026-09-05T14:22:10Z",
      },
      {
        settlement_id: 8,
        claim_id: 4033,
        payout_amount: "17100.00",
        payment_reference: "STUB-PAY-0000004033-01",
        created_at: "2026-09-03T09:11:47Z",
      },
    ],
  });
  mockedFetchClaimOverrides.mockResolvedValue({ overrides: [] });
}

describe("AdminDashboardPage", () => {
  it("AC1: changing status/product filters re-queries the claim queue without navigating", async () => {
    setup();
    render(renderWithActor(Role.ADMIN, "admin-1", <AdminDashboardPage />));

    await waitFor(() => expect(mockedFetchAdminClaims).toHaveBeenCalledTimes(1));
    expect(mockedFetchAdminClaims).toHaveBeenCalledWith(ADMIN_ACTOR, undefined, undefined);

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "MANUAL_REVIEW" },
    });
    await waitFor(() =>
      expect(mockedFetchAdminClaims).toHaveBeenLastCalledWith(
        ADMIN_ACTOR,
        "MANUAL_REVIEW",
        undefined,
      ),
    );

    fireEvent.change(screen.getByLabelText("Product"), { target: { value: "MOTOR" } });
    await waitFor(() =>
      expect(mockedFetchAdminClaims).toHaveBeenLastCalledWith(
        ADMIN_ACTOR,
        "MANUAL_REVIEW",
        "MOTOR",
      ),
    );

    // Same document/location throughout -- confirms no full page reload occurred.
    expect(screen.getByRole("heading", { name: /admin dashboard/i })).toBeInTheDocument();
  });

  it("AC2: the payout audit trail is read-only and rendered in the order the API returns", async () => {
    setup();
    render(renderWithActor(Role.ADMIN, "admin-1", <AdminDashboardPage />));

    await screen.findByText("STUB-PAY-0000004106-01");
    const rows = screen.getAllByText(/STUB-PAY-/).map((el) => el.textContent);
    expect(rows).toEqual(["STUB-PAY-0000004106-01", "STUB-PAY-0000004033-01"]);

    // Read-only: no input/button controls inside the payout table itself.
    const payoutTable = screen.getByText("STUB-PAY-0000004106-01").closest("table");
    expect(payoutTable).not.toBeNull();
    expect(payoutTable?.querySelectorAll("button, input, select")).toHaveLength(0);
  });

  it("AC3: submitting the override form without a reason code is blocked with a validation message", async () => {
    setup();
    render(renderWithActor(Role.ADMIN, "admin-1", <AdminDashboardPage />));

    fireEvent.click(await screen.findByRole("button", { name: /select for override/i }));
    await waitFor(() => expect(mockedFetchClaimOverrides).toHaveBeenCalledWith(ADMIN_ACTOR, 4455));

    fireEvent.click(screen.getByRole("button", { name: /submit override/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/reason code is required/i);
    expect(mockedSubmitOverride).not.toHaveBeenCalled();
  });

  it("AC4: a successful override appears in the claim's audit history", async () => {
    setup();
    mockedSubmitOverride.mockResolvedValue({
      claim_id: 4455,
      override_id: 5,
      claim_status: "AUTO_APPROVED",
    });

    render(renderWithActor(Role.ADMIN, "admin-1", <AdminDashboardPage />));

    fireEvent.click(await screen.findByRole("button", { name: /select for override/i }));
    await waitFor(() => expect(mockedFetchClaimOverrides).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText(/reason code/i), {
      target: { value: "Manual goodwill approval after phone review" },
    });

    mockedFetchClaimOverrides.mockResolvedValueOnce({
      overrides: [
        {
          override_id: 5,
          admin_actor_id: "admin-1",
          command: "FORCE_APPROVE",
          reason_code: "Manual goodwill approval after phone review",
          created_at: "2026-04-05T14:00:00Z",
        },
      ],
    });

    fireEvent.click(screen.getByRole("button", { name: /submit override/i }));

    await waitFor(() =>
      expect(mockedSubmitOverride).toHaveBeenCalledWith(
        ADMIN_ACTOR,
        4455,
        "FORCE_APPROVE",
        "Manual goodwill approval after phone review",
      ),
    );
    expect(
      await screen.findByText("Manual goodwill approval after phone review", {
        selector: "td",
      }),
    ).toBeInTheDocument();
  });
});
