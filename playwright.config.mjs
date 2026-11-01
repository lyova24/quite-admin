import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [['list'], ['html', {open:'never'}]],
  use: {
    baseURL: 'http://127.0.0.1:8127',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: ['chromium','firefox','webkit'].map(browserName=>({
    name: browserName,
    use: {browserName, ...(browserName === 'chromium' && process.env.QUITE_ADMIN_BROWSER_EXECUTABLE
      ? {launchOptions:{executablePath:process.env.QUITE_ADMIN_BROWSER_EXECUTABLE}} : {})},
  })),
  webServer: [{
    command: 'uv run --no-sync uvicorn tests.browser_app:app --host 127.0.0.1 --port 8127 --log-level warning',
    url: 'http://127.0.0.1:8127/health',
    reuseExistingServer: false,
    timeout: 30000,
  }, {
    command: 'uv run --no-sync python scripts/build_demo.py && uv run --no-sync python -m http.server 8128 --bind 127.0.0.1 --directory build/docs/demo',
    url: 'http://127.0.0.1:8128/',
    reuseExistingServer: false,
    timeout: 30000,
  }],
});
