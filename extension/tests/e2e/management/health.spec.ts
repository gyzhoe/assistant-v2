import { test, expect } from '@playwright/test'

test.describe('Health and management page', () => {
  test('GET /health returns 200 with status ok', async ({ request }) => {
    const response = await request.get('/health')
    expect(response.status()).toBe(200)
    const body = await response.json() as { status: string }
    expect(body.status).toBe('ok')
  })

  test('management page loads at /manage', async ({ page }) => {
    const response = await page.goto('/manage')
    expect(response?.status()).toBe(200)
    const contentType = response?.headers()['content-type'] ?? ''
    expect(contentType).toContain('text/html')
  })
})
