import { test, expect } from '@playwright/test'

// Sidebar E2E tests require the extension loaded in Edge with a chrome-extension:// URL.
// Playwright cannot load unpacked extensions in headed mode without special launch args,
// and the sidebar itself has no chrome.* API polyfills for a standalone browser context.
//
// These tests are deferred until extension loading via Playwright is fully supported.
// See: https://playwright.dev/docs/chrome-extensions
//
// For now, use the Management SPA E2E tests (tests/e2e/management/) which test
// the full stack against the FastAPI backend without extension dependencies.

test.describe('Sidebar E2E', () => {
  test('placeholder — sidebar loads', async ({ page }) => {
    test.skip(true, 'Sidebar E2E deferred: requires Edge with extension loaded via Playwright launch args')
    await page.goto('chrome-extension://placeholder/sidebar.html')
    await expect(page.locator('h1')).toContainText('Helpdesk Assistant')
  })
})
