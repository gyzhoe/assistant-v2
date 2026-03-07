import type { SSEEvent } from '../shared/types'
import { debugError } from '../shared/constants'

const DATA_PREFIX = 'data: '

/**
 * Parses a ReadableStream of SSE bytes into an async iterable of typed SSE events.
 * Handles line buffering across chunk boundaries.
 */
export async function* parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      if (signal?.aborted) return

      const { done, value } = await reader.read()
      if (done) return

      buffer += decoder.decode(value, { stream: true })

      // SSE events are separated by double newlines
      const parts = buffer.split('\n\n')
      // Last part may be incomplete — keep it in the buffer
      buffer = parts.pop() ?? ''

      for (const part of parts) {
        const line = part.trim()
        if (!line || !line.startsWith(DATA_PREFIX)) continue

        const jsonStr = line.slice(DATA_PREFIX.length)
        try {
          const event = JSON.parse(jsonStr) as SSEEvent
          yield event
        } catch {
          debugError('SSE: failed to parse event:', jsonStr)
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
