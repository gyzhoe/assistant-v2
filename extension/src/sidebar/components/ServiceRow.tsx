import React from 'react'

interface ServiceRowProps {
  label: string
  statusColor: 'ok' | 'error'
  info?: string
  children?: React.ReactNode
}

export function ServiceRow({
  label,
  statusColor,
  info,
  children,
}: ServiceRowProps): React.ReactElement {
  return (
    <div className="service-row">
      <span className={`service-indicator ${statusColor}`} />
      <span className="service-label">
        {label}{info ? <> <span className="backend-info">{info}</span></> : null}
      </span>
      {children}
    </div>
  )
}
