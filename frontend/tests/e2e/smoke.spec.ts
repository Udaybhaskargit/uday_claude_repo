import { expect, test } from "@playwright/test";

test("role-select page loads and lets a customer continue", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: /claimflow/i })).toBeVisible();

  await page.getByLabel(/actor id/i).fill("cust-1001");
  await page.getByRole("button", { name: /continue/i }).click();

  await expect(page).toHaveURL(/\/claims\/new$/);
});
