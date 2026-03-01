import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: 'tests/e2e',
  use: {
    channel: 'msedge',
  },
  projects: [
    {
      name: 'Edge',
      testMatch: ['sidebar.spec.ts'],
      use: { ...devices['Desktop Edge'] },
    },
    {
      name: 'Management SPA',
      testMatch: ['management/**/*.spec.ts'],
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://localhost:8765',
      },
    },
  ],
  webServer: {
    command: 'cd ../backend && python -m uv run uvicorn app.main:app --port 8765',
    port: 8765,
    reuseExistingServer: true,
    timeout: 30000,
  },
})
