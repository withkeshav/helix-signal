import { test, expect, Page } from '@playwright/test';

async function waitForAlpine(page: Page) {
  await page.waitForFunction(
    () => !!(document.documentElement._x_dataStack && document.documentElement._x_dataStack.length),
    null,
    { timeout: 10000 }
  );
}

test.describe('Alerts tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForAlpine(page);
    await page.getByRole('tab', { name: 'Alerts' }).click();
    await expect(page.locator('#tab-alerts')).toBeVisible({ timeout: 10000 });
  });

  test('loads fired alerts card', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Fired Alerts' })).toBeVisible();
  });

  test('loads alert rules card', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Alert Rules' })).toBeVisible();
  });

  test('shows severity filter dropdown', async ({ page }) => {
    const severitySelect = page.locator('#tab-alerts select');
    await expect(severitySelect).toBeVisible();
    await expect(severitySelect).toContainText('All severities');
  });
});
