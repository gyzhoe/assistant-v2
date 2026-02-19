import React, { useEffect, useState } from 'react'
import { storage, DEFAULT_SETTINGS } from '../lib/storage'
import { apiClient } from '../lib/api-client'
import type { AppSettings, SelectorConfig } from '../shared/types'
import { STORAGE_KEY_SECRETS, DEFAULT_SELECTORS } from '../shared/constants'

const SELECTOR_FIELDS: { key: keyof SelectorConfig; label: string }[] = [
  { key: 'subject', label: 'Subject' },
  { key: 'description', label: 'Description' },
  { key: 'requesterName', label: 'Requester Name' },
  { key: 'category', label: 'Category' },
  { key: 'status', label: 'Status' },
  { key: 'techNotes', label: 'Tech Notes' },
]

export default function OptionsPage(): React.ReactElement {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS)
  const [apiToken, setApiToken] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [selectorsExpanded, setSelectorsExpanded] = useState(false)

  useEffect(() => {
    storage.getSettings().then(setSettings)
    apiClient.models().then(setModels).catch(() => {})
    // Load API token from local storage (device-only, never synced)
    chrome.storage.local.get(STORAGE_KEY_SECRETS, (result) => {
      const secrets = result[STORAGE_KEY_SECRETS] as { apiToken?: string } | undefined
      setApiToken(secrets?.apiToken ?? '')
    })
  }, [])

  const handleChange = (field: keyof AppSettings, value: string) => {
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
    try {
      await storage.saveSettings(settings)
      // Save API token to local storage (never synced)
      await new Promise<void>((resolve, reject) => {
        chrome.storage.local.set(
          { [STORAGE_KEY_SECRETS]: { apiToken } },
          () => {
            if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message))
            else resolve()
          }
        )
      })
      setSaveMsg('Settings saved.')
    } catch {
      setSaveMsg('Failed to save settings.')
    } finally {
      setIsSaving(false)
      setTimeout(() => setSaveMsg(''), 3000)
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h1 className="text-xl font-semibold mb-6 text-neutral-900">
        AI Helpdesk Assistant — Settings
      </h1>

      <div className="flex flex-col gap-6">
        {/* Backend URL */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="backendUrl" className="text-sm font-medium text-neutral-700">
            Backend URL
          </label>
          <input
            id="backendUrl"
            type="url"
            value={settings.backendUrl}
            onChange={(e) => handleChange('backendUrl', e.target.value)}
            className="border border-neutral-300 rounded px-3 py-1.5 text-sm text-neutral-800 bg-white focus:outline-none focus:ring-2 focus:ring-accent"
            placeholder="http://localhost:8765"
          />
          <p className="text-xs text-neutral-500">URL of the local FastAPI backend server.</p>
        </div>

        {/* Default model */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="defaultModel" className="text-sm font-medium text-neutral-700">
            Default Model
          </label>
          <select
            id="defaultModel"
            value={settings.defaultModel}
            onChange={(e) => handleChange('defaultModel', e.target.value)}
            className="border border-neutral-300 rounded px-3 py-1.5 text-sm text-neutral-800 bg-white focus:outline-none focus:ring-2 focus:ring-accent"
            aria-label="Select default LLM model"
          >
            {(models.length > 0 ? models : [settings.defaultModel]).map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <p className="text-xs text-neutral-500">
            Ollama model used for reply generation. Fetch available models by visiting the backend health endpoint.
          </p>
        </div>

        {/* Prompt suffix */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="promptSuffix" className="text-sm font-medium text-neutral-700">
            Prompt Suffix
          </label>
          <textarea
            id="promptSuffix"
            value={settings.promptSuffix}
            onChange={(e) => handleChange('promptSuffix', e.target.value)}
            rows={3}
            className="border border-neutral-300 rounded px-3 py-1.5 text-sm text-neutral-800 bg-white focus:outline-none focus:ring-2 focus:ring-accent resize-none font-mono"
            placeholder="e.g. Always sign replies with 'IT Support Team'"
          />
          <p className="text-xs text-neutral-500">
            Custom instructions appended to every prompt.
          </p>
        </div>

        {/* Theme */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="theme" className="text-sm font-medium text-neutral-700">
            Theme
          </label>
          <select
            id="theme"
            value={settings.theme}
            onChange={(e) => handleChange('theme', e.target.value as AppSettings['theme'])}
            className="border border-neutral-300 rounded px-3 py-1.5 text-sm text-neutral-800 bg-white focus:outline-none focus:ring-2 focus:ring-accent"
            aria-label="Select theme"
          >
            <option value="system">System default</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </div>

        {/* API Token — stored in chrome.storage.local, never synced */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="apiToken" className="text-sm font-medium text-neutral-700">
            API Token
          </label>
          <input
            id="apiToken"
            type="password"
            value={apiToken}
            onChange={(e) => setApiToken(e.target.value)}
            className="border border-neutral-300 rounded px-3 py-1.5 text-sm text-neutral-800 bg-white focus:outline-none focus:ring-2 focus:ring-accent font-mono"
            placeholder="Paste the API_TOKEN from the backend .env file"
            autoComplete="off"
            spellCheck={false}
          />
          <p className="text-xs text-neutral-500">
            Shared secret configured in the backend <code className="font-mono">API_TOKEN</code> environment variable.
            Stored only on this device — never synced to other browsers.
            Leave blank if token auth is disabled on the backend.
          </p>
        </div>

        {/* DOM Selector Overrides */}
        <div className="flex flex-col gap-1.5">
          <button
            type="button"
            onClick={() => setSelectorsExpanded((v) => !v)}
            className="flex items-center gap-1 text-sm font-medium text-neutral-700 hover:text-neutral-900"
            aria-expanded={selectorsExpanded ? 'true' : 'false'}
            aria-controls="selector-overrides"
          >
            <span className="text-xs">{selectorsExpanded ? '▾' : '▸'}</span>
            DOM Selector Overrides
          </button>
          <p className="text-xs text-neutral-500">
            Override the CSS selectors used to read ticket fields from the WHD page.
            Leave blank to use the default selector.
          </p>

          {selectorsExpanded && (
            <div id="selector-overrides" className="flex flex-col gap-3 mt-2 pl-2 border-l-2 border-neutral-200">
              {SELECTOR_FIELDS.map(({ key, label }) => (
                <div key={key} className="flex flex-col gap-1">
                  <label htmlFor={`selector-${key}`} className="text-xs font-medium text-neutral-600">
                    {label}
                  </label>
                  <input
                    id={`selector-${key}`}
                    type="text"
                    value={settings.selectorOverrides[key] ?? ''}
                    onChange={(e) => handleSelectorChange(key, e.target.value)}
                    className="border border-neutral-300 rounded px-3 py-1 text-xs text-neutral-800 bg-white focus:outline-none focus:ring-2 focus:ring-accent font-mono"
                    placeholder={DEFAULT_SELECTORS[key]}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Save */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="px-5 py-1.5 bg-accent text-white text-sm font-semibold rounded hover:bg-accent-hover disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-accent"
            aria-label="Save settings"
          >
            {isSaving ? 'Saving…' : 'Save Settings'}
          </button>
          {saveMsg && (
            <p className="text-sm text-neutral-600" role="status" aria-live="polite">{saveMsg}</p>
          )}
        </div>
      </div>
    </div>
  )
}
