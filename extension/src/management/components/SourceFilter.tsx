import type { SourceType } from '../types'

interface SourceFilterProps {
  value: SourceType | ''
  onChange: (value: SourceType | '') => void
}

const SOURCE_OPTIONS: { value: SourceType | '', label: string }[] = [
  { value: '', label: 'All Sources' },
  { value: 'pdf', label: 'PDF' },
  { value: 'html', label: 'HTML' },
  { value: 'url', label: 'URL' },
  { value: 'json', label: 'JSON' },
  { value: 'csv', label: 'CSV' },
]

export function SourceFilter({ value, onChange }: SourceFilterProps): React.ReactElement {
  return (
    <select
      className="source-filter"
      value={value}
      onChange={e => onChange(e.target.value as SourceType | '')}
      aria-label="Filter by source type"
    >
      {SOURCE_OPTIONS.map(opt => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  )
}
