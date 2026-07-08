import { test, expect } from '@playwright/test';
import { waitForAlpine } from './helpers/auth';

test.describe('Global status bar', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/#signal');
    await waitForAlpine(page);
  });

  test('shows view-only auth badge when logged out', async ({ page }) => {
    await expect(page.getByText('View only')).toBeVisible();
  });

  test('shows AI mode badge', async ({ page }) => {
    await expect(page.getByText(/^AI:/)).toBeVisible();
  });

  test('shows data health badge', async ({ page }) => {
    await expect(page.getByText(/^Data:/)).toBeVisible();
  });

  test('asset selector is visible', async ({ page }) => {
    await expect(page.locator('.asset-select')).toBeVisible();
  });
});
