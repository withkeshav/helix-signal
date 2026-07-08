import { test, expect } from '@playwright/test';
import { waitForAlpine, signInAsAdmin } from './helpers/auth';

test.describe('Settings assets catalog', () => {
  test('loads asset toggles in Simple mode', async ({ page }) => {
    await page.goto('/#settings');
    await waitForAlpine(page);
    await signInAsAdmin(page);
    await page.getByRole('button', { name: 'Simple' }).click();
    await expect(page.getByText('Enabled Assets')).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Refresh catalog' }).click();
    // Catalog loads async — wait for at least one asset label to appear.
    await expect(page.locator('#tab-settings').getByText(/USDT|USDC|DAI/).first()).toBeVisible({ timeout: 15000 });
  });
});
