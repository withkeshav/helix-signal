import { test, expect } from '@playwright/test';
import { waitForAlpine, signInAsAdmin } from './helpers/auth';

test.describe('Settings wizard', () => {
  test('Simple and Advanced toggle visible when signed in', async ({ page }) => {
    await page.goto('/#settings');
    await waitForAlpine(page);
    await signInAsAdmin(page);
    await expect(page.getByRole('button', { name: 'Simple' })).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('button', { name: 'Advanced' })).toBeVisible();
  });

  test('provider test button exists in Simple mode', async ({ page }) => {
    await page.goto('/#settings');
    await waitForAlpine(page);
    await signInAsAdmin(page);
    await expect(page.getByRole('button', { name: 'Test provider chain' })).toBeVisible({ timeout: 15000 });
  });
});
