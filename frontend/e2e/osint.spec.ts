import { test, expect } from '@playwright/test';

test.describe('Intel tab', () => {
  test('loads Intel tab with OSINT sections', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('tab', { name: 'Intel' }).click();
    await expect(page.locator('#tab-intel')).toBeVisible();
    await expect(page.locator('#tab-intel').getByText('Signal Events')).toBeVisible();
    await expect(page.locator('#tab-intel').getByText('OSINT Feed')).toBeVisible();
    await expect(page.locator('#tab-intel').getByText('Attestation Reports')).toBeVisible();
  });
});
