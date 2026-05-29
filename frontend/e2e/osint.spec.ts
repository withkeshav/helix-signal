import { test, expect } from '@playwright/test';

test.describe('OSINT/Events Tabs', () => {
  test('loads Events tab with events and OSINT feed', async ({ page }) => {
    await page.goto('/');
    // Click Events tab (OSINT)
    await page.getByRole('tab', { name: 'OSINT' }).click();
    // Wait for tab to be visible
    await expect(page.locator('.tab-content.events')).toBeVisible();
    
    // Check that events section loads
    await expect(page.getByText('Signal Events')).toBeVisible();
    await expect(page.getByText('OSINT Feed')).toBeVisible();
    
    // Check that sentiment chart loads
    await expect(page.locator('#chart-sentiment')).toBeVisible();
  });

  test('loads Intel tab with attestation reports', async ({ page }) => {
    await page.goto('/');
    // Click Intel tab 
    await page.getByRole('tab', { name: 'Intel' }).click();
    // Wait for tab to be visible
    await expect(page.locator('.tab-content.intel')).toBeVisible();
    
    // Check that attestation section loads
    await expect(page.getByText('Attestation Reports')).toBeVisible();
  });
});
