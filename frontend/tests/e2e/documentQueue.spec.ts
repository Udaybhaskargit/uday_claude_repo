import { expect, test } from "@playwright/test";

// E11-S1 — document verification queue UI, exercised against a live backend
// seeded via backend/scripts/seed_e2e_db.py (2 DOCS_PENDING claims: claim 1,
// MOTOR, outstanding POLICE_FIR + INVOICE, and claim 2, HEALTH, outstanding
// HOSPITAL_BILL + DISCHARGE_SUMMARY). Other e2e specs' fixtures also seed
// DOCS_PENDING MOTOR claims into this same shared DB, so MOTOR rows below
// are scoped by claim id (1), not by claim_type text alone -- HEALTH has no
// such collision across this suite's fixtures.

async function loginAs(page: import("@playwright/test").Page, role: string, actorId: string) {
  await page.goto("/");
  await page.getByLabel(/role/i).selectOption(role);
  await page.getByLabel(/actor id/i).fill(actorId);
  await page.getByRole("button", { name: /continue/i }).click();
}

// AC2 mutates the seeded MOTOR claim (verifies its documents away); it must
// run after AC1's read of that same claim against the shared seeded backend,
// so this file is forced serial rather than relying on the global
// `fullyParallel` ordering.
test.describe.configure({ mode: "serial" });

test("AC1: the queue lists DOCS_PENDING claims, filterable by claim type", async ({ page }) => {
  await loginAs(page, "ASSESSOR", "assessor-1");

  await expect(page).toHaveURL(/\/documents\/pending$/);
  await expect(
    page.getByRole("heading", { name: /document verification queue/i }),
  ).toBeVisible();

  const table = page.locator("table");
  const claim1Row = table.locator("tr").filter({ has: page.getByText("1", { exact: true }) });
  await expect(claim1Row).toBeVisible();
  await expect(table.getByText("HEALTH", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Health", exact: true }).click();
  await expect(claim1Row).not.toBeVisible();
  await expect(table.getByText("HEALTH", { exact: true })).toBeVisible();
});

test("AC2: verifying the last outstanding document removes the claim on next refresh", async ({
  page,
}) => {
  await loginAs(page, "ASSESSOR", "assessor-2");
  await expect(page).toHaveURL(/\/documents\/pending$/);

  const table = page.locator("table");
  const motorRow = table.locator("tr").filter({ has: page.getByText("1", { exact: true }) });
  await expect(motorRow).toBeVisible();

  await motorRow.getByRole("button", { name: /police fir/i }).click();
  await expect(motorRow.getByRole("button", { name: /police fir/i })).toHaveCount(0);
  await motorRow.getByRole("button", { name: /invoice/i }).click();

  await expect(motorRow).not.toBeVisible();
});

test("AC3: a CUSTOMER actor sees an access-denied state instead of the queue", async ({
  page,
}) => {
  await loginAs(page, "CUSTOMER", "cust-1001");
  await page.goto("/documents/pending");

  await expect(page.getByRole("alert")).toContainText(/access denied/i);
  await expect(
    page.getByRole("heading", { name: /document verification queue/i }),
  ).not.toBeVisible();
});
