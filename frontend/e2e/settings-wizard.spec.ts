import { test, expect } from '@playwright/test';
import { waitForAlpine, signInAsAdmin } from './helpers/auth';

test.describe('Settings wizard', () => {
  test('Open Admin Panel and Test AI visible when signed in', async ({ page }) => {
    await page.goto('/#settings');
    await waitForAlpine(page);
    await signInAsAdmin(page);
    await expect(page.getByRole('link', { name: /Open Admin Panel/i })).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('button', { name: /Test AI/i })).toBeVisible();
  });

  test('provider test button exists after sign-in', async ({ page }) => {
    await page.goto('/#settings');
    await waitForAlpine(page);
    await signInAsAdmin(page);
    await expect(page.getByRole('button', { name: 'Test provider chain' })).toBeVisible({ timeout: 15000 });
  });
});
