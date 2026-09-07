import { expect, test } from "@playwright/test";

// E11-S4 — admin dashboard UI, exercised against a live backend seeded via
// backend/scripts/seed_e2e_db.py: a MANUAL_REVIEW MOTOR claim (override
// target) and a SETTLED HEALTH claim with one Settlement (payout trail).

async function loginAsAdmin(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByLabel(/role/i).selectOption("ADMIN");
  await page.getByLabel(/actor id/i).fill("admin-1");
  await page.getByRole("button", { name: /continue/i }).click();
  await expect(page).toHaveURL(/\/admin$/);
}

// AC4 submits a real override against the seeded MANUAL_REVIEW claim, which
// changes its status -- it must run after the read-only AC1/AC2 checks and
// after AC3's blocked (non-mutating) submission attempt, so this file is
// forced serial.
test.describe.configure({ mode: "serial" });

test("AC1: changing status/product filters updates the claim queue without reloading", async ({
  page,
}) => {
  await loginAsAdmin(page);

  const claimsTable = page.locator("table").first();
  await expect(claimsTable.getByText("90000.00")).toBeVisible();
  await expect(claimsTable.getByText("40000.00")).toBeVisible();

  await page.getByLabel("Status").selectOption("MANUAL_REVIEW");
  await expect(claimsTable.getByText("90000.00")).toBeVisible();
  await expect(claimsTable.getByText("40000.00")).not.toBeVisible();

  await page.getByLabel("Status").selectOption("SETTLED");
  await expect(claimsTable.getByText("40000.00")).toBeVisible();
  await expect(claimsTable.getByText("90000.00")).not.toBeVisible();

  await page.getByLabel("Status").selectOption("ALL");
  await expect(page.getByRole("heading", { name: /admin dashboard/i })).toBeVisible();
});

test("AC2: the payout audit trail is read-only", async ({ page }) => {
  await loginAsAdmin(page);

  const payoutSection = page.locator("table", { hasText: "STUB-PAY-" });
  await expect(payoutSection).toBeVisible();
  await expect(payoutSection.getByText("35000.00")).toBeVisible();
  await expect(payoutSection.locator("button, input, select")).toHaveCount(0);
});

test("AC3: submitting an override without a reason code is blocked", async ({ page }) => {
  await loginAsAdmin(page);

  const reviewRow = page.locator("tr", { hasText: "MANUAL_REVIEW" });
  await expect(reviewRow).toBeVisible();
  await reviewRow.getByRole("button", { name: /select for override/i }).click();
  await page.getByRole("button", { name: /submit override/i }).click();

  await expect(page.getByRole("alert")).toContainText(/reason code is required/i);
});

test("AC4: a successful override appears in the claim's audit history", async ({ page }) => {
  await loginAsAdmin(page);

  const reviewRow = page.locator("tr", { hasText: "MANUAL_REVIEW" });
  await expect(reviewRow).toBeVisible();
  await reviewRow.getByRole("button", { name: /select for override/i }).click();
  await page.getByLabel(/command/i).selectOption("FORCE_APPROVE");
  await page
    .getByLabel(/reason code/i)
    .fill("Manual goodwill approval after phone review");
  await page.getByRole("button", { name: /submit override/i }).click();

  const historyTable = page.locator("table", { hasText: "Manual goodwill approval" });
  await expect(historyTable).toBeVisible();
  await expect(historyTable.getByText("FORCE_APPROVE")).toBeVisible();
});
