import { test, expect, Page } from '@playwright/test';

async function waitForAlpine(page: Page) {
  await page.waitForFunction(
    () => !!(document.documentElement._x_dataStack && document.documentElement._x_dataStack.length),
    null,
    { timeout: 10000 }
  );
}

test.describe('Forensics tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await waitForAlpine(page);
    await page.getByRole('tab', { name: 'Forensics' }).click();
    await expect(page.locator('#tab-forensics')).toBeVisible({ timeout: 10000 });
  });

  test('loads blacklist overview card', async ({ page }) => {
    await expect(page.getByText('Blacklist Overview')).toBeVisible();
  });

  test('loads events section', async ({ page }) => {
    await expect(page.locator('#tab-forensics').getByRole('heading', { name: 'Events', exact: true })).toBeVisible();
  });

  test('loads investigate address form', async ({ page }) => {
    await expect(page.getByText('Investigate Address')).toBeVisible();
    await expect(page.locator('input[placeholder="0x..."]')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Investigate' })).toBeVisible();
  });
});
