import { useEffect, useState } from 'react'
import { storage, DEFAULT_SETTINGS } from '../../lib/storage'
import type { AppSettings } from '../../shared/types'

export function useSettings() {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    storage.getSettings().then((s) => {
      setSettings(s)
      setIsLoading(false)
    })
  }, [])

  const updateSettings = async (updates: Partial<AppSettings>) => {
    await storage.saveSettings(updates)
    setSettings((prev) => ({ ...prev, ...updates }))
  }

  return { settings, isLoading, updateSettings }
}
