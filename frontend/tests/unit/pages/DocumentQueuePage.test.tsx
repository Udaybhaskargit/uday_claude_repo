import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as documentsApi from "../../../src/api/documentsApi";
import { RoleGuard } from "../../../src/components/RoleGuard";
import { DocumentQueuePage } from "../../../src/pages/DocumentQueuePage";
import { Role } from "../../../src/types/enums";
import { renderWithActor } from "../../utils/renderWithActor";

vi.mock("../../../src/api/documentsApi");

const mockedFetchPendingDocuments = vi.mocked(documentsApi.fetchPendingDocuments);
const mockedVerifyDocument = vi.mocked(documentsApi.verifyDocument);

afterEach(() => {
  vi.clearAllMocks();
});

describe("DocumentQueuePage", () => {
  it("AC1: lists only the DOCS_PENDING claims returned by the queue endpoint", async () => {
    mockedFetchPendingDocuments.mockResolvedValue({
      claims: [
        { claim_id: 4231, claim_type: "MOTOR", outstanding_documents: ["POLICE_FIR"] },
        {
          claim_id: 4390,
          claim_type: "HEALTH",
          outstanding_documents: ["HOSPITAL_BILL", "DISCHARGE_SUMMARY"],
        },
      ],
    });

    render(renderWithActor(Role.ASSESSOR, "assessor-3", <DocumentQueuePage />));

    expect(await screen.findByText("4231")).toBeInTheDocument();
    expect(screen.getByText("4390")).toBeInTheDocument();
    expect(mockedFetchPendingDocuments).toHaveBeenCalledWith(
      { role: Role.ASSESSOR, actorId: "assessor-3" },
      undefined,
    );
  });

  it("AC1: filtering by claim type re-queries the endpoint with claim_type set", async () => {
    mockedFetchPendingDocuments.mockResolvedValue({ claims: [] });

    render(renderWithActor(Role.ASSESSOR, "assessor-3", <DocumentQueuePage />));

    await waitFor(() => expect(mockedFetchPendingDocuments).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Motor" }));

    await waitFor(() =>
      expect(mockedFetchPendingDocuments).toHaveBeenLastCalledWith(
        { role: Role.ASSESSOR, actorId: "assessor-3" },
        "MOTOR",
      ),
    );
  });

  it("AC2: verifying the last outstanding item removes the claim from the queue on next refresh", async () => {
    mockedFetchPendingDocuments
      .mockResolvedValueOnce({
        claims: [{ claim_id: 4231, claim_type: "MOTOR", outstanding_documents: ["POLICE_FIR"] }],
      })
      .mockResolvedValueOnce({ claims: [] });
    mockedVerifyDocument.mockResolvedValue({
      claim_id: 4231,
      document_type: "POLICE_FIR",
      verification_status: "VERIFIED",
      claim_status: "FRAUD_SCREENING",
    });

    render(renderWithActor(Role.ASSESSOR, "assessor-3", <DocumentQueuePage />));

    const row = (await screen.findByText("4231")).closest("tr");
    expect(row).not.toBeNull();
    fireEvent.click(within(row as HTMLElement).getByRole("button", { name: /police fir/i }));

    await waitFor(() =>
      expect(mockedVerifyDocument).toHaveBeenCalledWith(
        { role: Role.ASSESSOR, actorId: "assessor-3" },
        4231,
        "POLICE_FIR",
      ),
    );
    await waitFor(() => expect(mockedFetchPendingDocuments).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText("4231")).not.toBeInTheDocument());
    expect(
      screen.getByText("No claims currently in DOCS_PENDING for this filter."),
    ).toBeInTheDocument();
  });

  it("AC3: a CUSTOMER actor sees an access-denied state instead of the queue", () => {
    render(
      renderWithActor(
        Role.CUSTOMER,
        "cust-1001",
        <RoleGuard allow={[Role.ASSESSOR, Role.ADMIN]}>
          <DocumentQueuePage />
        </RoleGuard>,
      ),
    );

    expect(screen.getByRole("alert")).toHaveTextContent(/access denied/i);
    expect(screen.queryByText("Document verification queue")).not.toBeInTheDocument();
    expect(mockedFetchPendingDocuments).not.toHaveBeenCalled();
  });
});
