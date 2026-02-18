import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: 'tests/e2e',
  use: {
    channel: 'msedge',
  },
  projects: [
    {
      name: 'Edge',
      use: { ...devices['Desktop Edge'] },
    },
  ],
})
