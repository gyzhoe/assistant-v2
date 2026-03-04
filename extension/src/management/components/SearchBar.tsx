import { useState, useEffect, useRef } from 'react'
import { SearchIcon } from '../../shared/components/Icons'

interface SearchBarProps {
  value: string
  onChange: (value: string) => void
}

export function SearchBar({ value, onChange }: SearchBarProps): React.ReactElement {
  const [local, setLocal] = useState(value)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    setLocal(value)
  }, [value])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value
    setLocal(v)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => onChange(v), 300)
  }

  const handleClear = () => {
    setLocal('')
    onChange('')
  }

  useEffect(() => {
    return () => clearTimeout(timerRef.current)
  }, [])

  return (
    <div className="search-bar">
      <span className="search-icon"><SearchIcon /></span>
      <input
        type="text"
        className="search-input"
        placeholder="Search articles..."
        value={local}
        onChange={handleChange}
        aria-label="Search articles"
      />
      {local && (
        <button
          type="button"
          className="search-clear"
          onClick={handleClear}
          aria-label="Clear search"
        >
          &times;
        </button>
      )}
    </div>
  )
}
