import { expect, test } from "@playwright/test";

// E11-S1 — document verification queue UI, exercised against a live backend
// seeded via backend/scripts/seed_e2e_db.py (2 DOCS_PENDING claims: a MOTOR
// claim outstanding POLICE_FIR + INVOICE, and a HEALTH claim outstanding
// HOSPITAL_BILL + DISCHARGE_SUMMARY).

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
  await expect(table.getByText("MOTOR", { exact: true })).toBeVisible();
  await expect(table.getByText("HEALTH", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Health", exact: true }).click();
  await expect(table.getByText("MOTOR", { exact: true })).not.toBeVisible();
  await expect(table.getByText("HEALTH", { exact: true })).toBeVisible();
});

test("AC2: verifying the last outstanding document removes the claim on next refresh", async ({
  page,
}) => {
  await loginAs(page, "ASSESSOR", "assessor-2");
  await expect(page).toHaveURL(/\/documents\/pending$/);

  const table = page.locator("table");
  const motorRow = table.locator("tr", { has: page.getByText("MOTOR", { exact: true }) });
  await expect(motorRow).toBeVisible();

  await motorRow.getByRole("button", { name: /police fir/i }).click();
  await expect(motorRow.getByRole("button", { name: /police fir/i })).toHaveCount(0);
  await motorRow.getByRole("button", { name: /invoice/i }).click();

  await expect(table.getByText("MOTOR", { exact: true })).not.toBeVisible();
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
