import { useEffect, useState, useCallback } from 'react'
import { useSettings } from './useSettings'
import type { AppSettings } from '../../shared/types'

type ResolvedTheme = 'light' | 'dark'

interface UseThemeReturn {
  resolvedTheme: ResolvedTheme
  themeSetting: AppSettings['theme']
  cycleTheme: () => void
}

const MEDIA_QUERY = '(prefers-color-scheme: dark)'

function resolveTheme(setting: AppSettings['theme'], osDark: boolean): ResolvedTheme {
  if (setting === 'system') return osDark ? 'dark' : 'light'
  return setting
}

export function useTheme(): UseThemeReturn {
  const { settings, updateSettings } = useSettings()
  const [resolved, setResolved] = useState<ResolvedTheme>(() =>
    resolveTheme(settings.theme, window.matchMedia(MEDIA_QUERY).matches)
  )

  useEffect(() => {
    const mq = window.matchMedia(MEDIA_QUERY)
    const apply = () => setResolved(resolveTheme(settings.theme, mq.matches))

    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [settings.theme])

  const cycleTheme = useCallback(() => {
    const next: AppSettings['theme'] =
      settings.theme === 'system' ? 'light' :
      settings.theme === 'light' ? 'dark' : 'system'
    void updateSettings({ theme: next })
  }, [settings.theme, updateSettings])

  return { resolvedTheme: resolved, themeSetting: settings.theme, cycleTheme }
}
