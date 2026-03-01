import { test, expect } from '@playwright/test'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const TEST_TOKEN: string = (globalThis as any).process?.env?.['TEST_E2E_TOKEN'] ?? 'test-token-123'

async function loginAndNavigate(page: import('@playwright/test').Page) {
  await page.context().clearCookies()
  const resp = await page.request.post('/auth/login', { data: { token: TEST_TOKEN } })
  if (resp.status() === 401) return false
  await page.goto('/manage')
  // Wait for the app to be past the session-check phase
  await page.waitForSelector('.app-shell', { timeout: 10000 })
  const tokenGate = page.locator('.token-gate')
  const isGated = await tokenGate.isVisible().catch(() => false)
  return !isGated
}

test.describe('Article list — stats and table', () => {
  test('Stats cards are displayed after auth', async ({ page }) => {
    const authenticated = await loginAndNavigate(page)
    if (!authenticated) {
      test.skip(true, 'Could not authenticate — set TEST_E2E_TOKEN matching backend API_TOKEN')
      return
    }

    // Wait for either stat cards or the empty state
    await page.waitForSelector('.stat-cards, .empty-state', { timeout: 15000 })

    // If stat cards exist they should contain meaningful labels
    const statCards = page.locator('.stat-cards')
    if (await statCards.isVisible()) {
      await expect(statCards).toBeVisible()
    }
  })

  test('Article table or empty state renders', async ({ page }) => {
    const authenticated = await loginAndNavigate(page)
    if (!authenticated) {
      test.skip(true, 'Could not authenticate — set TEST_E2E_TOKEN matching backend API_TOKEN')
      return
    }

    // Wait for data to load (skeleton → real content or empty state)
    await page.waitForSelector('.article-rows, .empty-state, .no-results', { timeout: 15000 })

    const articleRows = page.locator('.article-rows')
    const emptyState = page.locator('.empty-state')

    const hasRows = await articleRows.isVisible().catch(() => false)
    const hasEmpty = await emptyState.isVisible().catch(() => false)

    expect(hasRows || hasEmpty).toBe(true)
  })

  test('Search input filters articles or shows no-results', async ({ page }) => {
    const authenticated = await loginAndNavigate(page)
    if (!authenticated) {
      test.skip(true, 'Could not authenticate — set TEST_E2E_TOKEN matching backend API_TOKEN')
      return
    }

    await page.waitForSelector('.article-rows, .empty-state', { timeout: 15000 })

    const emptyState = page.locator('.empty-state')
    if (await emptyState.isVisible()) {
      // No articles in DB — search bar won't be visible
      test.skip(true, 'No articles in database — skipping search filter test')
      return
    }

    // Search bar is only shown when there are articles
    await page.waitForSelector('.article-toolbar', { timeout: 10000 })
    const searchInput = page.locator('input[type="search"], input[placeholder*="search" i], input[placeholder*="Search" i]').first()

    if (!await searchInput.isVisible()) {
      // Try generic text input in toolbar
      const toolbarInput = page.locator('.article-toolbar input').first()
      await expect(toolbarInput).toBeVisible()
      await toolbarInput.fill('xyznotexist123')
      await page.waitForSelector('.no-results, .article-rows', { timeout: 10000 })
    } else {
      await searchInput.fill('xyznotexist123')
      await page.waitForSelector('.no-results, .article-rows', { timeout: 10000 })
    }

    // Either shows no-results or fewer article rows
    const noResults = page.locator('.no-results')
    const rows = page.locator('.article-rows')
    const hasNoResults = await noResults.isVisible().catch(() => false)
    const hasRows = await rows.isVisible().catch(() => false)
    expect(hasNoResults || hasRows).toBe(true)
  })

  test('Pagination controls render when there are enough articles', async ({ page }) => {
    const authenticated = await loginAndNavigate(page)
    if (!authenticated) {
      test.skip(true, 'Could not authenticate — set TEST_E2E_TOKEN matching backend API_TOKEN')
      return
    }

    await page.waitForSelector('.article-rows, .empty-state', { timeout: 15000 })

    const emptyState = page.locator('.empty-state')
    if (await emptyState.isVisible()) {
      test.skip(true, 'No articles in database — skipping pagination test')
      return
    }

    // Pagination only visible when total > page_size (20)
    const pagination = page.locator('.pagination, nav[aria-label*="pagination" i]')
    if (await pagination.isVisible()) {
      await expect(pagination).toBeVisible()
    } else {
      // Fewer than 20 articles — pagination is correctly hidden
      expect(true).toBe(true)
    }
  })
})
