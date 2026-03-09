import React from 'react'

interface OnboardingCardProps {
  backendOk: boolean
  llmOk: boolean
  modelOk: boolean
  onDismiss: () => void
}

export function OnboardingCard({
  backendOk,
  llmOk,
  modelOk,
  onDismiss,
}: OnboardingCardProps): React.ReactElement {
  const steps = [
    {
      label: 'Start LLM server',
      done: llmOk,
      hint: (
        <>
          Start the LLM server via the installer or manually.
        </>
      ),
    },
    {
      label: 'Download models',
      done: modelOk,
      hint: (
        <>
          Download models via Start Menu &rarr; Setup LLM Models.
        </>
      ),
    },
    {
      label: 'Start the backend',
      done: backendOk,
      hint: <>Start the AI Helpdesk backend server (port 8765).</>,
    },
  ]

  return (
    <div className="onboarding-card" role="region" aria-label="Getting started">
      <h3 className="onboarding-title">Getting Started</h3>
      <p className="onboarding-subtitle">
        Complete these steps to start using the AI assistant.
      </p>
      <div className="onboarding-steps">
        {steps.map((step) => (
          <div key={step.label} className="onboarding-step">
            <span className={`onboarding-step-indicator ${step.done ? 'done' : 'pending'}`}>
              {step.done ? '\u2713' : '\u00B7'}
            </span>
            <div className="onboarding-step-body">
              <span className="onboarding-step-label">{step.label}</span>
              {!step.done && <span className="onboarding-step-hint">{step.hint}</span>}
            </div>
          </div>
        ))}
      </div>
      <button className="onboarding-dismiss" onClick={onDismiss} type="button">
        Dismiss
      </button>
    </div>
  )
}
