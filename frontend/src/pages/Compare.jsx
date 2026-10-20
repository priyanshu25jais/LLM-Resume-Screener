import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import Band, { Avatar } from '../components/Band.jsx'
import ScoreBar from '../components/ScoreBar.jsx'

export default function Compare() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const [job, setJob] = useState(null)
  const [list, setList] = useState([])
  const [err, setErr] = useState('')

  useEffect(() => {
    const ids = (params.get('ids') || '').split(',').filter(Boolean)
    Promise.all([api.job(id), ...ids.map((x) => api.candidate(x))])
      .then(([j, ...cs]) => { setJob(j); setList(cs.sort((a, b) => b.final_score - a.final_score)) })
      .catch((e) => setErr(e.message))
  }, [id, params])

  if (err) return <p className="error">{err}</p>
  if (!job) return <div className="skeleton" style={{ height: 480 }} aria-busy="true" />

  const allMust = job.requirements.must_have_skills || []
  const has = (c, skill) => {
    const sm = c.skill_match || {}
    if ((sm.matched_must || []).some((s) => s === skill || s.endsWith(`(for ${skill})`))) return 'hit'
    if ((sm.partial_must || []).some((p) => p.skill === skill)) return 'partial'
    return 'miss'
  }

  return (
    <>
      <nav className="crumbs" aria-label="Breadcrumb"><Link to="/">Jobs</Link><span aria-hidden="true">/</span><Link to={`/jobs/${id}`}>{job.title}</Link><span aria-hidden="true">/</span><span>Compare</span></nav>
      <div className="page-head"><div><h1>Compare candidates</h1><p>Side by side on the same requirements, highest score first.</p></div></div>
      <div className="compare" style={{ '--cols': list.length }}>
        {list.map((c) => (
          <section key={c.id} className="card pad">
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 14 }}>
              <Avatar name={c.display_name} />
              <div><h2><Link to={`/candidates/${c.id}`}>{c.display_name}</Link></h2><Band value={c.recommendation} /></div>
            </div>
            <ScoreBar candidate={c} weights={job.weights} />
            <p className="row-label">Summary</p>
            <p className="small" style={{ lineHeight: 1.55 }}>{c.evaluation.summary}</p>
            <p className="row-label">Must-have skills</p>
            <div className="chips">{allMust.map((s) => <span key={s} className={`chip ${has(c, s)}`}>{s}</span>)}</div>
            <p className="row-label">Experience</p>
            <p className="small">{c.years_experience} years</p>
            <p className="row-label">Top strengths</p>
            <ul className="points plus small">{(c.evaluation.strengths || []).slice(0, 3).map((s) => <li key={s}>{s}</li>)}</ul>
            <p className="row-label">Main gaps</p>
            <ul className="points minus small">{(c.evaluation.gaps || []).length ? c.evaluation.gaps.slice(0, 3).map((s) => <li key={s}>{s}</li>) : <li>No gaps noted</li>}</ul>
          </section>
        ))}
      </div>
    </>
  )
}
