import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { MiniDist } from '../components/Band.jsx'

function JobCard({ j }) {
  const must = j.requirements.must_have_skills || []
  const strong = j.stats.by_recommendation?.['Strong Fit'] || 0
  return (
    <Link className="card job-card" to={`/jobs/${j.id}`}>
      <div>
        <h2>{j.title}</h2>
        <p className="tag" style={{ marginTop: 4 }}>
          {j.stats.processing > 0 ? <><span className="spinner" />Screening {j.stats.processing} resume(s)</> : j.blind_mode ? 'Blind screening on' : 'Blind screening off'}
        </p>
      </div>
      <div className="chips">
        {must.slice(0, 4).map((s) => <span key={s} className="chip">{s}</span>)}
        {must.length > 4 && <span className="chip more">+{must.length - 4}</span>}
      </div>
      <MiniDist counts={j.stats.by_recommendation} total={j.stats.done} />
      <div className="stats">
        <div><b>{j.stats.total}</b><span>resumes</span></div>
        <div><b>{strong}</b><span>strong fits</span></div>
        <div><b>{j.stats.done ? Math.round(j.stats.top_score) : '-'}</b><span>top score</span></div>
      </div>
    </Link>
  )
}

function SkeletonCards() {
  return (
    <div className="job-grid" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className="card job-card">
          <div className="skeleton" style={{ height: 22, width: '70%' }} />
          <div className="skeleton" style={{ height: 14, width: '40%' }} />
          <div className="skeleton" style={{ height: 8 }} />
          <div className="skeleton" style={{ height: 44 }} />
        </div>
      ))}
    </div>
  )
}

export default function Jobs() {
  const [jobs, setJobs] = useState(null)
  const [demos, setDemos] = useState([])
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const nav = useNavigate()

  useEffect(() => {
    api.jobs().then(setJobs).catch((e) => { setErr(e.message); setJobs([]) })
    api.demos().then(setDemos).catch(() => {})
  }, [])

  const demo = async (key) => {
    setBusy(key); setErr('')
    try { const job = await api.loadDemo(key); nav(`/jobs/${job.id}`) } catch (e) { setErr(e.message); setBusy('') }
  }

  const demoButtons = demos.filter((d) => d.available).map((d) => (
    <button key={d.key} className="btn secondary" onClick={() => demo(d.key)} disabled={!!busy}>
      {busy === d.key ? <><span className="spinner" />Loading...</> : d.title}
    </button>
  ))

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Jobs</h1>
          <p>Your jobs. Each job ranks its applicants against its job description. Open one to upload resumes or review the shortlist.</p>
        </div>
        <Link className="btn accent" to="/jobs/new">New job</Link>
      </div>
      {err && <p className="error" style={{ marginBottom: 16 }}>{err}</p>}
      {jobs === null && <SkeletonCards />}
      {jobs?.length === 0 && (
        <div className="card empty-hero">
          <div>
            <h2>Screen your first batch of resumes</h2>
            <p className="muted">Create a job from its description, or load a sample job with 15 ready-made resumes to see the ranking in action.</p>
            <div className="samples-row" style={{ marginTop: 18 }}>{demoButtons}</div>
          </div>
          <Link className="btn accent" to="/jobs/new">New job</Link>
        </div>
      )}
      {jobs?.length > 0 && (
        <>
          <div className="job-grid">{jobs.map((j) => <JobCard key={j.id} j={j} />)}</div>
          {demoButtons.length > 0 && (
            <div className="samples">
              <h3>Load a sample job with 15 resumes</h3>
              <div className="samples-row">{demoButtons}</div>
            </div>
          )}
        </>
      )}
    </>
  )
}
