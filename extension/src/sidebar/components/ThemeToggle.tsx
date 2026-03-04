import React from 'react'
import type { AppSettings } from '../../shared/types'
import { SunIcon, MoonIcon, MonitorIcon } from '../../shared/components/Icons'

interface ThemeToggleProps {
  theme: AppSettings['theme']
  resolvedTheme: 'light' | 'dark'
  onCycle: () => void
}

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
