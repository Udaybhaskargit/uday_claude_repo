import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthContext } from "../../src/context/AuthContext";
import { FraudQueuePage } from "../../src/pages/FraudQueuePage";
import { Role } from "../../src/types/enums";

const ACTOR = { role: Role.ASSESSOR, actorId: "assessor-1" };

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthContext.Provider value={{ actor: ACTOR, setActor: vi.fn(), clearActor: vi.fn() }}>
        <FraudQueuePage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("FraudQueuePage (E11-S2)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("F121: shows fraud score, triggered rules, and a workbench link per row", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        claims: [
          {
            claim_id: 42,
            claim_type: "MOTOR",
            fraud_score: 65,
            triggered_rules: ["HIGH_CLAIM_TO_SUM_RATIO", "EARLY_FILING"],
          },
        ],
      }),
    });

    renderPage();

    await waitFor(() => expect(screen.getByText(/65/)).toBeInTheDocument());
    expect(screen.getByText(/HIGH_CLAIM_TO_SUM_RATIO/)).toBeInTheDocument();
    expect(screen.getByText(/EARLY_FILING/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /open workbench/i });
    expect(link).toHaveAttribute("href", "/workbench/42");
  });

  it("F122: an empty response renders no rows", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ claims: [] }),
    });

    renderPage();

    await waitFor(() =>
      expect(
        screen.getByText(/no claims are currently flagged/i),
      ).toBeInTheDocument(),
    );
  });
});
