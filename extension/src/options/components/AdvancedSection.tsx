import React from 'react'
import type { SelectorConfig } from '../../shared/types'
import { DEFAULT_SELECTORS } from '../../shared/constants'

/** Selector field metadata for rendering the DOM override inputs. */
const SELECTOR_FIELDS: { key: keyof SelectorConfig; label: string }[] = [
  { key: 'subject', label: 'Subject' },
  { key: 'description', label: 'Description' },
  { key: 'requesterName', label: 'Requester Name' },
  { key: 'category', label: 'Category' },
  { key: 'status', label: 'Status' },
  { key: 'techNotes', label: 'Tech Notes' },
]

export interface AdvancedSectionProps {
  selectorOverrides: Partial<SelectorConfig>
  insertTargetSelector: string
  selectorsExpanded: boolean
  onSelectorChange: (field: keyof SelectorConfig, value: string) => void
  onInsertTargetChange: (value: string) => void
  onToggleSelectors: () => void
}

export function AdvancedSection({
  selectorOverrides,
  insertTargetSelector,
  selectorsExpanded,
  onSelectorChange,
  onInsertTargetChange,
  onToggleSelectors,
}: AdvancedSectionProps): React.ReactElement {
  return (
    <div className="options-section">
      <div className="options-section-header">
        <span className="options-section-label">Advanced</span>
      </div>

      {/* DOM Selector Overrides */}
      <div className="options-field">
        <button
          type="button"
          onClick={onToggleSelectors}
          className="options-expand-btn"
          aria-expanded={selectorsExpanded}
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
                  value={selectorOverrides[key] ?? ''}
                  onChange={(e) => onSelectorChange(key, e.target.value)}
                  className="options-input font-mono text-xs"
                  placeholder={DEFAULT_SELECTORS[key]}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Insert Target Selector */}
      <div className="options-field">
        <label htmlFor="insertTargetSelector" className="options-label">
          Insert Target Selector
        </label>
        <input
          id="insertTargetSelector"
          type="text"
          value={insertTargetSelector}
          onChange={(e) => onInsertTargetChange(e.target.value)}
          className="options-input font-mono text-xs"
          placeholder="textarea#techNotes"
        />
        <p className="options-hint">
          CSS selector for the textarea where generated replies are inserted.
          Leave blank to use the default WHD tech notes field.
        </p>
      </div>
    </div>
  )
}
