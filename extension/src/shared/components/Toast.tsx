import React, { useState, useEffect, useCallback, useRef } from 'react'
import './Toast.css'
import type { ToastMessage } from '../types'

export type { ToastMessage }

const AUTO_DISMISS_MS = 4000

let addToastFn: ((t: ToastMessage) => void) | null = null

export function showToast(
  text: string,
  type: ToastMessage['type'] = 'info',
  options?: { persistent?: boolean; action?: ToastMessage['action'] },
): void {
  addToastFn?.({
    id: crypto.randomUUID(),
    text,
    type,
    persistent: options?.persistent,
    action: options?.action,
  })
}

export function ToastContainer(): React.ReactElement {
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  const remove = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
  }, [])

  const add = useCallback(
    (t: ToastMessage) => {
      setToasts((prev) => [...prev, t])
      // Persistent toasts must be dismissed manually
      if (!t.persistent) {
        const timer = setTimeout(() => remove(t.id), AUTO_DISMISS_MS)
        timers.current.set(t.id, timer)
      }
    },
    [remove],
  )

  useEffect(() => {
    addToastFn = add
    return () => {
      addToastFn = null
    }
  }, [add])

  if (toasts.length === 0) return <></>

  return (
    <div className="toast-container" aria-live="polite" role="status">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          <span className="toast-text">{t.text}</span>
          {t.action && (
            <button
              type="button"
              className="toast-action"
              onClick={() => {
                t.action?.onClick()
                remove(t.id)
              }}
            >
              {t.action.label}
            </button>
          )}
          <button
            type="button"
            className="toast-close"
            onClick={() => remove(t.id)}
            aria-label="Dismiss notification"
          >
            &times;
          </button>
        </div>
      ))}
    </div>
  )
}
