import { test, expect } from '@playwright/test';
import { waitForAlpine, signInAsAdmin } from './helpers/auth';

test.describe('Settings assets catalog', () => {
  test('loads asset toggles after sign-in', async ({ page }) => {
    await page.goto('/#settings');
    await waitForAlpine(page);
    await signInAsAdmin(page);
    await expect(page.getByText('Enabled Assets')).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Refresh catalog' }).click();
    await expect(page.locator('#tab-settings').getByText(/USDT|USDC|DAI/).first()).toBeVisible({ timeout: 15000 });
  });
});
