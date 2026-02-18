import React, { useState, useEffect } from 'react'
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

  useEffect(() => {
    const listener = (message: ContentToSidebarMessage) => {
      if (message.type === 'INSERT_SUCCESS') {
        setInsertState('success')
        setIsInserted(true)
        setTimeout(() => setInsertState('idle'), 2000)
      } else if (message.type === 'INSERT_FAILED') {
        setInsertState('error')
        setErrorMsg(message.payload.reason)
        setTimeout(() => setInsertState('idle'), 3000)
      }
    }

    chrome.runtime.onMessage.addListener(listener)
    return () => chrome.runtime.onMessage.removeListener(listener)
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
    'w-full py-1.5 px-3 rounded text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
    {
      'bg-accent text-white hover:bg-accent-hover': insertState === 'idle',
      'bg-neutral-300 text-neutral-500 cursor-not-allowed': disabled && insertState !== 'success',
      'bg-green-600 text-white': insertState === 'success',
      'bg-red-600 text-white': insertState === 'error',
    }
  )

  const label =
    insertState === 'loading' ? 'Inserting…' :
    insertState === 'success' ? 'Inserted ✓' :
    insertState === 'error' ? 'Insert failed' :
    'Insert into reply'

  return (
    <div className="flex flex-col gap-1">
      <button
        onClick={handleInsert}
        disabled={disabled}
        className={buttonClass}
        aria-label="Insert generated reply into WHD reply textarea"
        aria-busy={insertState === 'loading'}
      >
        {label}
      </button>
      {insertState === 'error' && errorMsg && (
        <p className="text-xs text-red-600" role="alert">{errorMsg}</p>
      )}
    </div>
  )
}
