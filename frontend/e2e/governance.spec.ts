import { test, expect, Page } from '@playwright/test';
import { readFileSync } from 'fs';
import { resolve } from 'path';

async function waitForAlpine(page: Page) {
  await page.waitForFunction(
    () => !!(document.documentElement._x_dataStack && document.documentElement._x_dataStack.length),
    null,
    { timeout: 10000 }
  );
}

/** Sync Playwright fill() into Alpine x-model bindings on the login form. */
async function fillAlpineInput(page: Page, placeholder: string, value: string) {
  const input = page.getByPlaceholder(placeholder);
  await input.fill(value);
  await input.dispatchEvent('input');
  await input.dispatchEvent('change');
}

async function signInAsAdmin(page: Page, username: string, password: string) {
  await fillAlpineInput(page, 'Username', username);
  await fillAlpineInput(page, 'Password', password);
  await page.evaluate(async () => {
    const gov = (document.querySelector('#tab-settings') as any)?._x_dataStack?.[0];
    if (!gov?.submitAdminLogin) throw new Error('governance component not ready');
    await gov.submitAdminLogin();
  });
  await expect(
    page.locator('#tab-settings').getByRole('heading', { name: 'API Keys & Secrets' })
  ).toBeVisible({ timeout: 120000 });
}

/**
 * Admin credentials are read from the environment first, falling back to the
 * gitignored repo-root .env (docker-compose `env_file`). They are NEVER
 * hardcoded or committed. The Settings/Governance UI is admin-gated, so these
 * tests must authenticate through the real login form to render settings.
 */
function adminCreds(): { username: string; password: string } {
  let username = process.env.HELIX_ADMIN_USERNAME || '';
  let password = process.env.HELIX_ADMIN_PASSWORD || '';
  if (!username || !password) {
    try {
      const envText = readFileSync(resolve(__dirname, '../../.env'), 'utf8');
      for (const line of envText.split('\n')) {
        const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
        if (!m) continue;
        const val = m[2].replace(/^["']|["']$/g, '');
        if (m[1] === 'HELIX_ADMIN_USERNAME' && !username) username = val;
        if (m[1] === 'HELIX_ADMIN_PASSWORD' && !password) password = val;
      }
    } catch {
      /* .env not present — creds must come from the environment */
    }
  }
  return { username, password };
}

test.describe('Governance Tab (Settings)', () => {
  test.beforeEach(async ({ page }) => {
    const { username, password } = adminCreds();
    expect(username, 'HELIX_ADMIN_USERNAME must be available (env or .env)').toBeTruthy();
    expect(password, 'HELIX_ADMIN_PASSWORD must be available (env or .env)').toBeTruthy();

    await page.goto('/');
    await waitForAlpine(page);
    // Open the Settings tab (gear icon; accessible name "Settings").
    await page.getByRole('tab', { name: /settings/i }).click();
    await page.waitForFunction(
      () => {
        const panel = document.querySelector('#tab-settings');
        return !!(panel && (panel as any)._x_dataStack?.length);
      },
      null,
      { timeout: 10000 }
    );
    await expect(page.locator('.tab-content.settings')).toBeVisible();

    // Authenticate through the real login form so admin-gated settings render.
    await signInAsAdmin(page, username, password);
  });

  test('loads settings tab with admin token field', async ({ page }) => {
    // Admin authentication section renders with a password field + heading.
    await expect(page.locator('#tab-settings input[type="password"]').first()).toBeVisible();
    await expect(page.locator('#tab-settings').getByRole('heading', { name: 'Admin Login' })).toBeVisible();
  });

  test('loads settings list and API keys section', async ({ page }) => {
    const panel = page.locator('#tab-settings');
    await expect(panel.getByRole('heading', { name: 'API Keys & Secrets' })).toBeVisible();
    await expect(panel.getByRole('heading', { name: 'Data Providers' })).toBeVisible();
    await expect(panel.getByRole('heading', { name: 'Feature Toggles' })).toBeVisible();
    await expect(panel.getByRole('heading', { name: 'Refresh Intervals' })).toBeVisible();
    await expect(panel.getByRole('heading', { name: 'AI & Intelligence' })).toBeVisible();
  });

  test('loads AI budget display', async ({ page }) => {
    await expect(
      page.locator('#tab-settings').getByText('Daily AI Token Budget')
    ).toBeVisible({ timeout: 120000 });
  });
});
