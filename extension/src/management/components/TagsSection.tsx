import { DEFAULT_TAG_SUGGESTIONS } from '../constants/tagSuggestions'

interface TagsSectionProps {
  tags: string[]
  setTags: React.Dispatch<React.SetStateAction<string[]>>
  tagInput: string
  setTagInput: (value: string) => void
  tagSuggestions: string[]
  existingTags: { tags: string[] } | undefined
  showTagSuggestions: boolean
  setShowTagSuggestions: React.Dispatch<React.SetStateAction<boolean>>
  tagTruncateWarning: boolean
  setTagTruncateWarning: (value: boolean) => void
}

export function TagsSection({
  tags,
  setTags,
  tagInput,
  setTagInput,
  tagSuggestions,
  existingTags,
  showTagSuggestions,
  setShowTagSuggestions,
  tagTruncateWarning,
  setTagTruncateWarning,
}: TagsSectionProps): React.ReactElement {
  return (
    <>
      <div className="tag-picker">
        <div className="tag-pills">
          {tags.map(tag => (
            <span key={tag} className="tag-pill">
              {tag}
              <button
                type="button"
                className="tag-pill-remove"
                onClick={() => setTags(prev => prev.filter(t => t !== tag))}
                aria-label={`Remove tag ${tag}`}
              >
                &times;
              </button>
            </span>
          ))}
        </div>
        <div className="tag-input-wrapper">
          <input
            id="article-tags"
            type="text"
            className="tag-input"
            list="tag-suggestions-editor"
            placeholder={tags.length >= 20 ? 'Max tags reached' : 'Add tags (e.g., NETWORK CONNECTION, MAILBOX)'}
            value={tagInput}
            onChange={e => setTagInput(e.target.value)}
            onKeyDown={e => {
              if ((e.key === 'Enter' || e.key === ',') && tagInput.trim()) {
                e.preventDefault()
                const newTag = tagInput.trim().replace(/,$/g, '')
                if (newTag && !tags.includes(newTag) && tags.length < 20) {
                  setTags(prev => [...prev, newTag])
                }
                setTagInput('')
              }
            }}
            onPaste={e => {
              const pasted = e.clipboardData.getData('text')
              if (pasted.includes(',')) {
                e.preventDefault()
                const newTags = pasted.split(',').map(t => t.trim()).filter(Boolean)
                setTags(prev => {
                  const combined = [...prev, ...newTags.filter(t => !prev.includes(t))]
                  if (combined.length > 20) {
                    setTagTruncateWarning(true)
                    setTimeout(() => setTagTruncateWarning(false), 3000)
                  }
                  return combined.slice(0, 20)
                })
                setTagInput('')
              }
            }}
            disabled={tags.length >= 20}
            maxLength={100}
          />
          <datalist id="tag-suggestions-editor">
            {tagSuggestions.map(t => (
              <option key={t} value={t} />
            ))}
          </datalist>
        </div>
      </div>
      {tagTruncateWarning && (
        <p className="editor-hint" style={{ color: 'var(--warn-text, #9a6700)' }}>Some pasted tags were truncated to the 20-tag limit.</p>
      )}
      <div className="tag-browse-row">
        <button
          type="button"
          className="tag-browse-toggle"
          onClick={() => setShowTagSuggestions(v => !v)}
          aria-expanded={showTagSuggestions}
          aria-label="Browse tag suggestions"
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 10 10"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            className={`tag-browse-chevron${showTagSuggestions ? ' open' : ''}`}
          >
            <path d="M3 2l4 3-4 3" />
          </svg>
          Browse request types
        </button>
        <span className="editor-hint">or type custom tags above</span>
      </div>
      {showTagSuggestions && (() => {
        const apiTags = existingTags?.tags ?? []
        const allSuggestions = [...new Set([...DEFAULT_TAG_SUGGESTIONS, ...apiTags])]
        return (
          <div className="tag-suggestions-list">
            {allSuggestions.map(t => {
              const selected = tags.includes(t)
              return (
                <button
                  key={t}
                  type="button"
                  className={`tag-suggestion-chip ${selected ? 'tag-suggestion-selected' : ''}`}
                  onClick={() => {
                    if (selected) {
                      setTags(prev => prev.filter(x => x !== t))
                    } else if (tags.length < 20) {
                      setTags(prev => [...prev, t])
                    }
                  }}
                  disabled={!selected && tags.length >= 20}
                  aria-pressed={selected}
                >
                  {selected ? '\u2713 ' : '+ '}{t}
                </button>
              )
            })}
          </div>
        )
      })()}
    </>
  )
}
