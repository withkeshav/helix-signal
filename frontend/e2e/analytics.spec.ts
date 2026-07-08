import { test, expect, Page } from '@playwright/test';

async function waitForAlpine(page: Page) {
  // Alpine ESM build does not expose window.Alpine; wait for root data stack instead.
  await page.waitForFunction(
    () => !!(document.documentElement._x_dataStack && document.documentElement._x_dataStack.length),
    null,
    { timeout: 10000 }
  );
}

test.describe('Analytics tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForAlpine(page);
    await page.getByRole('tab', { name: 'Analytics' }).click();
    await expect(page.locator('#tab-analytics')).toBeVisible({ timeout: 10000 });
  });

  test('loads regime detection card', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /Regime Detection/ })).toBeVisible();
    await expect(page.locator('#tab-analytics')).toContainText(/Current State|No regime data available/);
  });

  test('loads change-point detection card', async ({ page }) => {
    await expect(page.getByText('Change-Point Detection')).toBeVisible();
  });

  test('loads correlation matrix card', async ({ page }) => {
    await expect(page.getByText('Cross-Asset Correlation Matrix')).toBeVisible();
  });
});
