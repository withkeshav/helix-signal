import { test, expect } from '@playwright/test';

test.describe('Market/Overview Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Ensure we're on the Overview tab (should be default)
    await expect(page.locator('.tab-content.overview')).toBeVisible();
  });

  test('loads market overview with all dashboard cards', async ({ page }) => {
    // Check that all main dashboard cards are visible
    await expect(page.getByText('Market Overview')).toBeVisible();
    await expect(page.getByText('Risk Terminal')).toBeVisible();
    await expect(page.getByText('Stress Leaderboard')).toBeVisible();
    await expect(page.getByText('Market Narrative')).toBeVisible();
    await expect(page.getByText('Analytics Insight')).toBeVisible();
    await expect(page.getByText('Rotation')).toBeVisible();
    
    // Check that risk gauge loads with score
    const riskGauge = page.locator('.risk-gauge');
    await expect(riskGauge).toBeVisible();
    
    // Check that token grid loads
    const tokenGrid = page.locator('.token-grid');
    await expect(tokenGrid).toBeVisible();
    
    // Check that at least one token card is visible
    await expect(page.locator('.token-card').first()).toBeVisible();
  });

  test('asset switching works correctly', async ({ page }) => {
    // Get initial asset
    const initialAsset = await page.locator('.token-symbol').first().textContent();
    
    // Switch to a different asset if available
    const tokenCards = page.locator('.token-card');
    const tokenCount = await tokenCards.count();
    
    if (tokenCount > 1) {
      // Click on second token card
      const secondToken = tokenCards.nth(1);
      await secondToken.click();
      
      // Verify asset changed in UI
      const newAsset = await page.locator('.token-symbol').first().textContent();
      expect(newAsset).not.toBe(initialAsset);
    }
  });

  test('time range selection works', async ({ page }) => {
    // Check that time range selector is visible
    const timeRangeSelector = page.locator('.time-range');
    await expect(timeRangeSelector).toBeVisible();
    
    // Check that time range pills exist
    await expect(page.getByText('6H')).toBeVisible();
    await expect(page.getByText('24H')).toBeVisible();
    await expect(page.getByText('7D')).toBeVisible();
    await expect(page.getByText('30D')).toBeVisible();
    await expect(page.getByText('90D')).toBeVisible();
    
    // Click on 24H range
    await page.getByText('24H').click();
    
    // Verify the active state changed (this would require checking the class)
    const activePill = page.locator('.time-pill.active');
    await expect(activePill).toHaveText('24H');
  });

  test('theme switching works', async ({ page }) => {
    // Check initial theme
    const initialTheme = await page.locator('html').getAttribute('data-theme');
    
    // Click theme toggle button
    await page.locator('button[aria-label="Toggle theme"]').click();
    
    // Verify theme changed
    const newTheme = await page.locator('html').getAttribute('data-theme');
    expect(newTheme).not.toBe(initialTheme);
    
    // Switch back
    await page.locator('button[aria-label="Toggle theme"]').click();
  });

  test('AI content cards load properly', async ({ page }) => {
    // Check that AI content sections exist
    await expect(page.getByText('Market Overview')).toBeVisible();
    await expect(page.getByText('Risk Terminal')).toBeVisible();
    await expect(page.getByText('Market Narrative')).toBeVisible();
    await expect(page.getByText('Analytics Insight')).toBeVisible();
    
    // Verify AI badges are present
    const aiBadges = page.locator('.model-badge:has-text("AI")');
    expect(await aiBadges.count()).toBeGreaterThanOrEqual(3);
  });

  test('stress leaderboard displays chain data', async ({ page }) => {
    // Check stress leaderboard section
    await expect(page.getByText('Stress Leaderboard')).toBeVisible();
    
    // Check for chain velocity indicator
    await expect(page.getByText('Chains ranked by supply velocity')).toBeVisible();
  });

  test('rotation data displays cross-asset correlations', async ({ page }) => {
    // Check rotation section
    await expect(page.getByText('Rotation')).toBeVisible();
    
    // Check for correlation indicator
    await expect(page.getByText('Cross-asset supply rotation')).toBeVisible();
  });

  test('anomaly events display properly', async ({ page }) => {
    // Scroll to anomaly section
    const anomalySection = page.getByText('Recent Anomalies');
    await anomalySection.scrollIntoViewIfNeeded();
    
    // Check that anomaly section exists
    await expect(anomalySection).toBeVisible();
  });

  test('chain cards display supply distribution', async ({ page }) => {
    // Check that chain grid exists
    const chainGrid = page.locator('.chain-grid');
    
    // If chains exist, verify chain cards
    if (await chainGrid.isVisible()) {
      const chainCards = page.locator('.chain-card');
      if (await chainCards.count() > 0) {
        // Check first chain card has required elements
        const firstCard = chainCards.first();
        await expect(firstCard.locator('.chain-name')).toBeVisible();
        await expect(firstCard.locator('.chain-peg')).toBeVisible();
      }
    }
  });
});