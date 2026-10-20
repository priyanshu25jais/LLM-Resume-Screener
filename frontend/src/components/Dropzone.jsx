import { useRef, useState } from 'react'

const ACCEPT = '.pdf,.docx,.txt'

export default function Dropzone({ onFiles, busy }) {
  const input = useRef(null)
  const [over, setOver] = useState(false)

  const take = (list) => {
    const files = Array.from(list || [])
    if (files.length) onFiles(files)
  }

  return (
    <div
      className={`dropzone${over ? ' over' : ''}`}
      role="button" tabIndex={0} aria-label="Upload resumes"
      onClick={() => input.current?.click()}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files) }}
    >
      <span className="dz-icon" aria-hidden="true">
        {busy ? <span className="spinner" /> : (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 16V4" /><path d="m6 10 6-6 6 6" /><path d="M4 20h16" /></svg>
        )}
      </span>
      <div>
        <strong>{busy ? 'Uploading...' : 'Drop resumes or click to choose'}</strong>
        <span>PDF, DOCX or TXT, up to 10 MB each</span>
      </div>
      <input ref={input} type="file" accept={ACCEPT} multiple hidden onChange={(e) => { take(e.target.files); e.target.value = '' }} />
    </div>
  )
}
