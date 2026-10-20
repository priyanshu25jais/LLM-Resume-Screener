import { useEffect, useState } from 'react'
import { Link, Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import { api } from './api.js'
import { AuthProvider, useAuth } from './auth.jsx'
import { Avatar } from './components/Band.jsx'
import { ToastProvider } from './components/Toast.jsx'
import Jobs from './pages/Jobs.jsx'
import NewJob from './pages/NewJob.jsx'
import JobDetail from './pages/JobDetail.jsx'
import Candidate from './pages/Candidate.jsx'
import Compare from './pages/Compare.jsx'
import AuthPage from './pages/AuthPage.jsx'
import AdminConsole from './pages/AdminConsole.jsx'

function Mark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--ink)" />
      <rect x="7" y="9" width="18" height="3" rx="1.5" fill="var(--sig-llm)" />
      <rect x="7" y="15" width="13" height="3" rx="1.5" fill="var(--sig-skills)" />
      <rect x="7" y="21" width="8" height="3" rx="1.5" fill="var(--sig-semantic)" />
    </svg>
  )
}

function readTheme() {
  try {
    const saved = localStorage.getItem('shortlist-theme')
    if (saved === 'dark' || saved === 'light') return saved
  } catch {}
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function ThemeToggle() {
  const [theme, setTheme] = useState(readTheme)
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('shortlist-theme', theme) } catch {}
  }, [theme])
  const dark = theme === 'dark'
  return (
    <button className="icon-btn" onClick={() => setTheme(dark ? 'light' : 'dark')} aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'} title={dark ? 'Light mode' : 'Dark mode'}>
      {dark ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
      ) : (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
      )}
    </button>
  )
}

function AiStatus({ health }) {
  if (health === null) return null
  if (health === false) return <span className="ai-pill"><span className="dot off" />Backend not reachable</span>
  if (!health.llm_available) return <span className="ai-pill" title="Add an API key in backend/.env"><span className="dot off" /><span>Offline mode<span className="long">, no LLM key</span></span></span>
  const backups = (health.llm_chain || []).slice(1).map((x) => x.split(':')[0])
  return (
    <span className="ai-pill" title={(health.llm_chain || []).join(' -> ')}>
      <span className="dot" />
      <span><b>{health.llm_provider}</b><span className="long"> {health.llm_model}{backups.length > 0 && `, backup ${backups.join(', ')}`}</span></span>
    </span>
  )
}

function UserMenu() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const out = async () => { await logout(); nav('/', { replace: true }) }
  return (
    <div className="user-chip">
      <Avatar name={user.name} />
      <span className="who"><b>{user.name}</b><small>{user.role === 'admin' ? 'Admin' : 'Recruiter'}</small></span>
      <button className="btn ghost sm" onClick={out}>Log out</button>
    </div>
  )
}

function Shell() {
  const { user } = useAuth()
  const [health, setHealth] = useState(null)
  useEffect(() => { api.health().then(setHealth).catch(() => setHealth(false)) }, [])

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand"><Mark />Shortlist</Link>
          {user?.role === 'recruiter' && (
            <nav aria-label="Main">
              <NavLink to="/" end>Jobs</NavLink>
              <NavLink to="/jobs/new">New job</NavLink>
            </nav>
          )}
          {user?.role === 'admin' && (
            <nav aria-label="Main"><NavLink to="/" end>Admin console</NavLink></nav>
          )}
          <div className="right">
            <AiStatus health={health} />
            <ThemeToggle />
            {user && <UserMenu />}
          </div>
        </div>
      </header>
      <main>
        {user === undefined && <div className="skeleton" style={{ height: 320 }} aria-busy="true" />}
        {user === null && (
          <Routes>
            <Route path="/register" element={<AuthPage mode="register" />} />
            <Route path="*" element={<AuthPage mode="login" />} />
          </Routes>
        )}
        {user?.role === 'admin' && (
          <Routes>
            <Route path="/" element={<AdminConsole />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
        {user?.role === 'recruiter' && (
          <Routes>
            <Route path="/" element={<Jobs />} />
            <Route path="/jobs/new" element={<NewJob />} />
            <Route path="/jobs/:id" element={<JobDetail />} />
            <Route path="/jobs/:id/compare" element={<Compare />} />
            <Route path="/candidates/:cid" element={<Candidate />} />
            <Route path="/login" element={<Navigate to="/" replace />} />
            <Route path="/register" element={<Navigate to="/" replace />} />
            <Route path="*" element={<p>Page not found. <Link to="/">Go to jobs</Link></p>} />
          </Routes>
        )}
      </main>
    </>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </ToastProvider>
  )
}
