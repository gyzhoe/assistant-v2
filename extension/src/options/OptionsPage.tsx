import React, { useEffect, useRef, useState } from 'react'
import { storage, DEFAULT_SETTINGS } from '../lib/storage'
import { apiClient, sendNativeCommand } from '../lib/api-client'
import type { AppSettings, ModelDownloadStatus, ModelInfo, SelectorConfig } from '../shared/types'
import { STORAGE_KEY_SECRETS } from '../shared/constants'
import {
  ConnectionSection,
  ModelPromptSection,
  LLMModelsSection,
  AdvancedSection,
  QuickLinksSection,
  SaveFooter,
} from './components'

/** Fallback model list shown when the backend is unreachable (e.g. fresh install). */
const FALLBACK_MODEL_INFO: Record<string, ModelInfo> = {
  'qwen3.5:9b': {
    downloaded: false,
    size_bytes: null,
    description: '~5.3 GB',
    gguf_name: 'Qwen3.5-9B-Q4_K_M.gguf',
  },
  'qwen3:14b': {
    downloaded: false,
    size_bytes: null,
    description: '~9 GB (optional, better language control)',
    gguf_name: 'Qwen3-14B-Q4_K_M.gguf',
  },
}

export default function OptionsPage(): React.ReactElement {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS)
  const [apiToken, setApiToken] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [backendReachable, setBackendReachable] = useState(true)
  const [selectorsExpanded, setSelectorsExpanded] = useState(false)
  const [autoDetectMsg, setAutoDetectMsg] = useState('')
  const [isDetecting, setIsDetecting] = useState(false)
  const [onboardingResetMsg, setOnboardingResetMsg] = useState('')
  const [modelInfo, setModelInfo] = useState<Record<string, ModelInfo>>({})
  const [downloadStatus, setDownloadStatus] = useState<ModelDownloadStatus | null>(null)
  const [downloadError, setDownloadError] = useState('')
  const initialSettingsRef = useRef('')
  const initialTokenRef = useRef('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const isDirty =
    JSON.stringify(settings) !== initialSettingsRef.current ||
    apiToken !== initialTokenRef.current

  // ── Lifecycle ──

  useEffect(() => {
    storage.getSettings().then((s) => {
      setSettings(s)
      initialSettingsRef.current = JSON.stringify(s)
    })
    apiClient.models().then((data) => {
      setModels(data.models)
      if (data.model_info) setModelInfo(data.model_info)
    }).catch(() => {
      setBackendReachable(false)
      setModelInfo(FALLBACK_MODEL_INFO)
    })
    chrome.storage.local.get(STORAGE_KEY_SECRETS, (result) => {
      const secrets = result[STORAGE_KEY_SECRETS] as { apiToken?: string } | undefined
      const token = secrets?.apiToken ?? ''
      setApiToken(token)
      initialTokenRef.current = token
    })
  }, [])

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault()
      }
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isDirty])

  useEffect(() => {
    return () => stopPolling()
  }, [])

  // ── Handlers ──

  type StringAppField = { [K in keyof AppSettings]: AppSettings[K] extends string ? K : never }[keyof AppSettings]

  const handleChange = <K extends StringAppField>(field: K, value: AppSettings[K]) => {
    setSettings((prev) => ({ ...prev, [field]: value }))
  }

  const handleSelectorChange = (field: keyof SelectorConfig, value: string) => {
    setSettings((prev) => {
      const overrides = { ...prev.selectorOverrides }
      if (value.trim()) {
        overrides[field] = value.trim()
      } else {
        delete overrides[field]
      }
      return { ...prev, selectorOverrides: overrides }
    })
  }

  const handleSave = async () => {
    setIsSaving(true)
    setSaveMsg('')

    if (settings.backendUrl) {
      try {
        const parsed = new URL(settings.backendUrl)
        if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
          setSaveMsg('Backend URL must start with http:// or https://')
          setIsSaving(false)
          return
        }
      } catch {
        setSaveMsg('Backend URL is not a valid URL.')
        setIsSaving(false)
        return
      }
    }

    try {
      await storage.saveSettings(settings)
      await new Promise<void>((resolve, reject) => {
        chrome.storage.local.set(
          { [STORAGE_KEY_SECRETS]: { apiToken } },
          () => {
            if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message))
            else resolve()
          }
        )
      })
      initialSettingsRef.current = JSON.stringify(settings)
      initialTokenRef.current = apiToken
      setSaveMsg('Settings saved.')
    } catch {
      setSaveMsg('Failed to save settings.')
    } finally {
      setIsSaving(false)
      setTimeout(() => setSaveMsg(''), 3000)
    }
  }

  const handleAutoDetect = async () => {
    setIsDetecting(true)
    setAutoDetectMsg('')
    try {
      const response = await sendNativeCommand('get_token')
      if (response.ok && response.token) {
        setApiToken(response.token)
        setAutoDetectMsg('Token detected! Click Save to apply.')
      } else {
        setAutoDetectMsg('Could not detect token. Enter manually.')
      }
    } catch {
      setAutoDetectMsg('Could not detect token. Enter manually.')
    } finally {
      setIsDetecting(false)
      setTimeout(() => setAutoDetectMsg(''), 5000)
    }
  }

  const refreshModels = () => {
    apiClient.models().then((data) => {
      setModels(data.models)
      if (data.model_info) setModelInfo(data.model_info)
      setBackendReachable(true)
    }).catch(() => {})
  }

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const startPolling = () => {
    stopPolling()
    pollRef.current = setInterval(() => {
      apiClient.downloadStatus().then((status) => {
        setDownloadStatus(status)
        if (!status.downloading) {
          stopPolling()
          setDownloadError(status.error || '')
          refreshModels()
        }
      }).catch(() => {
        stopPolling()
        setDownloadStatus(null)
        setDownloadError('Lost connection to backend.')
      })
    }, 2000)
  }

  const handleDownload = (ggufNames?: string[]) => {
    setDownloadError('')
    apiClient.downloadModels(ggufNames).then((resp) => {
      if (resp.status === 'started' || resp.status === 'already_downloading') {
        setDownloadStatus({
          downloading: true,
          current_model: null,
          bytes_downloaded: 0,
          bytes_total: 0,
          models_completed: 0,
          models_total: resp.models.length,
          error: '',
        })
        startPolling()
      } else if (resp.status === 'all_downloaded') {
        refreshModels()
      } else if (resp.status === 'error') {
        setDownloadError(String((resp as Record<string, unknown>).error ?? 'Unknown model'))
      }
    }).catch(() => {
      setDownloadError('Failed to start download. Is the backend running?')
    })
  }

  const handleCancelDownload = () => {
    apiClient.cancelDownload().then(() => {
      stopPolling()
      setDownloadStatus(null)
      refreshModels()
    }).catch(() => {})
  }

  const handleClearErrorAndRetry = () => {
    setDownloadError('')
    handleDownload()
  }

  const handleOnboardingReset = () => {
    chrome.storage.local.remove('onboardingDismissed', () => {
      setOnboardingResetMsg('Getting Started guide will appear in the sidebar.')
      setTimeout(() => setOnboardingResetMsg(''), 4000)
    })
  }

  // ── Render ──

  return (
    <div className="options-page">
      {/* Page heading */}
      <div>
        <h1 className="options-heading">AI Helpdesk Assistant</h1>
        <p className="options-heading-subtitle">Extension settings</p>
      </div>

      <ConnectionSection
        backendUrl={settings.backendUrl}
        apiToken={apiToken}
        autoDetectMsg={autoDetectMsg}
        isDetecting={isDetecting}
        onBackendUrlChange={(v) => handleChange('backendUrl', v)}
        onApiTokenChange={setApiToken}
        onAutoDetect={handleAutoDetect}
      />

      <ModelPromptSection
        defaultModel={settings.defaultModel}
        promptSuffix={settings.promptSuffix}
        theme={settings.theme}
        models={models}
        onDefaultModelChange={(v) => handleChange('defaultModel', v)}
        onPromptSuffixChange={(v) => handleChange('promptSuffix', v)}
        onThemeChange={(v) => handleChange('theme', v)}
      />

      <LLMModelsSection
        modelInfo={modelInfo}
        backendReachable={backendReachable}
        downloadStatus={downloadStatus}
        downloadError={downloadError}
        onDownload={handleDownload}
        onCancelDownload={handleCancelDownload}
        onClearErrorAndRetry={handleClearErrorAndRetry}
      />

      <AdvancedSection
        selectorOverrides={settings.selectorOverrides}
        insertTargetSelector={settings.insertTargetSelector}
        selectorsExpanded={selectorsExpanded}
        onSelectorChange={handleSelectorChange}
        onInsertTargetChange={(v) => handleChange('insertTargetSelector', v)}
        onToggleSelectors={() => setSelectorsExpanded((v) => !v)}
      />

      <SaveFooter
        isDirty={isDirty}
        isSaving={isSaving}
        saveMsg={saveMsg}
        onSave={handleSave}
      />

      <QuickLinksSection
        backendUrl={settings.backendUrl}
        onboardingResetMsg={onboardingResetMsg}
        onResetOnboarding={handleOnboardingReset}
      />
    </div>
  )
}
