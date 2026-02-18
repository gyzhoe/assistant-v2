import { test, expect } from '@playwright/test'

// E2E tests require the extension loaded in Edge.
// These are placeholder stubs — full E2E implemented in Phase 9.

test.describe('Sidebar E2E (stubs)', () => {
  test('placeholder — sidebar loads', async ({ page }) => {
    // Full E2E requires Edge with extension loaded — skip in basic CI
    test.skip(true, 'E2E requires Edge with extension loaded')
    await page.goto('chrome-extension://placeholder/sidebar.html')
    await expect(page.locator('h1')).toContainText('Helpdesk Assistant')
  })
})
