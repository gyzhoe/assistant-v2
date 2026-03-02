import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock chrome APIs
vi.stubGlobal('chrome', {
  storage: {
    sync: { get: vi.fn((_k, cb) => cb({})) },
    local: { get: vi.fn((_k, cb) => cb({})) },
  },
  runtime: {
    sendMessage: vi.fn(),
    onMessage: { addListener: vi.fn(), removeListener: vi.fn() },
  },
})

describe('DOMInserter', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    // jsdom doesn't implement scrollIntoView
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('inserts text into textarea#techNotes', async () => {
    document.body.innerHTML = '<textarea id="techNotes"></textarea>'
    const { DOMInserter } = await import('../../src/content/dom-inserter')
    const inserter = new DOMInserter()

    const result = inserter.insertReply('Hello, try restarting your computer.')
    expect(result).toBe(true)

    const textarea = document.querySelector('#techNotes') as HTMLTextAreaElement
    expect(textarea.value).toBe('Hello, try restarting your computer.')
  })

  it('returns false when textarea is not found', async () => {
    document.body.innerHTML = '<div>No textarea here</div>'
    const { DOMInserter } = await import('../../src/content/dom-inserter')
    const inserter = new DOMInserter()

    const result = inserter.insertReply('Hello')
    expect(result).toBe(false)
  })

  it('dispatches input and change events', async () => {
    document.body.innerHTML = '<textarea id="techNotes"></textarea>'
    const textarea = document.querySelector('#techNotes') as HTMLTextAreaElement
    const inputSpy = vi.fn()
    const changeSpy = vi.fn()
    textarea.addEventListener('input', inputSpy)
    textarea.addEventListener('change', changeSpy)

    const { DOMInserter } = await import('../../src/content/dom-inserter')
    const inserter = new DOMInserter()
    inserter.insertReply('Test')

    expect(inputSpy).toHaveBeenCalledTimes(1)
    expect(changeSpy).toHaveBeenCalledTimes(1)
  })

  it('uses native setter when available', async () => {
    document.body.innerHTML = '<textarea id="techNotes"></textarea>'
    const textarea = document.querySelector('#techNotes') as HTMLTextAreaElement

    // Spy on the native setter
    const nativeDescriptor = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      'value'
    )
    const originalSet = nativeDescriptor?.set
    const setSpy = vi.fn(function (this: HTMLTextAreaElement, val: string) {
      originalSet?.call(this, val)
    })
    Object.defineProperty(HTMLTextAreaElement.prototype, 'value', {
      ...nativeDescriptor,
      set: setSpy,
    })

    const { DOMInserter } = await import('../../src/content/dom-inserter')
    const inserter = new DOMInserter()
    inserter.insertReply('Native setter test')

    expect(setSpy).toHaveBeenCalled()
    expect(textarea.value).toBe('Native setter test')

    // Restore
    Object.defineProperty(HTMLTextAreaElement.prototype, 'value', nativeDescriptor!)
  })

  it('falls back to textarea[name="techNote"]', async () => {
    document.body.innerHTML = '<textarea name="techNote"></textarea>'
    const { DOMInserter } = await import('../../src/content/dom-inserter')
    const inserter = new DOMInserter()

    const result = inserter.insertReply('Fallback test')
    expect(result).toBe(true)

    const textarea = document.querySelector('textarea[name="techNote"]') as HTMLTextAreaElement
    expect(textarea.value).toBe('Fallback test')
  })

  it('uses custom selector when set', async () => {
    document.body.innerHTML = '<textarea id="techNotes"></textarea><textarea class="custom-target"></textarea>'
    const { DOMInserter } = await import('../../src/content/dom-inserter')
    const inserter = new DOMInserter()
    inserter.setCustomSelector('textarea.custom-target')

    const result = inserter.insertReply('Custom target text')
    expect(result).toBe(true)

    const customTextarea = document.querySelector('textarea.custom-target') as HTMLTextAreaElement
    expect(customTextarea.value).toBe('Custom target text')
    // Default textarea should not be affected
    const defaultTextarea = document.querySelector('#techNotes') as HTMLTextAreaElement
    expect(defaultTextarea.value).toBe('')
  })

  it('falls back to default selectors when custom selector finds nothing', async () => {
    document.body.innerHTML = '<textarea id="techNotes"></textarea>'
    const { DOMInserter } = await import('../../src/content/dom-inserter')
    const inserter = new DOMInserter()
    inserter.setCustomSelector('textarea.nonexistent')

    const result = inserter.insertReply('Fallback to default')
    expect(result).toBe(true)

    const textarea = document.querySelector('#techNotes') as HTMLTextAreaElement
    expect(textarea.value).toBe('Fallback to default')
  })

  it('returns false when custom selector matches non-textarea element', async () => {
    document.body.innerHTML = '<div class="not-textarea">Not a textarea</div>'
    const { DOMInserter } = await import('../../src/content/dom-inserter')
    const inserter = new DOMInserter()
    inserter.setCustomSelector('div.not-textarea')

    const result = inserter.insertReply('Should fail')
    expect(result).toBe(false)
  })
})
