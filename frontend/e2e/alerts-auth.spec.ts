import { test, expect } from '@playwright/test';
import { waitForAlpine, signInAsAdmin } from './helpers/auth';

test.describe('Alerts auth', () => {
  test('alerts reloads after settings login', async ({ page }) => {
    await page.goto('/#alerts');
    await waitForAlpine(page);
    await signInAsAdmin(page);
    await page.getByRole('tab', { name: 'Alerts' }).click();
    await expect(page.locator('#tab-alerts')).toBeVisible();
    await expect(page.locator('#tab-alerts').getByRole('heading', { name: 'Fired Alerts' })).toBeVisible({ timeout: 15000 });
  });
});
