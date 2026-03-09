import React from 'react'

export interface QuickLinksSectionProps {
  backendUrl: string
  onboardingResetMsg: string
  onResetOnboarding: () => void
}

export function QuickLinksSection({
  backendUrl,
  onboardingResetMsg,
  onResetOnboarding,
}: QuickLinksSectionProps): React.ReactElement {
  return (
    <div className="options-section">
      <div className="options-section-header">
        <span className="options-section-label">Quick Links</span>
      </div>
      <div className="options-links-list">
        <a
          href={`${backendUrl || 'http://localhost:8765'}/manage/`}
          target="_blank"
          rel="noopener noreferrer"
          className="options-link"
        >
          Knowledge Base Management &rarr;
        </a>
      </div>
      <div className="options-field">
        <button
          type="button"
          onClick={onResetOnboarding}
          className="options-btn-secondary"
          aria-label="Show Getting Started guide in the sidebar"
        >
          Show Getting Started guide
        </button>
        {onboardingResetMsg && (
          <p className="options-hint font-medium" role="status" aria-live="polite">
            {onboardingResetMsg}
          </p>
        )}
      </div>
    </div>
  )
}
