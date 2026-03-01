import { useSidebarStore } from '../store/sidebarStore'
import type { AppSettings } from '../../shared/types'

export function useSettings() {
  const settings = useSidebarStore((s) => s.settings)
  const isLoading = useSidebarStore((s) => s.settingsLoading)
  const updateSettings = useSidebarStore((s) => s.updateSettings)

  return { settings, isLoading, updateSettings }
}

export type { AppSettings }
