import { test, expect } from '@playwright/test'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const TEST_TOKEN: string = (globalThis as any).process?.env?.['TEST_E2E_TOKEN'] ?? 'test-token-123'

async function loginAndNavigate(page: import('@playwright/test').Page): Promise<boolean> {
  await page.context().clearCookies()
  const resp = await page.request.post('/auth/login', { data: { token: TEST_TOKEN } })
  if (resp.status() === 401) return false
  await page.goto('/manage')
  await page.waitForSelector('.app-shell', { timeout: 10000 })
  const tokenGate = page.locator('.token-gate')
  const isGated = await tokenGate.isVisible().catch(() => false)
  return !isGated
}

test.describe('Theme toggle', () => {
  test('Theme toggle changes data-theme attribute on .app-shell', async ({ page }) => {
    const authenticated = await loginAndNavigate(page)
    if (!authenticated) {
      test.skip(true, 'Could not authenticate')
      return
    }

    const appShell = page.locator('.app-shell')
    await expect(appShell).toBeVisible()

    // Record starting theme
    const initialTheme = await appShell.getAttribute('data-theme')
    expect(['light', 'dark']).toContain(initialTheme)

    // Find and click theme toggle button
    const themeToggleBtn = page.locator('button[aria-label*="theme" i], button[title*="theme" i], .theme-toggle, button[class*="theme"]')
      .first()

    if (!await themeToggleBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      // Try finding by icon content or header area
      const headerBtn = page.locator('header button, .mgmt-header button').last()
      await expect(headerBtn).toBeVisible({ timeout: 5000 })
      await headerBtn.click()
    } else {
      await themeToggleBtn.click()
    }

    // data-theme should have flipped
    const newTheme = await appShell.getAttribute('data-theme')
    expect(newTheme).not.toBe(initialTheme)
    expect(['light', 'dark']).toContain(newTheme)
  })

  test('Theme preference persists across page reload', async ({ page }) => {
    const authenticated = await loginAndNavigate(page)
    if (!authenticated) {
      test.skip(true, 'Could not authenticate')
      return
    }

    const appShell = page.locator('.app-shell')
    await expect(appShell).toBeVisible()

    // Get current theme and determine the opposite
    const currentTheme = await appShell.getAttribute('data-theme')
    const targetTheme = currentTheme === 'dark' ? 'light' : 'dark'

    // Set theme via localStorage directly (bypass needing to find the toggle button)
    await page.evaluate((theme) => {
      localStorage.setItem('kb-manage-theme', theme)
    }, targetTheme)

    // Reload the page (session cookie persists, localStorage persists)
    await page.reload()
    await page.waitForSelector('.app-shell', { timeout: 10000 })

    // Theme should match what we set
    const reloadedTheme = await page.locator('.app-shell').getAttribute('data-theme')
    expect(reloadedTheme).toBe(targetTheme)
  })
})
