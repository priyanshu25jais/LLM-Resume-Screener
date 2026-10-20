import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import WeightsEditor from '../components/WeightsEditor.jsx'

const DEFAULT = { llm: 0.45, skills: 0.25, semantic: 0.2, experience: 0.1 }

export default function NewJob() {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [blind, setBlind] = useState(true)
  const [weights, setWeights] = useState(DEFAULT)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const nav = useNavigate()

  const loadFile = async (file) => {
    if (!file) return
    if (!file.name.match(/\.(txt|md)$/i)) { setErr('Paste the text of PDF or Word job descriptions; only .txt files can be loaded here.'); return }
    setDescription(await file.text())
    if (!title) setTitle(file.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' '))
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      const job = await api.createJob({ title, description, blind_mode: blind, weights })
      nav(`/jobs/${job.id}`)
    } catch (ex) { setErr(ex.message); setBusy(false) }
  }

  return (
    <form onSubmit={submit}>
      <nav className="crumbs" aria-label="Breadcrumb"><Link to="/">Jobs</Link><span aria-hidden="true">/</span><span>New job</span></nav>
      <div className="page-head">
        <div>
          <h1>New job</h1>
          <p>Paste the job description. The LLM turns it into must-have and nice-to-have requirements, which you can correct before screening.</p>
        </div>
      </div>
      <div className="split">
        <div className="card pad stack">
          <label className="field">Job title
            <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Python Backend Developer" required minLength={2} />
          </label>
          <label className="field">Job description
            <span className="hint">Responsibilities, required skills, preferred skills and experience. At least a few lines.</span>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} required minLength={30}
              placeholder={'Requirements\n- 2+ years of experience with Python\n- FastAPI or Django\n\nNice to have\n- Docker, AWS'} />
          </label>
          <label className="small muted">Or load the description from a .txt file: <input type="file" accept=".txt,.md" onChange={(e) => loadFile(e.target.files[0])} /></label>
        </div>
        <div className="stack">
          <div className="card pad stack">
            <label className="switch">
              <input type="checkbox" checked={blind} onChange={(e) => setBlind(e.target.checked)} />
              <div><strong>Blind screening</strong><span>Names, contact details, gender and age are removed before the LLM reads a resume, and hidden from you until you reveal them.</span></div>
            </label>
          </div>
          <div className="card pad stack">
            <div>
              <h2>Scoring weights</h2>
              <p className="muted small">How much each signal counts in the final score. You can change these later without re-screening.</p>
            </div>
            <WeightsEditor value={weights} onChange={setWeights} />
            <button type="button" className="btn ghost sm" onClick={() => setWeights(DEFAULT)}>Reset to default</button>
          </div>
          {err && <p className="error">{err}</p>}
          <button className="btn accent" style={{ width: '100%', justifyContent: 'center', padding: '12px' }} disabled={busy}>
            {busy ? <><span className="spinner" />Reading the job description...</> : 'Create job'}
          </button>
        </div>
      </div>
    </form>
  )
}
