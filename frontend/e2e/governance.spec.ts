import { test, expect } from '@playwright/test';

test.describe('Governance Tab (Settings)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Click Settings tab
    await page.getByRole('tab', { name: '⚙' }).click();
    // Wait for tab to be visible
    await expect(page.locator('.tab-content.settings')).toBeVisible();
  });

  test('loads settings tab with admin token field', async ({ page }) => {
    // Check that admin token input is visible
    await expect(page.locator('input[type="password"]').first()).toBeVisible();
    await expect(page.getByText('Admin Token')).toBeVisible();
  });

  test('loads settings list and API keys section', async ({ page }) => {
    // Check that settings sections are loaded
    await expect(page.getByText('API Keys')).toBeVisible();
    await expect(page.getByText('Data Providers')).toBeVisible();
    await expect(page.getByText('Features')).toBeVisible();
    await expect(page.getByText('Refresh Intervals')).toBeVisible();
    await expect(page.getByText('AI & Anomaly Detection')).toBeVisible();
  });

  test('loads AI budget display', async ({ page }) => {
    // Check that AI budget section loads
    await expect(page.getByText('Daily Token Budget')).toBeVisible();
  });
});
