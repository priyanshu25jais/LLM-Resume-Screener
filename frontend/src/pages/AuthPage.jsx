import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { useAuth } from '../auth.jsx'

const PREVIEW = [
  { name: 'Candidate 1', score: 90, band: 'Strong Fit', cls: 'strong', parts: [41, 24, 14, 10] },
  { name: 'Candidate 9', score: 74, band: 'Good Fit', cls: 'good', parts: [33, 20, 12, 9] },
  { name: 'Candidate 4', score: 52, band: 'Consider', cls: 'consider', parts: [22, 15, 9, 6] },
]
const SIG = ['llm', 'skills', 'semantic', 'experience']

function Preview() {
  return (
    <div className="auth-preview" aria-hidden="true">
      {PREVIEW.map((p) => (
        <div key={p.name} className="auth-preview-row">
          <span className="who">{p.name}</span>
          <b>{p.score}</b>
          <span className="bar">{p.parts.map((w, i) => <i key={SIG[i]} style={{ width: `${w}%`, background: `var(--sig-${SIG[i]})` }} />)}</span>
          <span className={`band ${p.cls}`}>{p.band}</span>
        </div>
      ))}
    </div>
  )
}

export default function AuthPage({ mode }) {
  const { setUser } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const [opts, setOpts] = useState(null)
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [waiting, setWaiting] = useState('')

  useEffect(() => { api.authOptions().then(setOpts).catch(() => setOpts({ allow_registration: true, require_approval: true, demo_login: false })) }, [])
  useEffect(() => { setErr(''); setWaiting('') }, [mode])

  const signup = mode === 'register'
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const done = (user) => {
    setUser(user)
    if (loc.pathname === '/login' || loc.pathname === '/register') nav('/', { replace: true })
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy('form'); setErr('')
    try {
      if (signup) {
        const user = await api.register(form.name, form.email, form.password)
        if (user.status === 'pending') { setWaiting(user.email); setBusy(''); return }
        done(user)
      } else {
        done(await api.login(form.email, form.password))
      }
    } catch (ex) { setErr(ex.message); setBusy('') }
  }

  const demo = async () => {
    setBusy('demo'); setErr('')
    try { done(await api.demoLogin()) } catch (ex) { setErr(ex.message); setBusy('') }
  }

  return (
    <div className="auth">
      <section className="auth-pitch">
        <h1>Screen resumes with an LLM, and see why each candidate ranks where they do.</h1>
        <p>Every score is split into four parts: the LLM's rating, skill match, text similarity and experience. Each recruiter works only on their own jobs.</p>
        <Preview />
      </section>

      <section className="card auth-card">
        {waiting ? (
          <div className="auth-waiting">
            <h2>Account created</h2>
            <p className="muted">Your recruiter account for <b>{waiting}</b> is waiting for an admin to approve it. You can log in once it is approved.</p>
            <Link className="btn secondary wide" to="/login" style={{ marginTop: 20 }}>Back to log in</Link>
          </div>
        ) : (
          <>
            <h2>{signup ? 'Create a recruiter account' : 'Log in'}</h2>
            <p className="muted small">
              {signup
                ? (opts?.require_approval ? 'An admin approves new accounts before the first login.' : 'You can start right after signing up.')
                : 'Recruiters see their jobs; admins see the admin console.'}
            </p>
            <form onSubmit={submit} className="auth-form">
              {signup && (
                <label className="field">Full name
                  <input type="text" value={form.name} onChange={set('name')} autoComplete="name" required minLength={2} placeholder="Your full name" />
                </label>
              )}
              <label className="field">Email
                <input type="email" value={form.email} onChange={set('email')} autoComplete="email" required placeholder="you@company.com" />
              </label>
              <label className="field">Password
                {signup && <span className="hint">At least 8 characters</span>}
                <input type="password" value={form.password} onChange={set('password')} autoComplete={signup ? 'new-password' : 'current-password'} required minLength={signup ? 8 : 1} />
              </label>
              {err && <p className="error small">{err}</p>}
              <button className="btn accent wide" disabled={!!busy || !opts}>
                {busy === 'form' ? <><span className="spinner" />Please wait...</> : signup ? 'Create account' : 'Log in'}
              </button>
            </form>

            {opts && (
              <p className="small muted switch-mode">
                {signup
                  ? <>Already have an account? <Link to="/login">Log in</Link></>
                  : opts.allow_registration && <>New recruiter? <Link to="/register">Create an account</Link></>}
              </p>
            )}
            {opts?.demo_login && !signup && (
              <>
                <div className="or"><span>or</span></div>
                <button type="button" className="btn secondary wide" onClick={demo} disabled={!!busy}>
                  {busy === 'demo' ? <><span className="spinner" />Opening demo...</> : 'Try the demo recruiter account'}
                </button>
                <p className="tiny muted">Load a sample job from the Jobs page to see the ranking.</p>
              </>
            )}
          </>
        )}
      </section>
    </div>
  )
}
