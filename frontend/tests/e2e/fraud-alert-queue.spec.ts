import { expect, test } from "@playwright/test";

test.describe("Fraud alert queue (E11-S2)", () => {
  test("F121: assessor sees fraud score, rules, and a workbench link", async ({ page }) => {
    await page.route("**/api/claims/fraud-alerts", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
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
    });

    await page.goto("/");
    await page.getByLabel(/actor id/i).fill("assessor-1");
    await page.getByLabel(/role/i).selectOption("ASSESSOR");
    await page.getByRole("button", { name: /continue/i }).click();

    await page.goto("/fraud-alerts");

    await expect(page.getByRole("heading", { name: /fraud alert queue/i })).toBeVisible();
    await expect(page.getByText("65")).toBeVisible();
    await expect(page.getByText(/HIGH_CLAIM_TO_SUM_RATIO/)).toBeVisible();
    const link = page.getByRole("link", { name: /open workbench/i });
    await expect(link).toHaveAttribute("href", "/workbench/42");
  });

  test("F123: a customer sees access-denied instead of the queue", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel(/actor id/i).fill("cust-1001");
    // CUSTOMER is the form's default selection -- no need to change it.
    await page.getByRole("button", { name: /continue/i }).click();

    await page.goto("/fraud-alerts");

    await expect(page.getByRole("alert")).toContainText(/access denied/i);
    await expect(page.getByRole("heading", { name: /fraud alert queue/i })).not.toBeVisible();
  });
});
