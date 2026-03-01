import React, { useEffect, useRef, useState } from 'react'
import { storage, DEFAULT_SETTINGS } from '../lib/storage'
import { apiClient, sendNativeCommand } from '../lib/api-client'
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
  const [autoDetectMsg, setAutoDetectMsg] = useState('')
  const [isDetecting, setIsDetecting] = useState(false)
  const initialSettingsRef = useRef('')
  const initialTokenRef = useRef('')

  const isDirty =
    JSON.stringify(settings) !== initialSettingsRef.current ||
    apiToken !== initialTokenRef.current

  useEffect(() => {
    storage.getSettings().then((s) => {
      setSettings(s)
      initialSettingsRef.current = JSON.stringify(s)
    })
    apiClient.models().then(setModels).catch(() => {})
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

  return (
    <div className="options-page">
      {/* Page heading */}
      <div>
        <h1 className="options-heading">AI Helpdesk Assistant</h1>
        <p className="options-heading-subtitle">Extension settings</p>
      </div>

      {/* ── Section: Connection ── */}
      <div className="options-section">
        <div className="options-section-header">
          <span className="options-section-label">Connection</span>
        </div>

        {/* Backend URL */}
        <div className="options-field">
          <label htmlFor="backendUrl" className="options-label">
            Backend URL
          </label>
          <input
            id="backendUrl"
            type="url"
            value={settings.backendUrl}
            onChange={(e) => handleChange('backendUrl', e.target.value)}
            className="options-input"
            placeholder="http://localhost:8765"
          />
          <p className="options-hint">URL of the local FastAPI backend server.</p>
        </div>

        {/* API Token */}
        <div className="options-field">
          <label htmlFor="apiToken" className="options-label">
            API Token
          </label>
          <div className="options-input-row">
            <input
              id="apiToken"
              type="password"
              value={apiToken}
              onChange={(e) => setApiToken(e.target.value)}
              className="options-input font-mono"
              placeholder="Paste the API_TOKEN from the backend .env file"
              autoComplete="off"
              spellCheck={false}
            />
            <button
              type="button"
              onClick={handleAutoDetect}
              disabled={isDetecting}
              className="options-btn-secondary"
              aria-label="Auto-detect API token from backend"
            >
              {isDetecting ? 'Detecting\u2026' : 'Auto-detect'}
            </button>
          </div>
          {autoDetectMsg && (
            <p className="options-hint font-medium" role="status" aria-live="polite">{autoDetectMsg}</p>
          )}
          <p className="options-hint">
            Shared secret configured in the backend <code>API_TOKEN</code> environment variable.
            Stored only on this device — never synced to other browsers.
            Leave blank if token auth is disabled on the backend.
          </p>
        </div>
      </div>

      {/* ── Section: Model & Prompt ── */}
      <div className="options-section">
        <div className="options-section-header">
          <span className="options-section-label">Model &amp; Prompt</span>
        </div>

        {/* Default model */}
        <div className="options-field">
          <label htmlFor="defaultModel" className="options-label">
            Default Model
          </label>
          <select
            id="defaultModel"
            value={settings.defaultModel}
            onChange={(e) => handleChange('defaultModel', e.target.value)}
            className="options-input"
            aria-label="Select default LLM model"
          >
            {(models.length > 0 ? models : [settings.defaultModel]).map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <p className="options-hint">
            Ollama model used for reply generation. Fetch available models by visiting the backend health endpoint.
          </p>
        </div>

        {/* Prompt suffix */}
        <div className="options-field">
          <label htmlFor="promptSuffix" className="options-label">
            Prompt Suffix
          </label>
          <textarea
            id="promptSuffix"
            value={settings.promptSuffix}
            onChange={(e) => handleChange('promptSuffix', e.target.value)}
            rows={3}
            className="options-input resize-none font-mono"
            placeholder="e.g. Always sign replies with 'IT Support Team'"
          />
          <p className="options-hint">
            Custom instructions appended to every prompt.
          </p>
        </div>
      </div>

      {/* ── Section: Appearance ── */}
      <div className="options-section">
        <div className="options-section-header">
          <span className="options-section-label">Appearance</span>
        </div>

        {/* Theme */}
        <div className="options-field">
          <label htmlFor="theme" className="options-label">
            Theme
          </label>
          <select
            id="theme"
            value={settings.theme}
            onChange={(e) => handleChange('theme', e.target.value as AppSettings['theme'])}
            className="options-input"
            aria-label="Select theme"
          >
            <option value="system">System default</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </div>
      </div>

      {/* ── Section: Advanced ── */}
      <div className="options-section">
        <div className="options-section-header">
          <span className="options-section-label">Advanced</span>
        </div>

        {/* DOM Selector Overrides */}
        <div className="options-field">
          <button
            type="button"
            onClick={() => setSelectorsExpanded((v) => !v)}
            className="options-expand-btn"
            aria-expanded={selectorsExpanded ? 'true' : 'false'}
            aria-controls="selector-overrides"
          >
            <svg
              className="options-expand-chevron"
              data-open={selectorsExpanded ? 'true' : 'false'}
              viewBox="0 0 12 12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
            >
              <path d="M4 2l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            DOM Selector Overrides
          </button>
          <p className="options-hint">
            Override the CSS selectors used to read ticket fields from the WHD page.
            Leave blank to use the default selector.
          </p>

          {selectorsExpanded && (
            <div id="selector-overrides" className="options-divider">
              {SELECTOR_FIELDS.map(({ key, label }) => (
                <div key={key} className="options-selector-field">
                  <label htmlFor={`selector-${key}`} className="options-hint font-medium">
                    {label}
                  </label>
                  <input
                    id={`selector-${key}`}
                    type="text"
                    value={settings.selectorOverrides[key] ?? ''}
                    onChange={(e) => handleSelectorChange(key, e.target.value)}
                    className="options-input font-mono text-xs"
                    placeholder={DEFAULT_SELECTORS[key]}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Save ── */}
      <div className="options-save-row">
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="options-btn-primary"
          aria-label="Save settings"
        >
          {isSaving ? 'Saving\u2026' : 'Save Settings'}
        </button>
        {isDirty && (
          <span className="options-hint font-medium">(unsaved changes)</span>
        )}
        {saveMsg && (
          <p
            className={saveMsg.startsWith('Failed') ? 'options-save-msg options-save-msg--error' : 'options-save-msg options-save-msg--success'}
            role="status"
            aria-live="polite"
          >{saveMsg}</p>
        )}
      </div>

      {/* ── Quick Links ── */}
      <div className="options-section">
        <div className="options-section-header">
          <span className="options-section-label">Quick Links</span>
        </div>
        <div className="options-links-list">
          <a
            href={`${settings.backendUrl || 'http://localhost:8765'}/manage/`}
            target="_blank"
            rel="noopener noreferrer"
            className="options-link"
          >
            Knowledge Base Management &rarr;
          </a>
        </div>
      </div>
    </div>
  )
}
