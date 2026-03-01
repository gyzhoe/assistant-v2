import React, { useState, useEffect, useRef } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import type { ContentToSidebarMessage } from '../../shared/messages'
import { clsx } from 'clsx'

type InsertState = 'idle' | 'loading' | 'success' | 'error'

export function InsertButton(): React.ReactElement {
  const reply = useSidebarStore((s) => s.reply)
  const isGenerating = useSidebarStore((s) => s.isGenerating)
  const setIsInserted = useSidebarStore((s) => s.setIsInserted)
  const [insertState, setInsertState] = useState<InsertState>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const listener = (message: ContentToSidebarMessage) => {
      if (message.type === 'INSERT_SUCCESS') {
        setInsertState('success')
        setIsInserted(true)
        if (timerRef.current) clearTimeout(timerRef.current)
        timerRef.current = setTimeout(() => setInsertState('idle'), 2000)
      } else if (message.type === 'INSERT_FAILED') {
        setInsertState('error')
        setErrorMsg(message.payload.reason)
        if (timerRef.current) clearTimeout(timerRef.current)
        timerRef.current = setTimeout(() => setInsertState('idle'), 3000)
      }
    }

    chrome.runtime.onMessage.addListener(listener)
    return () => {
      chrome.runtime.onMessage.removeListener(listener)
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [setIsInserted])

  const handleInsert = () => {
    if (!reply || insertState === 'loading') return
    setInsertState('loading')
    setErrorMsg('')
    chrome.runtime.sendMessage({ type: 'INSERT_REPLY', payload: { text: reply } }).catch(() => {
      setInsertState('error')
      setErrorMsg('Could not reach content script. Refresh the WHD page.')
    })
  }

  const disabled = !reply || isGenerating || insertState === 'loading'

  const buttonClass = clsx(
    'secondary-btn',
    { success: insertState === 'success', error: insertState === 'error' }
  )

  const label =
    insertState === 'loading' ? 'Inserting…' :
    insertState === 'success' ? 'Inserted \u2713' :
    insertState === 'error' ? 'Insert failed' :
    'Insert reply'

  return (
    <div className="insert-button-wrapper">
      <button
        onClick={handleInsert}
        disabled={disabled}
        className={buttonClass}
        aria-label="Insert generated reply into WHD reply textarea"
        aria-busy={insertState === 'loading' ? 'true' : undefined}
      >
        {label}
      </button>
      <div aria-live="polite" className="sr-only">
        {insertState === 'success' && 'Reply inserted successfully.'}
        {insertState === 'error' && `Insert failed: ${errorMsg}`}
      </div>
      {insertState === 'error' && errorMsg && (
        <p className="support-text error-text" role="alert">{errorMsg}</p>
      )}
    </div>
  )
}
