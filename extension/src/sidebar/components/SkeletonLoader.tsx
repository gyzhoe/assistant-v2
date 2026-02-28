import React from 'react'

export function SkeletonLoader(): React.ReactElement {
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
      <span className="sr-only">Generating reply…</span>
    </div>
  )
}
