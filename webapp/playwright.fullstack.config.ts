import { defineConfig, devices } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
const webPort = Number(process.env.PLAYWRIGHT_WEB_PORT || 4173);
const apiPort = Number(process.env.PLAYWRIGHT_API_PORT || 8000);
const baseURL = process.env.PLAYWRIGHT_BASE_URL || `http://127.0.0.1:${webPort}`;
const pythonExec = process.platform === 'win32' ? 'py' : 'python3';
const backendCmd = process.env.PLAYWRIGHT_BACKEND_CMD || `${pythonExec} -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`;

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: backendCmd,
      cwd: path.resolve(here, '../backend'),
      port: apiPort,
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: {
        ...process.env,
        CORS_ORIGINS: process.env.CORS_ORIGINS || `http://127.0.0.1:${webPort},http://localhost:${webPort}`,
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${webPort}`,
      cwd: here,
      port: webPort,
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: {
        ...process.env,
        VITE_API_PROXY_TARGET: `http://127.0.0.1:${apiPort}`,
      },
    },
  ],
});
