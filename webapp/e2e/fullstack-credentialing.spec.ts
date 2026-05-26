import { test, expect } from '@playwright/test';

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL || 'ci.e2e.fullstack@noodledoc.com';
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD || 'admin';

test.describe('Full-stack credentialing flow @fullstack', () => {
  test('supports login + session/csrf + add provider', async ({ page }) => {
    const suffix = Date.now().toString().slice(-8);
    const npi = `9${suffix}${Math.floor(Math.random() * 10)}`.slice(0, 10);

    await page.goto('/login');
    await page.getByPlaceholder('you@company.com').fill(ADMIN_EMAIL);
    await page.getByPlaceholder('Enter your password').fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('heading', { name: /hello,/i })).toBeVisible();

    await page.getByRole('button', { name: /open credentialing queue/i }).click();
    await expect(page).toHaveURL(/\/credentialing$/);
    await expect(page.getByRole('heading', { name: /provider credentialing queue/i })).toBeVisible();

    await page.getByTestId('add-provider-open-btn').click();
    await page.getByTestId('add-provider-first-name').fill('Nathan');
    await page.getByTestId('add-provider-last-name').fill('Harrington-Foster');
    await page.getByTestId('add-provider-npi').fill(npi);
    await page.getByTestId('add-provider-submit-btn').click();

    await expect(page.getByText(/created\. verification checks running\./i)).toBeVisible();
    await expect(page.getByText(new RegExp(`NPI:\\s*${npi}`))).toBeVisible();
  });
});
