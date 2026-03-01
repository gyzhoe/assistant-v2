import React, { useState, useEffect } from 'react'

export function SkeletonLoader(): React.ReactElement {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div
      className="skeleton-loader"
      role="status"
      aria-label="Generating reply, please wait"
      aria-live="polite"
    >
      <div className="skeleton skeleton-line" />
      <div className="skeleton skeleton-line skeleton-line-80" />
      <div className="skeleton skeleton-line skeleton-line-75" />
      <div className="skeleton skeleton-line skeleton-line-gap" />
      <div className="skeleton skeleton-line skeleton-line-85" />
      <span className="skeleton-elapsed" aria-live="off">Generating… {elapsed}s</span>
      <span className="sr-only">Generating reply…</span>
    </div>
  )
}
