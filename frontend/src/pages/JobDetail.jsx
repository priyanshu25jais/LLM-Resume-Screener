import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, BANDS, DECISIONS, formatTokens, skillName } from '../api.js'
import AskPanel from '../components/AskPanel.jsx'
import Band, { Avatar, MiniDist } from '../components/Band.jsx'
import Dropzone from '../components/Dropzone.jsx'
import RequirementsEditor from '../components/RequirementsEditor.jsx'
import ScoreBar, { Legend } from '../components/ScoreBar.jsx'
import { useToast } from '../components/Toast.jsx'
import WeightsEditor from '../components/WeightsEditor.jsx'

const FILTERS = [
  { key: 'All', label: 'All candidates' },
  { key: 'Strong Fit', label: 'Strong fit', swatch: 'b-strong' },
  { key: 'Good Fit', label: 'Good fit', swatch: 'b-good' },
  { key: 'Consider', label: 'Consider', swatch: 'b-consider' },
  { key: 'Not a Fit', label: 'Not a fit', swatch: 'b-not' },
  { key: 'Shortlisted', label: 'Shortlisted' },
]

function Row({ c, job, picked, onPick }) {
  const nav = useNavigate()
  const done = c.status === 'done'
  const open = (e) => { if (!e.target.closest('a, input, button')) nav(`/candidates/${c.id}`) }
  const matched = c.matched_skills.map(skillName)
  const injected = c.flags.some((f) => f.startsWith('Resume contains'))
  return (
    <div className={`row${picked ? ' picked' : ''}`} onClick={open}>
      <div className="pick">{done && <input type="checkbox" checked={picked} onChange={onPick} aria-label={`Select ${c.display_name} to compare`} />}</div>
      <div className="rank">{c.rank ?? ''}</div>
      <div className="who">
        <Avatar name={c.display_name} top={c.rank && c.rank <= 3} />
        <div className="who-text">
          <Link to={`/candidates/${c.id}`}>{c.display_name}</Link>
          <span className="sub">{done ? `${c.years_experience} yrs experience, ${c.filename}` : c.filename}</span>
          {injected && <span className="flag">Manipulation attempt flagged</span>}
        </div>
      </div>
      <div className="score-cell">
        {done && <ScoreBar candidate={c} weights={job.weights} />}
        {(c.status === 'queued' || c.status === 'processing') && (
          <span className="status-pill"><span className="spinner" />{c.status === 'queued' ? 'Waiting in queue' : 'Screening with AI...'}</span>
        )}
        {c.status === 'failed' && <span className="flag" title={c.error}>Could not read this file</span>}
      </div>
      <div className="verdict">
        {done && <Band value={c.recommendation} />}
        {c.decision !== 'pending' && <span className={`decision ${c.decision}`}>{DECISIONS[c.decision]}</span>}
      </div>
      <div className="skills-cell">
        {done && <span className="have" title={matched.join(', ')}>{matched.length ? matched.join(', ') : 'No listed skills found'}</span>}
        {done && (c.missing_skills.length
          ? <span className="gap" title={c.missing_skills.join(', ')}>Missing {c.missing_skills.join(', ')}</span>
          : <span className="ok">No must-have missing</span>)}
      </div>
    </div>
  )
}

export default function JobDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const [job, setJob] = useState(null)
  const [cands, setCands] = useState(null)
  const [err, setErr] = useState('')
  const [upload, setUpload] = useState({ busy: false, skipped: [] })
  const [filter, setFilter] = useState('All')
  const [query, setQuery] = useState('')
  const [picked, setPicked] = useState([])
  const [weights, setWeights] = useState(null)

  const load = useCallback(async () => {
    try {
      const [j, c] = await Promise.all([api.job(id), api.candidates(id)])
      setJob(j); setCands(c)
      setWeights((w) => w ?? j.weights)
    } catch (e) { setErr(e.message) }
  }, [id])

  useEffect(() => { load() }, [load])

  const list = cands || []
  const pending = list.filter((c) => c.status === 'queued' || c.status === 'processing').length
  useEffect(() => {
    if (!pending) return undefined
    const t = setInterval(load, 1500)
    return () => clearInterval(t)
  }, [pending, load])

  const onFiles = async (files) => {
    setUpload({ busy: true, skipped: [] })
    try {
      const r = await api.upload(id, files)
      setUpload({ busy: false, skipped: r.skipped })
      if (r.added.length) toast(`${r.added.length} resume(s) added, screening now`)
      load()
    } catch (e) { setUpload({ busy: false, skipped: [] }); setErr(e.message) }
  }

  const saveRequirements = async (req) => {
    await api.updateRequirements(id, { ...req, min_years_experience: Number(req.min_years_experience) || 0 })
    await api.rescreen(id)
    toast('Requirements saved, re-screening all resumes')
    load()
  }

  const applyWeights = async () => {
    const j = await api.updateJob(id, { weights })
    setWeights(j.weights)
    toast('Weights applied, ranking updated')
    load()
  }

  const removeJob = async () => {
    if (!window.confirm(`Delete "${job.title}" and all ${list.length} resumes? This cannot be undone.`)) return
    await api.deleteJob(id)
    nav('/')
  }

  const count = (key) => {
    if (key === 'All') return list.length
    if (key === 'Shortlisted') return list.filter((c) => c.decision === 'shortlisted').length
    return list.filter((c) => c.recommendation === key).length
  }

  const shown = useMemo(() => list.filter((c) => {
    if (filter === 'Shortlisted' && c.decision !== 'shortlisted') return false
    if (BANDS.includes(filter) && c.recommendation !== filter) return false
    if (query) {
      const hay = `${c.display_name} ${c.filename} ${c.matched_skills.join(' ')}`.toLowerCase()
      if (!hay.includes(query.toLowerCase())) return false
    }
    return true
  }), [list, filter, query])

  const toggle = (cid) => setPicked((p) => (p.includes(cid) ? p.filter((x) => x !== cid) : p.length >= 3 ? p : [...p, cid]))

  if (err && !job) return <p className="error">{err}</p>
  if (!job || !cands) {
    return (
      <div aria-busy="true">
        <div className="skeleton" style={{ height: 36, width: 420, marginBottom: 24 }} />
        <div className="skeleton" style={{ height: 120, marginBottom: 24 }} />
        <div className="skeleton" style={{ height: 400 }} />
      </div>
    )
  }
  const done = job.stats.done
  const weightsChanged = weights && Object.keys(weights).some((k) => Math.abs((weights[k] || 0) - (job.weights[k] || 0)) > 0.001)
  const usage = job.stats.tokens || {}

  return (
    <>
      <nav className="crumbs" aria-label="Breadcrumb"><Link to="/">Jobs</Link><span aria-hidden="true">/</span><span>{job.title}</span></nav>
      <div className="page-head" style={{ marginBottom: 18 }}>
        <div>
          <h1>{job.title}</h1>
          <p>
            {job.stats.total} resumes, {job.stats.shortlisted} shortlisted.{' '}
            {job.blind_mode ? 'Blind screening is on, so identities stay hidden until you reveal them.' : 'Blind screening is off.'}
          </p>
        </div>
        <div className="btn-row">
          {picked.length >= 2 && <Link className="btn accent" to={`/jobs/${id}/compare?ids=${picked.join(',')}`}>Compare {picked.length}</Link>}
          <a className="btn secondary" href={api.exportUrl(id)}>Export CSV</a>
          <button className="btn ghost danger" onClick={removeJob}>Delete job</button>
        </div>
      </div>

      {err && <p className="error" style={{ marginBottom: 16 }}>{err}</p>}

      <section className="card summary" aria-label="Candidates by fit">
        <MiniDist className="dist" counts={job.stats.by_recommendation} total={done} />
        <div className="filters" role="group" aria-label="Show">
          {FILTERS.map((f) => (
            <button key={f.key} type="button" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
              <b>{count(f.key)}</b>
              <span>{f.swatch && <i className={f.swatch} />}{f.label}</span>
            </button>
          ))}
        </div>
      </section>

      <div className="job-layout">
        <section aria-labelledby="rank-h" className="stack">
          <div className="toolbar">
            <div>
              <h2 id="rank-h">Ranking</h2>
              {pending > 0
                ? <span className="status-pill"><span className="spinner" />Screening {pending} resume(s), {done} done</span>
                : <span className="muted small">Click a candidate to see why they scored what they did. Tick up to 3 to compare.</span>}
            </div>
            <div className="search" style={{ width: 260 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
              <input type="search" placeholder="Search name, file or skill" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search candidates" />
            </div>
          </div>
          <Legend />
          {list.length === 0 ? (
            <div className="card pad" style={{ padding: 40 }}>
              <h2 style={{ marginBottom: 6 }}>No resumes yet</h2>
              <p className="muted">Drop PDF, DOCX or TXT resumes in the upload box. Each one is parsed, scored and explained in a few seconds.</p>
            </div>
          ) : (
            <div>
              <div className="list-head" aria-hidden="true">
                <span /><span>#</span><span>Candidate</span><span>Score</span><span>Verdict</span><span className="skills-h">Skills</span>
              </div>
              <div className="rows">
                {shown.map((c) => <Row key={c.id} c={c} job={job} picked={picked.includes(c.id)} onPick={() => toggle(c.id)} />)}
              </div>
              {shown.length === 0 && <p className="muted" style={{ padding: 16 }}>No candidates match this filter.</p>}
            </div>
          )}
        </section>

        <aside className="side" aria-label="Job tools">
          <section className="card pad">
            <div className="card-head" style={{ marginBottom: 12 }}><h2>Add resumes</h2></div>
            <Dropzone onFiles={onFiles} busy={upload.busy} />
            {upload.skipped.length > 0 && (
              <p className="notice" style={{ marginTop: 10 }}>
                Not added: {upload.skipped.map((s) => `${s.filename} (${s.reason})`).join('; ')}
              </p>
            )}
          </section>
          <RequirementsEditor key={JSON.stringify(job.requirements)} requirements={job.requirements}
            analysedBy={job.analysed_by} onSave={saveRequirements} />
          <AskPanel jobId={id} disabled={done === 0} />
          <details className="card pad">
            <summary>Scoring weights</summary>
            <p className="muted small" style={{ margin: '8px 0 14px' }}>Re-ranks everyone instantly, with no new AI calls.</p>
            {weights && <WeightsEditor value={weights} onChange={setWeights} />}
            <div className="btn-row" style={{ marginTop: 14 }}>
              <button className="btn sm" onClick={applyWeights} disabled={!weightsChanged}>Apply weights</button>
              {weightsChanged && <button className="btn ghost sm" onClick={() => setWeights(job.weights)}>Undo</button>}
            </div>
          </details>
          {usage.calls > 0 && (
            <section className="card pad" aria-labelledby="use-h">
              <div className="card-head" style={{ marginBottom: 10 }}><h2 id="use-h">AI usage for this job</h2></div>
              <dl className="kv">
                <dt>Tokens used</dt><dd className="num">{formatTokens(usage.used)} in {usage.calls} AI call(s)</dd>
                <dt>Per resume</dt><dd className="num">{formatTokens(usage.avg_per_resume)} on average</dd>
                <dt>Saved by cache</dt><dd className="num">{formatTokens(usage.saved)} ({usage.cached_resumes} cached)</dd>
              </dl>
            </section>
          )}
        </aside>
      </div>
    </>
  )
}
