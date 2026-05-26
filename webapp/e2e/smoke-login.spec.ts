import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mockAuthenticatedDashboardApis } from './support/mockApi';

test.describe('Login smoke', () => {
  test('redirects unauthenticated users to login', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole('heading', { name: /provider onboarding & rcm/i })).toBeVisible();
  });

  test('shows login failure and has no critical accessibility violations', async ({ page }) => {
    await page.route('**/api/auth/login', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Invalid credentials' }),
      });
    });

    await page.goto('/login');
    await page.getByPlaceholder('you@company.com').fill('admin@app.io');
    await page.getByPlaceholder('Enter your password').fill('wrong-password');
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page.getByText('Invalid credentials')).toBeVisible();

    const a11y = await new AxeBuilder({ page }).analyze();
    const criticalViolations = a11y.violations.filter((v) => v.impact === 'critical');
    expect(criticalViolations).toEqual([]);
  });

  test('supports mocked authenticated login and dashboard shell render', async ({ page }) => {
    await mockAuthenticatedDashboardApis(page);
    await page.goto('/login');

    await page.getByPlaceholder('you@company.com').fill('admin@app.io');
    await page.getByPlaceholder('Enter your password').fill('admin');
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('heading', { name: /hello, admin/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /create claim/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /notifications/i })).toBeVisible();
  });
});
