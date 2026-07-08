import { test, expect } from '@playwright/test';
import { waitForAlpine } from './helpers/auth';

test.describe('Market tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/#market');
    await waitForAlpine(page);
  });

  test('renders peg forecast panel', async ({ page }) => {
    await expect(page.locator('#tab-market')).toBeVisible();
    await expect(page.getByText('Peg Forecast').first()).toBeVisible();
  });
});
