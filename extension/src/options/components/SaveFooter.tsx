import React from 'react'

export interface SaveFooterProps {
  isDirty: boolean
  isSaving: boolean
  saveMsg: string
  onSave: () => void
}

export function SaveFooter({
  isDirty,
  isSaving,
  saveMsg,
  onSave,
}: SaveFooterProps): React.ReactElement {
  return (
    <div className="options-save-row">
      <button
        onClick={onSave}
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
  )
}
