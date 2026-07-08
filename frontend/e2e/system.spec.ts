import { test, expect } from '@playwright/test';
import { waitForAlpine } from './helpers/auth';

test.describe('System tab', () => {
  test('renders source health', async ({ page }) => {
    await page.goto('/#system');
    await waitForAlpine(page);
    await expect(page.locator('#tab-system')).toBeVisible();
    await expect(page.getByText('Source Health').first()).toBeVisible();
  });

  test('admin operations drawer opens', async ({ page }) => {
    await page.goto('/#system');
    await waitForAlpine(page);
    await page.getByRole('button', { name: 'Admin Operations' }).click();
    await expect(page.getByText('Seed Demo History')).toBeVisible();
  });
});
