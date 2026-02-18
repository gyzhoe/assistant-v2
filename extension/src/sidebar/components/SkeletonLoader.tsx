import React from 'react'

export function SkeletonLoader(): React.ReactElement {
  return (
    <div
      className="flex flex-col gap-2 p-4"
      role="status"
      aria-label="Generating reply, please wait"
      aria-live="polite"
    >
      <div className="skeleton h-3 rounded w-full" />
      <div className="skeleton h-3 rounded w-4/5" />
      <div className="skeleton h-3 rounded w-3/4" />
      <div className="skeleton h-3 rounded w-full mt-2" />
      <div className="skeleton h-3 rounded w-5/6" />
      <span className="sr-only">Generating reply…</span>
    </div>
  )
}
