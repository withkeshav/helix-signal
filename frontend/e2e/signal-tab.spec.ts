import { test, expect } from '@playwright/test';
import { waitForAlpine } from './helpers/auth';

test.describe('Signal tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/#signal');
    await waitForAlpine(page);
    await expect(page.locator('#tab-signal')).toBeVisible();
  });

  test('loads market overview with all dashboard cards', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Risk Terminal' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Stress Leaderboard' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Rotation' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Risk Components' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Recent Anomalies' })).toBeVisible();
    await expect(page.locator('.risk-gauge')).toBeVisible();
    await expect(page.locator('.token-grid')).toBeVisible();
    await expect(page.locator('.token-card').first()).toBeVisible();
  });

  test('advanced analytics section is on signal tab', async ({ page }) => {
    await expect(page.locator('#signal-analytics-section')).toBeVisible();
    await expect(page.getByText('Advanced Analytics')).toBeVisible();
  });

  test('asset switching works correctly', async ({ page }) => {
    const tokenCards = page.locator('.token-card');
    const tokenCount = await tokenCards.count();
    expect(tokenCount).toBeGreaterThan(1);
    const secondSymbol = await tokenCards.nth(1).locator('.token-symbol').textContent();
    await tokenCards.nth(1).click();
    await expect(tokenCards.nth(1)).toHaveClass(/token-active/);
    await expect(page.locator('.token-card.token-active .token-symbol')).toHaveText(secondSymbol!);
  });

  test('time range selection works', async ({ page }) => {
    const timeRangeSelector = page.locator('.time-range');
    await expect(timeRangeSelector).toBeVisible();
    await expect(timeRangeSelector.getByText('24H')).toBeVisible();
    await timeRangeSelector.getByText('24H').click();
    await expect(timeRangeSelector.locator('.time-pill.active')).toHaveText('24H');
  });

  test('theme switching works', async ({ page }) => {
    const initialTheme = await page.locator('html').getAttribute('data-theme');
    await page.locator('button[aria-label="Toggle dark/light theme"]').click();
    const newTheme = await page.locator('html').getAttribute('data-theme');
    expect(newTheme).not.toBe(initialTheme);
  });

  test('AI content sub-tabs exist', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Overview' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Narrative' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Insights' })).toBeVisible();
  });

  test('stress leaderboard section visible', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Stress Leaderboard' })).toBeVisible();
    await expect(page.getByText('Chains ranked by supply velocity')).toBeVisible();
  });

  test('rotation section visible', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Rotation' })).toBeVisible();
    await expect(page.getByText('Cross-asset supply rotation')).toBeVisible();
  });

  test('deterministic risk content visible without AI', async ({ page }) => {
    await expect(page.locator('.risk-gauge')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Risk Components' })).toBeVisible();
    await expect(page.locator('.token-grid .token-card').first()).toBeVisible();
  });
});
