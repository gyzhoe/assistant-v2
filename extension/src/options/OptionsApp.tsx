import React from 'react'
import { useTheme } from '../sidebar/hooks/useTheme'
import OptionsPage from './OptionsPage'

export default function OptionsApp(): React.ReactElement {
  const { resolvedTheme } = useTheme()

  return (
    <div className="options-shell" data-theme={resolvedTheme}>
      <OptionsPage />
    </div>
  )
}
