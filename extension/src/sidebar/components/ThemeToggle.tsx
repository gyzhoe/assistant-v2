import React from 'react'
import type { AppSettings } from '../../shared/types'

interface ThemeToggleProps {
  theme: AppSettings['theme']
  resolvedTheme: 'light' | 'dark'
  onCycle: () => void
}

/* SVG icons — 16×16, stroke-based, aria-hidden */
const SunIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" aria-hidden="true">
    <circle cx="8" cy="8" r="3" />
    <path d="M8 1.5v1M8 13.5v1M1.5 8h1M13.5 8h1M3.4 3.4l.7.7M11.9 11.9l.7.7M3.4 12.6l.7-.7M11.9 4.1l.7-.7" />
  </svg>
)

const MoonIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" aria-hidden="true">
    <path d="M13.2 9.8A5.5 5.5 0 1 1 6.2 2.8a4.4 4.4 0 0 0 7 7Z" />
  </svg>
)

const MonitorIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" aria-hidden="true">
    <rect x="2" y="2.5" width="12" height="8" rx="1.2" />
    <path d="M5.5 13.5h5M8 10.5v3" />
  </svg>
)

const ICON_MAP = { light: SunIcon, dark: MoonIcon, system: MonitorIcon } as const

export function ThemeToggle({ theme, resolvedTheme, onCycle }: ThemeToggleProps): React.ReactElement {
  const Icon = ICON_MAP[theme]

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={onCycle}
      aria-label={`Switch theme, current: ${theme}`}
      title={`Theme: ${theme} (${resolvedTheme})`}
    >
      <Icon />
    </button>
  )
}
