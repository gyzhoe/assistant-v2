import { describe, it, expect } from 'vitest'
import type { SSEEvent } from '../../src/shared/types'
import { parseSSEStream } from '../../src/lib/sse-parser'

/** Helper: encode a string as a ReadableStream of Uint8Array chunks */
function makeReadableStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  let index = 0
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index]))
        index++
      } else {
        controller.close()
      }
    },
  })
}

/** Collect all events from an async generator */
async function collect(gen: AsyncGenerator<SSEEvent>): Promise<SSEEvent[]> {
  const events: SSEEvent[] = []
  for await (const event of gen) {
    events.push(event)
  }
  return events
}

describe('parseSSEStream', () => {
  it('parses a complete SSE stream with meta, tokens, and done', async () => {
    const stream = makeReadableStream([
      'data: {"type":"meta","context_docs":[{"content":"KB","source":"kb","score":0.9,"metadata":{}}]}\n\n',
      'data: {"type":"token","content":"Hello"}\n\n',
      'data: {"type":"token","content":" world"}\n\n',
      'data: {"type":"done","latency_ms":150}\n\n',
    ])

    const events = await collect(parseSSEStream(stream.getReader()))

    expect(events).toHaveLength(4)
    expect(events[0]).toEqual({ type: 'meta', context_docs: [{ content: 'KB', source: 'kb', score: 0.9, metadata: {} }] })
    expect(events[1]).toEqual({ type: 'token', content: 'Hello' })
    expect(events[2]).toEqual({ type: 'token', content: ' world' })
    expect(events[3]).toEqual({ type: 'done', latency_ms: 150 })
  })

  it('handles chunks split across event boundaries', async () => {
    // Token event split across two chunks
    const stream = makeReadableStream([
      'data: {"type":"token","con',
      'tent":"split"}\n\ndata: {"type":"done","latency_ms":10}\n\n',
    ])

    const events = await collect(parseSSEStream(stream.getReader()))

    expect(events).toHaveLength(2)
    expect(events[0]).toEqual({ type: 'token', content: 'split' })
    expect(events[1]).toEqual({ type: 'done', latency_ms: 10 })
  })

  it('handles SSE error events', async () => {
    const stream = makeReadableStream([
      'data: {"type":"token","content":"partial"}\n\n',
      'data: {"type":"error","error_code":"LLM_DOWN","message":"Server crashed"}\n\n',
    ])

    const events = await collect(parseSSEStream(stream.getReader()))

    expect(events).toHaveLength(2)
    expect(events[0]).toEqual({ type: 'token', content: 'partial' })
    expect(events[1]).toEqual({ type: 'error', error_code: 'LLM_DOWN', message: 'Server crashed' })
  })

  it('skips malformed JSON lines without crashing', async () => {
    const stream = makeReadableStream([
      'data: {"type":"token","content":"ok"}\n\n',
      'data: {INVALID JSON}\n\n',
      'data: {"type":"done","latency_ms":5}\n\n',
    ])

    const events = await collect(parseSSEStream(stream.getReader()))

    expect(events).toHaveLength(2)
    expect(events[0]).toEqual({ type: 'token', content: 'ok' })
    expect(events[1]).toEqual({ type: 'done', latency_ms: 5 })
  })

  it('ignores non-data lines (comments, empty lines)', async () => {
    const stream = makeReadableStream([
      ': this is a comment\n\n',
      '\n\n',
      'data: {"type":"token","content":"hi"}\n\n',
    ])

    const events = await collect(parseSSEStream(stream.getReader()))

    expect(events).toHaveLength(1)
    expect(events[0]).toEqual({ type: 'token', content: 'hi' })
  })

  it('stops when signal is aborted', async () => {
    const controller = new AbortController()
    const stream = makeReadableStream([
      'data: {"type":"token","content":"first"}\n\n',
      'data: {"type":"token","content":"second"}\n\n',
    ])

    const reader = stream.getReader()
    const gen = parseSSEStream(reader, controller.signal)

    const first = await gen.next()
    expect(first.value).toEqual({ type: 'token', content: 'first' })

    controller.abort()
    const next = await gen.next()
    expect(next.done).toBe(true)
  })

  it('handles empty stream gracefully', async () => {
    const stream = makeReadableStream([])
    const events = await collect(parseSSEStream(stream.getReader()))
    expect(events).toHaveLength(0)
  })

  it('handles multiple events in a single chunk', async () => {
    const stream = makeReadableStream([
      'data: {"type":"token","content":"a"}\n\ndata: {"type":"token","content":"b"}\n\ndata: {"type":"done","latency_ms":1}\n\n',
    ])

    const events = await collect(parseSSEStream(stream.getReader()))

    expect(events).toHaveLength(3)
    expect(events[0]).toEqual({ type: 'token', content: 'a' })
    expect(events[1]).toEqual({ type: 'token', content: 'b' })
    expect(events[2]).toEqual({ type: 'done', latency_ms: 1 })
  })
})
