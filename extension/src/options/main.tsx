import React from 'react'
import ReactDOM from 'react-dom/client'
import OptionsApp from './OptionsApp'
import './options.css'

const root = document.getElementById('root')
if (!root) throw new Error('Root element not found')

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <OptionsApp />
  </React.StrictMode>
)
