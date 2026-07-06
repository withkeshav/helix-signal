import { test, expect } from '@playwright/test';

const TABS = [
  { name: 'Signal', id: 'tab-signal', heading: 'Risk Terminal' },
  { name: 'Market', id: 'tab-market', heading: 'Peg Forecast' },
  { name: 'Intel', id: 'tab-intel', heading: 'Signal Events' },
  { name: 'System', id: 'tab-system', heading: 'Source Health' },
];

test.describe('Tab navigation', () => {
  test('no delete-user modal flash on load', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('Delete User?')).not.toBeVisible({ timeout: 500 });
  });

  for (const tab of TABS) {
    test(`${tab.name} tab renders content`, async ({ page }) => {
      await page.goto('/');
      await page.getByRole('tab', { name: tab.name }).click();
      await expect(page.locator(`#${tab.id}`)).toBeVisible();
      await expect(page.getByText(tab.heading).first()).toBeVisible();
    });
  }

  test('Settings tab shows login form', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('tab', { name: /settings/i }).click();
    await expect(page.locator('#tab-settings')).toBeVisible();
    await expect(page.getByText('Admin Login')).toBeVisible();
  });
});
