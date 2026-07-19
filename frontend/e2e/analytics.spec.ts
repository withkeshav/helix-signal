import { test, expect } from '@playwright/test';
import { waitForAlpine } from './helpers/auth';

test.describe('Analytics (merged into Signal)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/#signal');
    await waitForAlpine(page);
  });

  test('loads regime detection card', async ({ page }) => {
    await page.locator('#signal-analytics-section').scrollIntoViewIfNeeded();
    await expect(page.getByRole('heading', { name: /Regime Detection/ })).toBeVisible();
    await expect(page.locator('#signal-analytics-section')).toContainText(/Current State|No regime data available/);
  });

  test('loads change-point detection card', async ({ page }) => {
    await page.locator('#signal-analytics-section').scrollIntoViewIfNeeded();
    await expect(page.getByText('Change-Point Detection')).toBeVisible();
  });

  test('loads correlation matrix card', async ({ page }) => {
    await page.locator('#signal-analytics-section').scrollIntoViewIfNeeded();
    await expect(page.getByText('Cross-Asset Correlation Matrix')).toBeVisible();
  });

  test('redirects legacy #analytics hash to signal', async ({ page }) => {
    await page.goto('/#analytics');
    await waitForAlpine(page);
    await expect(page.locator('#tab-signal')).toBeVisible();
  });
});
