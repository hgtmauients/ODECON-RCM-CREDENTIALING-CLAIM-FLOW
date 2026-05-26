import { test, expect } from '@playwright/test';
import { mockAuthenticatedDashboardApis } from './support/mockApi';

test.describe('Visual regression @visual', () => {
  test('login page remains visually stable @visual', async ({ page }) => {
    await page.goto('/login');
    await expect(page).toHaveScreenshot('login-page.png', {
      fullPage: true,
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.05,
    });
  });

  test('dashboard shell remains visually stable @visual', async ({ page }) => {
    await mockAuthenticatedDashboardApis(page);
    await page.goto('/login');
    await page.getByPlaceholder('you@company.com').fill('admin@app.io');
    await page.getByPlaceholder('Enter your password').fill('admin');
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page.getByRole('heading', { name: /hello, admin/i })).toBeVisible();

    await expect(page).toHaveScreenshot('dashboard-shell.png', {
      fullPage: true,
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.05,
    });
  });
});
