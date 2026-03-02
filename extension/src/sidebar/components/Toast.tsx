import React, { useState, useEffect, useCallback, useRef } from 'react'

export interface SidebarToastMessage {
  id: string
  text: string
  type: 'success' | 'error' | 'info'
}

const AUTO_DISMISS_MS = 4000

let addToastFn: ((t: SidebarToastMessage) => void) | null = null

export function showSidebarToast(
  text: string,
  type: SidebarToastMessage['type'] = 'info',
): void {
  addToastFn?.({ id: crypto.randomUUID(), text, type })
}

export function SidebarToastContainer(): React.ReactElement {
  const [toasts, setToasts] = useState<SidebarToastMessage[]>([])
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
    (t: SidebarToastMessage) => {
      setToasts((prev) => [...prev, t])
      const timer = setTimeout(() => remove(t.id), AUTO_DISMISS_MS)
      timers.current.set(t.id, timer)
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
    <div className="sidebar-toast-container" aria-live="polite" role="status">
      {toasts.map((t) => (
        <div key={t.id} className={`sidebar-toast sidebar-toast-${t.type}`}>
          <span className="sidebar-toast-text">{t.text}</span>
          <button
            type="button"
            className="sidebar-toast-close"
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
