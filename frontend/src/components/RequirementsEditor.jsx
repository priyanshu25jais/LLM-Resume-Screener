import { useState } from 'react'
import { byWhom } from '../api.js'

function ChipList({ items, kind, onChange, editing, limit = 99 }) {
  const [draft, setDraft] = useState('')
  const [all, setAll] = useState(false)
  const add = () => {
    const v = draft.trim()
    if (v && !items.includes(v)) onChange([...items, v])
    setDraft('')
  }
  const shown = editing || all ? items : items.slice(0, limit)
  return (
    <>
      <div className="chips">
        {items.length === 0 && <span className="muted small">None listed</span>}
        {shown.map((s) => (
          <span key={s} className={`chip ${kind}`}>
            {s}
            {editing && <button type="button" aria-label={`Remove ${s}`} onClick={() => onChange(items.filter((x) => x !== s))}>×</button>}
          </span>
        ))}
        {!editing && items.length > limit && (
          <button type="button" className="chip more" onClick={() => setAll(!all)}>{all ? 'Show less' : `+${items.length - limit} more`}</button>
        )}
      </div>
      {editing && (
        <div className="chip-input">
          <input type="text" value={draft} placeholder="Add a skill" onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }} />
          <button type="button" className="btn secondary sm" onClick={add}>Add</button>
        </div>
      )}
    </>
  )
}

export default function RequirementsEditor({ requirements, onSave, analysedBy }) {
  const [editing, setEditing] = useState(false)
  const [req, setReq] = useState(requirements)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    try { await onSave(req); setEditing(false) } finally { setSaving(false) }
  }

  return (
    <section className="card pad" aria-labelledby="req-h">
      <div className="card-head" style={{ alignItems: 'flex-start' }}>
        <div>
          <h2 id="req-h">Job requirements</h2>
          <p>Read by {byWhom(analysedBy).replace('evaluator', 'analyser')}</p>
        </div>
        {!editing && <button className="link-btn" onClick={() => { setReq(requirements); setEditing(true) }}>Edit</button>}
      </div>
      <div className="req-block">
        <h3>Must have</h3>
        <ChipList items={req.must_have_skills || []} kind="must" editing={editing} limit={10}
          onChange={(v) => setReq({ ...req, must_have_skills: v })} />
      </div>
      <div className="req-block">
        <h3>Nice to have</h3>
        <ChipList items={req.nice_to_have_skills || []} kind="" editing={editing} limit={6}
          onChange={(v) => setReq({ ...req, nice_to_have_skills: v })} />
      </div>
      <div className="req-block">
        {editing ? (
          <div className="stack">
            <label className="field">Minimum years of experience
              <input type="text" inputMode="decimal" value={req.min_years_experience}
                onChange={(e) => setReq({ ...req, min_years_experience: e.target.value })} />
            </label>
            <label className="field">Education
              <input type="text" value={req.education} onChange={(e) => setReq({ ...req, education: e.target.value })} />
            </label>
          </div>
        ) : (
          <dl className="kv">
            <dt>Experience</dt><dd>{req.min_years_experience ? `${req.min_years_experience}+ years` : 'Not specified'}</dd>
            <dt>Education</dt><dd>{req.education || 'Not specified'}</dd>
            <dt>Level</dt><dd>{req.seniority || 'Not specified'}</dd>
          </dl>
        )}
      </div>
      {editing && (
        <div className="btn-row" style={{ marginTop: 16 }}>
          <button className="btn" onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save and re-screen'}</button>
          <button className="btn ghost" onClick={() => { setReq(requirements); setEditing(false) }}>Cancel</button>
        </div>
      )}
    </section>
  )
}
