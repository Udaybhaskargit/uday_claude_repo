import { expect, test } from "@playwright/test";

// E10-S1 — FNOL submission form, exercised against a live backend seeded via
// backend/scripts/seed_e2e_db.py (an ACTIVE, claim-free MOTOR policy
// POL-MOTOR-E2E-FNOL for AC4's real POST /api/claims submission).

async function loginAsCustomer(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByLabel(/role/i).selectOption("CUSTOMER");
  await page.getByLabel(/actor id/i).fill("cust-1001");
  await page.getByRole("button", { name: /continue/i }).click();
  await expect(page).toHaveURL(/\/claims\/new$/);
}

test("F107/AC1: at a 375px mobile viewport, all form fields are reachable without horizontal scrolling", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await loginAsCustomer(page);

  await expect(page.getByLabel(/policy number/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /submit claim/i })).toBeVisible();

  const hasHorizontalScroll = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasHorizontalScroll).toBe(false);
});

test("F108/AC2: selecting HEALTH shows exactly Hospital bill and Discharge summary, not motor/life labels", async ({
  page,
}) => {
  await loginAsCustomer(page);

  await page.getByText("Health", { exact: true }).click();

  await expect(page.getByText("Hospital bill")).toBeVisible();
  await expect(page.getByText("Discharge summary")).toBeVisible();
  await expect(page.getByText("Police FIR")).not.toBeVisible();
  await expect(page.getByText("Death certificate")).not.toBeVisible();
});

test("F109/AC3: submitting with a missing required field shows inline validation and stays on the form", async ({
  page,
}) => {
  await loginAsCustomer(page);

  await page.getByLabel(/claim amount/i).fill("40000");
  await page.getByRole("button", { name: /submit claim/i }).click();

  await expect(page.getByText(/policy number is required/i)).toBeVisible();
  await expect(page).toHaveURL(/\/claims\/new$/);
});

test("F110/AC4: a successful submission navigates to the claim tracker for the new claim id", async ({
  page,
}) => {
  await loginAsCustomer(page);

  await page.getByLabel(/policy number/i).fill("POL-MOTOR-E2E-FNOL");
  await page.getByLabel(/incident date/i).fill("2026-03-10");
  await page.getByLabel(/claim amount/i).fill("40000");
  await page.getByRole("button", { name: /submit claim/i }).click();

  await expect(page).toHaveURL(/\/claims\/\d+$/);
  await expect(page.getByRole("heading", { name: /^claim #\d+$/i })).toBeVisible();
});
