import { expect, test } from "@playwright/test";

// E11-S3 — assessor workbench UI, exercised against a live backend seeded
// via backend/scripts/seed_e2e_db.py: claim 8, MANUAL_REVIEW/MOTOR, with a
// FraudScreening (score 65/threshold 60, flagged) and an Assessment
// (payable_amount 70000.00) already persisted.

async function loginAsAssessor(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByLabel(/role/i).selectOption("ASSESSOR");
  await page.getByLabel(/actor id/i).fill("assessor-3");
  await page.getByRole("button", { name: /continue/i }).click();
}

// F125 submits a real decision against claim 8, moving it out of
// MANUAL_REVIEW -- it must run after F124/F126's read-only checks against
// that same claim, so this file is forced serial.
test.describe.configure({ mode: "serial" });

test("F124/AC1: displays the fraud score and breakdown alongside the computed payable_amount", async ({
  page,
}) => {
  await loginAsAssessor(page);
  await page.goto("/workbench/8");

  await expect(page.getByText(/score 65 \/ threshold 60/i)).toBeVisible();
  await expect(page.getByText("HIGH_CLAIM_TO_SUM_RATIO")).toBeVisible();
  await expect(page.getByText("+40")).toBeVisible();
  await expect(page.getByText("70000.00")).toBeVisible();
});

test("F126/AC3: submitting without selecting an outcome blocks the call with a validation message", async ({
  page,
}) => {
  let decisionCalled = false;
  await page.route("**/api/claims/8/decision", (route) => {
    decisionCalled = true;
    route.continue();
  });

  await loginAsAssessor(page);
  await page.goto("/workbench/8");
  await page.getByRole("button", { name: /submit decision/i }).click();

  await expect(page.getByText(/select an outcome/i)).toBeVisible();
  expect(decisionCalled).toBe(false);
});

test("F125/AC2: a successful submission shows a confirmation and removes the pending decision form", async ({
  page,
}) => {
  await loginAsAssessor(page);
  await page.goto("/workbench/8");

  // AUTO_APPROVE/REJECT are the only outcomes an assessor can submit --
  // MANUAL_REVIEW has no corresponding ASSESSOR_* state-machine event (see
  // backend/src/services/decision_engine.py's submit_assessor_decision()
  // docstring), so it's rejected as a 422 rather than accepted. The radio
  // input itself is visually hidden (sr-only) with its clickable surface on
  // the wrapping <label> -- target the label text directly rather than the
  // input's accessible role, which Playwright's hit-testing can miss on a
  // zero-size clipped element.
  // Scoped to the Outcome group -- an unscoped "AUTO_APPROVE" text match
  // also hits the reason-code <select>'s "AUTO_APPROVED_LOW_RISK" option
  // (a substring match), which is a sibling label, not this one.
  await page.getByRole("group", { name: "Outcome" }).locator("label", { hasText: "AUTO_APPROVE" }).click();
  await page.getByRole("button", { name: /submit decision/i }).click();

  await expect(page.getByText(/decision submitted for claim #8/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /submit decision/i })).not.toBeVisible();
});
