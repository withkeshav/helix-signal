import { Page, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { resolve } from 'path';

export async function waitForAlpine(page: Page) {
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
      const envText = readFileSync(resolve(__dirname, '../../../.env'), 'utf8');
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

export async function signInAsAdmin(page: Page) {
  const { username, password } = adminCreds();
  if (!username || !password) {
    throw new Error('Admin credentials not found — set HELIX_ADMIN_USERNAME/HELIX_ADMIN_PASSWORD env vars or repo .env');
  }
  await page.getByRole('tab', { name: /settings/i }).click();
  await waitForAlpine(page);
  // Wait for the Settings panel (x-if lazy mount) to be ready.
  await page.waitForFunction(
    () => {
      const panel = document.querySelector('#tab-settings');
      return !!(panel && (panel as any)._x_dataStack?.length);
    },
    null,
    { timeout: 10000 }
  );
  // Fill the login form inputs and dispatch events to sync Alpine x-model.
  await fillAlpineInput(page, 'Username', username);
  await fillAlpineInput(page, 'Password', password);
  // Set credentials directly in the Alpine store + call login() via $store magic.
  await page.evaluate(async ([u, p]) => {
    const root = document.documentElement as any;
    const ui = root._x_dataStack?.[0]?.$store?.ui;
    if (!ui) throw new Error('Alpine ui store not found');
    ui.loginUsername = u;
    ui.loginPassword = p;
    await ui.login();
  }, [username, password]);
  // Wait for post-login Settings surface (Test AI / Open Admin Panel).
  await expect(page.getByRole('button', { name: /Test AI/i })).toBeVisible({ timeout: 120000 });
}
