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

async function fillAlpineInput(page: Page, placeholder: string, value: string) {
  const input = page.getByPlaceholder(placeholder);
  await input.fill(value);
  await input.dispatchEvent('input');
  await input.dispatchEvent('change');
}

async function signInAsAdmin(page: Page, username: string, password: string) {
  await fillAlpineInput(page, 'Username', username);
  await fillAlpineInput(page, 'Password', password);
  await page.evaluate(async ([u, p]) => {
    const root = document.documentElement as any;
    const ui = root._x_dataStack?.[0]?.$store?.ui;
    if (ui) {
      ui.loginUsername = u;
      ui.loginPassword = p;
    }
    const gov = (document.querySelector('#tab-settings') as any)?._x_dataStack?.[0];
    if (!gov?.submitAdminLogin) throw new Error('governance component not ready');
    await gov.submitAdminLogin();
  }, [username, password]);
  await expect(page.getByRole('button', { name: /Test AI/i })).toBeVisible({ timeout: 120000 });
}

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
      /* .env not present */
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
    await signInAsAdmin(page, username, password);
  });

  test('loads settings tab with admin login', async ({ page }) => {
    await expect(page.locator('#tab-settings input[type="password"]').first()).toBeVisible();
    await expect(page.locator('#tab-settings').getByRole('heading', { name: 'Admin Login' })).toBeVisible();
  });

  test('shows Open Admin Panel and AI surface after login', async ({ page }) => {
    const panel = page.locator('#tab-settings');
    await expect(panel.getByRole('link', { name: /Open Admin Panel/i })).toBeVisible();
    await expect(panel.getByText('AI Feature Mapping')).toBeVisible();
    await expect(panel.getByRole('button', { name: /Test provider chain/i })).toBeVisible();
  });

  test('shows AI status budget line', async ({ page }) => {
    await expect(page.locator('#tab-settings').getByText(/Mode:/i)).toBeVisible({ timeout: 120000 });
  });
});
