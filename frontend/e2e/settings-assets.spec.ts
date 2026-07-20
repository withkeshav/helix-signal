import { test, expect } from '@playwright/test';
import { waitForAlpine, signInAsAdmin } from './helpers/auth';

test.describe('Settings assets catalog', () => {
  test('loads asset toggles after sign-in', async ({ page }) => {
    await page.goto('/#settings');
    await waitForAlpine(page);
    await signInAsAdmin(page);
    const panel = page.locator('#tab-settings');
    await panel.getByRole('button', { name: 'Data & Sources' }).click();
    await expect(panel.getByRole('heading', { name: /Enabled assets/i })).toBeVisible({ timeout: 15000 });
    await panel.getByRole('button', { name: 'Refresh catalog' }).click();
    await expect(panel.getByText(/USDT|USDC|DAI/).first()).toBeVisible({ timeout: 15000 });
  });
});
