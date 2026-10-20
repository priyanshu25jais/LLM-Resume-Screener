import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, byWhom, formatTokens, llmFellBack, skillName } from '../api.js'
import Band, { Avatar } from '../components/Band.jsx'
import ScoreBar, { contributions } from '../components/ScoreBar.jsx'
import { useToast } from '../components/Toast.jsx'

const SUBS = [['skills_score', 'Skills'], ['experience_score', 'Experience'], ['projects_score', 'Projects'], ['education_score', 'Education']]
const DECISION_BUTTONS = [['shortlisted', 'Shortlist', 'Shortlisted'], ['on_hold', 'Hold', 'Put on hold'], ['rejected', 'Reject', 'Rejected']]

function SkillRow({ title, matched, partial, missing }) {
  return (
    <div>
      <h3 style={{ marginBottom: 10 }}>{title}</h3>
      <div className="chips">
        {matched.map((s) => <span key={s} className="chip hit" title={s}>{skillName(s)}</span>)}
        {partial.map((p) => <span key={p.skill} className="chip partial" title={`Related experience: ${p.via.join(', ')}`}>{p.skill} via {p.via[0]}</span>)}
        {missing.map((s) => <span key={s} className="chip miss">{s}</span>)}
        {!matched.length && !partial.length && !missing.length && <span className="muted small">None listed for this job</span>}
      </div>
    </div>
  )
}

function usageText(t) {
  if (!t) return ''
  if (t.cached) return ` Served from cache, saving ${formatTokens(t.saved || 0)} tokens.`
  if (t.total) return ` Used ${formatTokens(t.total)} tokens (${formatTokens(t.input)} in, ${formatTokens(t.output)} out).`
  return ''
}

export default function Candidate() {
  const { cid } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const [c, setC] = useState(null)
  const [job, setJob] = useState(null)
  const [order, setOrder] = useState([])
  const [reveal, setReveal] = useState(false)
  const [notes, setNotes] = useState('')
  const [err, setErr] = useState('')

  const load = useCallback(async () => {
    try {
      const d = await api.candidate(cid, reveal)
      setC(d)
      setNotes(d.notes || '')
    } catch (e) { setErr(e.message) }
  }, [cid, reveal])

  const jobId = c?.job_id
  const status = c?.status
  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!jobId) return
    api.job(jobId).then(setJob).catch((e) => setErr(e.message))
    api.candidates(jobId).then((list) => setOrder(list.filter((x) => x.status === 'done').map((x) => x.id))).catch(() => {})
  }, [jobId, status])
  useEffect(() => {
    if (status !== 'queued' && status !== 'processing') return undefined
    const t = setInterval(load, 1500)
    return () => clearInterval(t)
  }, [status, load])

  const decide = async (decision, done) => {
    const next = c.decision === decision ? 'pending' : decision
    const d = await api.updateCandidate(cid, { decision: next })
    setC((x) => ({ ...x, decision: d.decision }))
    toast(next === 'pending' ? 'Decision cleared' : done)
  }
  const saveNotes = async () => { await api.updateCandidate(cid, { notes }); toast('Notes saved') }
  const rescreen = async () => { await api.reprocess(cid); toast('Re-screening this resume'); load() }
  const remove = async () => {
    if (!window.confirm('Delete this candidate and their resume file?')) return
    await api.deleteCandidate(cid)
    nav(`/jobs/${c.job_id}`)
  }

  if (err) return <p className="error">{err}</p>
  if (!c || !job) {
    return (
      <div aria-busy="true">
        <div className="skeleton" style={{ height: 110, marginBottom: 20 }} />
        <div className="grid-2"><div className="skeleton" style={{ height: 380 }} /><div className="skeleton" style={{ height: 380 }} /></div>
      </div>
    )
  }

  const crumbs = (
    <nav className="crumbs" aria-label="Breadcrumb">
      <Link to="/">Jobs</Link><span aria-hidden="true">/</span>
      <Link to={`/jobs/${c.job_id}`}>{job.title}</Link><span aria-hidden="true">/</span>
      <span>{c.display_name}</span>
    </nav>
  )
  if (c.status !== 'done') {
    return (
      <>
        {crumbs}
        <div className="card pad stack">
          <h1>{c.display_name}</h1>
          {c.status === 'failed'
            ? <p className="error">This resume could not be screened: {c.error}</p>
            : <p className="status-pill"><span className="spinner" />Screening this resume...</p>}
          <div className="btn-row">
            <button className="btn secondary" onClick={rescreen}>Try again</button>
            <button className="btn ghost danger" onClick={remove}>Delete candidate</button>
          </div>
        </div>
      </>
    )
  }

  const ev = c.evaluation || {}
  const sm = c.skill_match || {}
  const parts = contributions(c, job.weights)
  const pos = order.indexOf(c.id)
  const prev = pos > 0 ? order[pos - 1] : null
  const next = pos >= 0 && pos < order.length - 1 ? order[pos + 1] : null

  return (
    <>
      {crumbs}
      <section className="card cand-hero">
        <Avatar name={c.display_name} large top={c.rank <= 3} />
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <h1>{c.display_name}</h1>
            <Band value={c.recommendation} large />
          </div>
          <p className="sub">
            <span>Rank {c.rank} of {job.stats.done}</span>
            <span>{c.years_experience} years of experience</span>
            <span>{c.filename}</span>
          </p>
        </div>
        <div className="actions">
          <div className="segmented" role="group" aria-label="Decision">
            {DECISION_BUTTONS.map(([d, label, done]) => (
              <button key={d} className={d} aria-pressed={c.decision === d} onClick={() => decide(d, done)}>{label}</button>
            ))}
          </div>
          <div className="pager">
            <button className="btn secondary sm" disabled={!prev} onClick={() => nav(`/candidates/${prev}`)}>Previous</button>
            <button className="btn secondary sm" disabled={!next} onClick={() => nav(`/candidates/${next}`)}>Next</button>
          </div>
        </div>
      </section>

      {c.flags.length > 0 && (
        <div className="flagbox" role="alert">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={{ flex: 'none', marginTop: 2 }}><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /></svg>
          <div>{c.flags.map((f) => <p key={f}>{f}</p>)}</div>
        </div>
      )}

      <div className="grid-2">
        <section className="card pad" aria-labelledby="why-h">
          <div className="card-head"><h2 id="why-h">Why this score</h2></div>
          <ScoreBar candidate={c} weights={job.weights} large />
          <table className="signals">
            <tbody>
              {parts.map((p) => (
                <tr key={p.key}>
                  <td><span className="swatch" style={{ background: `var(--sig-${p.key})` }} />{p.name}</td>
                  <td className="r">{Math.round(c[p.field] * 100)} x {Math.round(job.weights[p.key] * 100)}%</td>
                  <td className="r" style={{ color: 'var(--ink)', fontWeight: 650 }}>{p.value.toFixed(1)}</td>
                </tr>
              ))}
              <tr className="total"><td>Final score</td><td /><td className="r">{c.final_score.toFixed(1)}</td></tr>
            </tbody>
          </table>
          <div className="subscores" aria-label="LLM rubric scores">
            {SUBS.map(([k, label]) => (
              <div key={k}><b>{ev[k] ?? '-'}</b><span>{label}</span><div className="meter"><span style={{ width: `${ev[k] || 0}%` }} /></div></div>
            ))}
          </div>
          <p className="muted small" style={{ marginTop: 12 }}>
            Rubric by {byWhom(c.evaluated_by)}, which on its own rated this resume {ev.overall_score}/100.{usageText(ev.tokens)}
            {llmFellBack(c.evaluated_by) && ' No LLM could be reached when this resume was screened; use Re-screen later for an LLM evaluation.'}
          </p>
        </section>

        <section className="card pad stack" aria-labelledby="sum-h">
          <h2 id="sum-h">Summary</h2>
          <p style={{ lineHeight: 1.6 }}>{ev.summary}</p>
          <h3>Strengths</h3>
          <ul className="points plus">{(ev.strengths || []).length ? ev.strengths.map((s) => <li key={s}>{s}</li>) : <li>No strengths found for this job</li>}</ul>
          <h3>Gaps and risks</h3>
          <ul className="points minus">{(ev.gaps || []).length ? ev.gaps.map((s) => <li key={s}>{s}</li>) : <li>No gaps noted</li>}</ul>
        </section>
      </div>

      <section className="card pad" style={{ marginTop: 20 }} aria-labelledby="sk-h">
        <div className="card-head">
          <div><h2 id="sk-h">Skills against the job</h2><p>Green: found. Dashed: a related skill instead, half credit. Red: not found.</p></div>
        </div>
        <div className="req-grid">
          <SkillRow title="Must have" matched={sm.matched_must || []} partial={sm.partial_must || []} missing={sm.missing_must || []} />
          <SkillRow title="Nice to have" matched={sm.matched_nice || []} partial={sm.partial_nice || []} missing={sm.missing_nice || []} />
          <div>
            <h3 style={{ marginBottom: 10 }}>Other skills on the resume</h3>
            <div className="chips">{(sm.extra_skills || []).map((s) => <span key={s} className="chip">{s}</span>)}</div>
          </div>
        </div>
      </section>

      <div className="grid-2" style={{ marginTop: 20 }}>
        <section className="card pad stack" aria-labelledby="iq-h">
          <h2 id="iq-h">Interview questions</h2>
          <ol className="questions">{(ev.interview_questions || []).map((q) => <li key={q}>{q}</li>)}</ol>
        </section>
        <section className="card pad stack" aria-labelledby="notes-h">
          <h2 id="notes-h">Your notes</h2>
          <textarea style={{ minHeight: 120 }} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Phone screen on Monday; ask about the Kafka migration." />
          <div className="btn-row"><button className="btn secondary" onClick={saveNotes}>Save notes</button></div>
        </section>
      </div>

      <section className="card pad stack" style={{ marginTop: 20 }}>
        <div className="toolbar">
          <h2>Resume</h2>
          {c.identity_hidden
            ? <button className="btn secondary sm" onClick={() => setReveal(true)}>Reveal identity</button>
            : job.blind_mode && <button className="btn ghost sm" onClick={() => setReveal(false)}>Hide identity</button>}
        </div>
        {!c.identity_hidden && (
          <dl className="kv">
            <dt>Email</dt><dd>{c.email || 'Not found'}</dd>
            <dt>Phone</dt><dd>{c.phone || 'Not found'}</dd>
            <dt>Links</dt><dd>{c.links.length ? c.links.join(', ') : 'None'}</dd>
          </dl>
        )}
        <details>
          <summary>{c.identity_hidden ? 'Anonymised text the AI read' : 'Full resume text'}</summary>
          <div className="resume-text" style={{ marginTop: 12 }}>{c.resume_text}</div>
        </details>
        <div className="btn-row">
          <button className="btn ghost sm" onClick={rescreen}>Re-screen this resume</button>
          <button className="btn ghost sm danger" onClick={remove}>Delete candidate</button>
          <span className="muted small">Processed in {(c.processing_ms / 1000).toFixed(1)} s</span>
        </div>
      </section>
    </>
  )
}
