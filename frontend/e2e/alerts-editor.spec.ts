import { test, expect } from '@playwright/test';
import { waitForAlpine, signInAsAdmin } from './helpers/auth';

test.describe('Alerts rule editor', () => {
  test('shows edit rules control when signed in', async ({ page }) => {
    await page.goto('/#alerts');
    await waitForAlpine(page);
    await signInAsAdmin(page);
    await page.getByRole('tab', { name: 'Alerts' }).click();
    await expect(page.getByRole('button', { name: 'Edit rules' })).toBeVisible();
  });
});
