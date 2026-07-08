import { test, expect } from '@playwright/test';
import { waitForAlpine, signInAsAdmin } from './helpers/auth';

test.describe('Signal AI', () => {
  test('signal tab shows narrative section after login', async ({ page }) => {
    await page.goto('/#signal');
    await waitForAlpine(page);
    await signInAsAdmin(page);
    await page.getByRole('tab', { name: 'Signal' }).click();
    await expect(page.locator('#tab-signal')).toBeVisible();
    await expect(page.getByText(/Signal Narrative|narrative/i).first()).toBeVisible();
  });
});
