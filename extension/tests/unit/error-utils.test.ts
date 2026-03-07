import { describe, it, expect } from 'vitest'
import { parseErrorDetail } from '../../src/lib/error-utils'

describe('parseErrorDetail', () => {
  it('extracts plain string detail', () => {
    expect(parseErrorDetail({ detail: 'Something went wrong' })).toBe('Something went wrong')
  })

  it('extracts message field', () => {
    expect(parseErrorDetail({ message: 'Not found' })).toBe('Not found')
  })

  it('prefers message over detail', () => {
    expect(parseErrorDetail({ message: 'Primary', detail: 'Secondary' })).toBe('Primary')
  })

  it('includes error_code prefix when present', () => {
    expect(parseErrorDetail({ error_code: 'LLM_DOWN', detail: 'Service unavailable' }))
      .toBe('[LLM_DOWN] Service unavailable')
  })

  it('does not prefix when error_code is the only useful field', () => {
    // error_code alone with no readable message
    expect(parseErrorDetail({ error_code: 'SOME_CODE' })).toBe('An unexpected error occurred')
  })

  it('handles Pydantic validation error array', () => {
    const body = {
      detail: [
        { loc: ['body', 'url'], msg: 'field required', type: 'value_error.missing' },
        { loc: ['body', 'name'], msg: 'must not be empty', type: 'value_error' },
      ],
    }
    const result = parseErrorDetail(body)
    expect(result).toContain('body -> url: field required')
    expect(result).toContain('body -> name: must not be empty')
  })

  it('handles nested object detail', () => {
    const body = { detail: { inner: { message: 'Deeply nested error' } } }
    expect(parseErrorDetail(body)).toBe('Deeply nested error')
  })

  it('never returns [object Object]', () => {
    const body = { detail: { foo: { bar: {} } } }
    const result = parseErrorDetail(body)
    expect(result).not.toContain('[object Object]')
  })

  it('returns fallback for empty body', () => {
    expect(parseErrorDetail({})).toBe('An unexpected error occurred')
  })

  it('handles error field', () => {
    expect(parseErrorDetail({ error: 'Connection refused' })).toBe('Connection refused')
  })

  it('handles msg field', () => {
    expect(parseErrorDetail({ msg: 'Validation failed' })).toBe('Validation failed')
  })

  it('handles numeric detail gracefully', () => {
    expect(parseErrorDetail({ detail: 500 as unknown as string })).toBe('500')
  })

  it('handles array of plain strings in detail', () => {
    const body = { detail: ['Error one', 'Error two'] }
    expect(parseErrorDetail(body)).toBe('Error one; Error two')
  })

  it('handles deeply nested objects without stack overflow', () => {
    // Build a deeply nested structure
    let obj: Record<string, unknown> = { message: 'Found it' }
    for (let i = 0; i < 20; i++) {
      obj = { nested: obj }
    }
    expect(parseErrorDetail(obj)).toBe('Found it')
  })

  it('combines error_code with nested message', () => {
    const body = { error_code: 'RATE_LIMIT', detail: { message: 'Too many requests' } }
    expect(parseErrorDetail(body)).toBe('[RATE_LIMIT] Too many requests')
  })

  it('returns fallback for null body', () => {
    expect(parseErrorDetail(null as unknown as Record<string, unknown>)).toBe('An unexpected error occurred')
  })

  it('returns fallback for undefined body', () => {
    expect(parseErrorDetail(undefined as unknown as Record<string, unknown>)).toBe('An unexpected error occurred')
  })

  it('handles circular references without crashing', () => {
    const body: Record<string, unknown> = { detail: {} }
    const inner = body['detail'] as Record<string, unknown>
    inner['self'] = body // circular reference
    const result = parseErrorDetail(body)
    expect(result).not.toContain('[object Object]')
    expect(result).toBe('An unexpected error occurred')
  })
})
