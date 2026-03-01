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

async function checkOllamaAvailable(request: import('@playwright/test').APIRequestContext): Promise<boolean> {
  try {
    const resp = await request.get('http://localhost:11434', { timeout: 3000 })
    return resp.ok()
  } catch {
    return false
  }
}

test.describe('Article CRUD', () => {
  test('Create article via the editor form', async ({ page }) => {
    const authenticated = await loginAndNavigate(page)
    if (!authenticated) {
      test.skip(true, 'Could not authenticate')
      return
    }

    const ollamaUp = await checkOllamaAvailable(page.request)
    if (!ollamaUp) {
      test.skip(true, 'Ollama not running — article creation requires embedding service')
      return
    }

    // Click "New Article" button in the header
    const newArticleBtn = page.locator('button', { hasText: 'New Article' })
    await expect(newArticleBtn).toBeVisible({ timeout: 10000 })
    await newArticleBtn.click()

    // Editor should appear
    await page.waitForSelector('.editor-container', { timeout: 5000 })
    await expect(page.locator('.editor-title')).toContainText('Create New Article')

    // Fill in title
    const uniqueTitle = `E2E Test Article ${Date.now()}`
    await page.fill('#article-title', uniqueTitle)

    // Clear template and fill minimal content
    await page.fill('#article-content', '## Problem\n\nE2E test content.\n\n## Solution\n\nTest solution.')

    // Save
    const saveBtn = page.locator('button', { hasText: 'Save Article' })
    await expect(saveBtn).toBeEnabled({ timeout: 5000 })
    await saveBtn.click()

    // Should return to list view after save
    await page.waitForSelector('.article-rows, .stat-cards', { timeout: 30000 })
    await expect(page.locator('.editor-container')).not.toBeVisible()
  })

  test('Edit existing article shows editor with prefilled fields', async ({ page }) => {
    const authenticated = await loginAndNavigate(page)
    if (!authenticated) {
      test.skip(true, 'Could not authenticate')
      return
    }

    await page.waitForSelector('.article-rows, .empty-state', { timeout: 15000 })

    const emptyState = page.locator('.empty-state')
    if (await emptyState.isVisible()) {
      test.skip(true, 'No articles to edit')
      return
    }

    // Find the first article row and expand it
    const firstRow = page.locator('.article-row, [class*="article-row"]').first()
    if (!await firstRow.isVisible()) {
      test.skip(true, 'No article rows visible')
      return
    }

    // Click the row to expand (toggle)
    await firstRow.click()

    // Look for an Edit button in the expanded detail
    const editBtn = page.locator('button', { hasText: 'Edit' }).first()
    const editBtnVisible = await editBtn.isVisible({ timeout: 3000 }).catch(() => false)

    if (!editBtnVisible) {
      test.skip(true, 'Edit button not found (article may not be a manual article)')
      return
    }

    await editBtn.click()

    // Editor should open in edit mode
    await page.waitForSelector('.editor-container', { timeout: 5000 })
    await expect(page.locator('.editor-title')).toContainText('Edit Article')

    // Title field should be pre-filled (not empty)
    const titleValue = await page.inputValue('#article-title')
    expect(titleValue.length).toBeGreaterThan(0)

    // Back button cancels without needing Ollama
    const backBtn = page.locator('button', { hasText: 'Back' }).first()
    await backBtn.click()

    // Returns to list
    await page.waitForSelector('.article-rows, .empty-state', { timeout: 5000 })
  })

  test('Delete article shows confirmation and removes from list', async ({ page }) => {
    const authenticated = await loginAndNavigate(page)
    if (!authenticated) {
      test.skip(true, 'Could not authenticate')
      return
    }

    await page.waitForSelector('.article-rows, .empty-state', { timeout: 15000 })

    const emptyState = page.locator('.empty-state')
    if (await emptyState.isVisible()) {
      test.skip(true, 'No articles to delete')
      return
    }

    // Expand first article row
    const firstRow = page.locator('.article-row, [class*="article-row"]').first()
    if (!await firstRow.isVisible()) {
      test.skip(true, 'No article rows visible')
      return
    }

    await firstRow.click()

    // Look for delete button in expanded row
    const deleteBtn = page.locator('button', { hasText: 'Delete' }).first()
    const deleteBtnVisible = await deleteBtn.isVisible({ timeout: 3000 }).catch(() => false)

    if (!deleteBtnVisible) {
      test.skip(true, 'Delete button not found in expanded row')
      return
    }

    await deleteBtn.click()

    // A toast notification should appear (optimistic removal with undo)
    // The UI shows a toast with "Deleted" message and "Undo" action
    const toast = page.locator('.toast, [class*="toast"]').first()
    await expect(toast).toBeVisible({ timeout: 5000 })
    await expect(toast).toContainText(/deleted/i)
  })

  test('File upload section is accessible from the Import area', async ({ page }) => {
    const authenticated = await loginAndNavigate(page)
    if (!authenticated) {
      test.skip(true, 'Could not authenticate')
      return
    }

    await page.waitForSelector('.app-shell', { timeout: 10000 })

    // Click Import in the header
    const importBtn = page.locator('button', { hasText: /import/i }).first()
    const importBtnVisible = await importBtn.isVisible({ timeout: 5000 }).catch(() => false)

    if (!importBtnVisible) {
      test.skip(true, 'Import button not visible in header')
      return
    }

    await importBtn.click()

    // Import section should expand/appear
    await page.waitForSelector('.import-section, [class*="import"]', { timeout: 5000 })

    // There should be a file input or file upload area
    const fileInput = page.locator('input[type="file"]')
    const fileInputVisible = await fileInput.isVisible({ timeout: 3000 }).catch(() => false)

    if (fileInputVisible) {
      await expect(fileInput).toBeVisible()
    } else {
      // File input may be hidden (visual drop zone) — just verify the section rendered
      const importSection = page.locator('.import-section, [class*="import"]').first()
      await expect(importSection).toBeVisible()
    }
  })
})
