import { expect, test } from "@playwright/test";

// E10-S2 — claim tracker view, and E10-S3 — dispute action flow, exercised
// against a live backend seeded via backend/scripts/seed_e2e_db.py:
//   claim 5 -- DOCS_PENDING, MOTOR, POLICE_FIR verified / INVOICE outstanding
//   claim 6 -- MANUAL_REVIEW, MOTOR, decided HIGH_VALUE_REVIEW
//   claim 7 -- SETTLED, HEALTH, dedicated to the dispute-flow mutation below
//   claim 4 -- SETTLED, HEALTH (the E11-S4 admin fixture), reused read-only
//              /mocked-only here so it's never actually mutated
// Claim ids are printed by the seed script and may differ per run; this
// suite hardcodes them to match a fresh `seed_e2e_db.py` run on an empty DB.

async function loginAsCustomer(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByLabel(/role/i).selectOption("CUSTOMER");
  await page.getByLabel(/actor id/i).fill("cust-1001");
  await page.getByRole("button", { name: /continue/i }).click();
}

// F115/F116 actually reopen claim 7 (SETTLED -> REOPENED); F117 must not
// depend on that having already happened, so this file is forced serial and
// F117 uses a route-mocked failure on a claim it never actually mutates.
test.describe.configure({ mode: "serial" });

test("F111/AC1: lists each outstanding document type distinctly from verified ones", async ({
  page,
}) => {
  await loginAsCustomer(page);
  await page.goto("/claims/5");

  const policeFirRow = page.locator("li", { hasText: "Police FIR" });
  await expect(policeFirRow).toContainText("Verified");
  const invoiceRow = page.locator("li", { hasText: "Repair invoice" });
  await expect(invoiceRow).toContainText("Outstanding");
});

test("F112/AC2: shows the human-readable reason text, not just the raw code", async ({
  page,
}) => {
  await loginAsCustomer(page);
  await page.goto("/claims/6");

  await expect(page.getByText("HIGH_VALUE_REVIEW", { exact: false })).toBeVisible();
  await expect(
    page.getByText(/sent for manual review due to the claim's high value/i),
  ).toBeVisible();
});

test("F113/AC3: a SETTLED claim shows the payout amount and a Dispute this claim action", async ({
  page,
}) => {
  await loginAsCustomer(page);
  await page.goto("/claims/7");

  await expect(page.getByText("17100.00")).toBeVisible();
  await expect(page.getByRole("button", { name: /dispute this claim/i })).toBeVisible();
});

test("F114/AC4: a non-SETTLED claim shows no dispute action", async ({ page }) => {
  await loginAsCustomer(page);
  await page.goto("/claims/5");

  await expect(page.getByRole("heading", { name: /claim #5/i })).toBeVisible();
  await expect(
    page.getByRole("button", { name: /dispute this claim/i }),
  ).not.toBeVisible();
});

test("F115/AC1 (E10-S3): clicking Dispute this claim shows a confirmation dialog before any API call", async ({
  page,
}) => {
  let reopenCalled = false;
  await page.route("**/api/claims/7/reopen", (route) => {
    reopenCalled = true;
    route.continue();
  });

  await loginAsCustomer(page);
  await page.goto("/claims/7");
  await page.getByRole("button", { name: /dispute this claim/i }).click();

  await expect(page.getByRole("dialog")).toBeVisible();
  expect(reopenCalled).toBe(false);

  // Cancel rather than confirm -- claim 7 must stay SETTLED for F116, the
  // next test in this serial file, to actually exercise a real reopen.
  await page.getByRole("button", { name: /^cancel$/i }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
});

test("F116/AC2 (E10-S3): confirming a successful reopen shows the new sub-claim id and a link to its tracker", async ({
  page,
}) => {
  await loginAsCustomer(page);
  await page.goto("/claims/7");
  await page.getByRole("button", { name: /dispute this claim/i }).click();
  await page.getByRole("button", { name: /yes, dispute/i }).click();

  await expect(page.getByText(/dispute filed as claim #\d+/i)).toBeVisible();
  const link = page.getByRole("link", { name: /track it here/i });
  await expect(link).toBeVisible();
  const href = await link.getAttribute("href");
  expect(href).toMatch(/^\/claims\/\d+$/);
});

test("F117/AC3 (E10-S3): a failed reopen shows a user-facing error and leaves the displayed status unchanged", async ({
  page,
}) => {
  await page.route("**/api/claims/4/reopen", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        error: { code: "INVALID_STATE_TRANSITION", message: "Claim is not SETTLED." },
      }),
    }),
  );

  await loginAsCustomer(page);
  await page.goto("/claims/4");
  await page.getByRole("button", { name: /dispute this claim/i }).click();
  await page.getByRole("button", { name: /yes, dispute/i }).click();

  await expect(page.getByRole("alert")).toContainText(/claim is not settled/i);
  await expect(page.getByText("SETTLED", { exact: true })).toBeVisible();
});
