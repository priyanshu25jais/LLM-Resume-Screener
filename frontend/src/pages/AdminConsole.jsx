import { useCallback, useEffect, useState } from 'react'
import { api, formatDate } from '../api.js'
import { useAuth } from '../auth.jsx'
import ActionDialog from '../components/ActionDialog.jsx'
import { Avatar } from '../components/Band.jsx'
import { useToast } from '../components/Toast.jsx'

const STATUS_FILTERS = [['', 'All'], ['pending', 'Pending'], ['active', 'Active'], ['suspended', 'Suspended'], ['deleted', 'Deleted']]
const EVENT_FILTERS = [['flagged', 'Flags'], ['all', 'Everything'], ['admin', 'Admin actions'], ['security', 'Security'], ['account', 'Account activity']]

const EVENT_NAMES = {
  login: 'Logged in', login_failed: 'Wrong password', login_locked: 'Locked after 5 wrong passwords',
  blocked_login: 'Login blocked', register: 'Signed up', upload: 'Uploaded resumes', upload_burst: 'Unusually many uploads',
  duplicate_upload: 'Duplicate uploads', foreign_access: "Tried another recruiter's data", approve: 'Approved',
  suspend: 'Suspended', reactivate: 'Reactivated', delete: 'Deleted', demote: 'Admin role removed', purge: 'Data purged',
  admin_created: 'Admin created', migration: 'Database upgraded', orphan_jobs_assigned: 'Old jobs assigned',
  review_flag: 'Flag reviewed',
}

function plural(n, word) { return `${n} ${word}${n === 1 ? '' : 's'}` }

function detailText(e) {
  const d = e.detail || {}
  if (e.action === 'upload') return plural(d.count || 0, 'file')
  if (e.action === 'duplicate_upload') return `${plural(d.count || 0, 'duplicate')}${d.last_24h ? `, ${d.last_24h} in 24 h` : ''}`
  if (e.action === 'upload_burst') return `${d.count} files in ${d.minutes} min`
  if (e.action === 'foreign_access') return `${d.kind} #${d.id}`
  if (e.action === 'purge') return `${plural(d.jobs || 0, 'job')}, ${plural(d.resumes || 0, 'resume')} removed`
  if (d.email_ref) return `unknown email (ref ${d.email_ref})`
  if (d.status && e.action === 'blocked_login') return `account ${d.status}`
  if (d.sessions_ended !== undefined) return `${plural(d.sessions_ended, 'session')} ended`
  if (d.admins_made_recruiters !== undefined) return `${d.admins_made_recruiters} old admin(s) made recruiters`
  if (d.jobs !== undefined) return plural(d.jobs, 'job')
  if (d.error) return d.error
  return ''
}

function Status({ value }) {
  return <span className={`status-badge s-${value}`}>{value}</span>
}

function actionsFor(account, me) {
  if (account.id === me.id) return []
  if (account.status === 'pending') return ['approve', 'delete']
  if (account.status === 'active') return account.role === 'admin' ? ['suspend', 'demote', 'delete'] : ['suspend', 'delete']
  if (account.status === 'suspended') return ['reactivate', 'delete']
  if (account.status === 'deleted') return ['reactivate']
  return []
}

const ACTION_LABEL = { approve: 'Approve', reactivate: 'Reactivate', suspend: 'Suspend', delete: 'Delete', demote: 'Remove admin' }

export default function AdminConsole() {
  const { user } = useAuth()
  const toast = useToast()
  const [overview, setOverview] = useState(null)
  const [recruiters, setRecruiters] = useState(null)
  const [pending, setPending] = useState([])
  const [admins, setAdmins] = useState([])
  const [events, setEvents] = useState(null)
  const [status, setStatus] = useState('')
  const [query, setQuery] = useState('')
  const [eventKind, setEventKind] = useState('flagged')
  const [eventTarget, setEventTarget] = useState(null)
  const [dialog, setDialog] = useState(null)
  const [err, setErr] = useState('')

  const loadSummary = useCallback(() => {
    api.adminOverview().then(setOverview).catch((e) => setErr(e.message))
    api.adminRecruiters('pending').then(setPending).catch(() => {})
    api.adminAdmins().then(setAdmins).catch(() => {})
  }, [])
  const loadRecruiters = useCallback(() => {
    api.adminRecruiters(status, query.trim()).then(setRecruiters).catch((e) => setErr(e.message))
  }, [status, query])
  const loadEvents = useCallback(() => {
    api.adminEvents(eventKind, eventTarget?.id).then(setEvents).catch((e) => setErr(e.message))
  }, [eventKind, eventTarget])

  useEffect(() => { loadSummary() }, [loadSummary])
  useEffect(() => { const t = setTimeout(loadRecruiters, 250); return () => clearTimeout(t) }, [loadRecruiters])
  useEffect(() => { loadEvents() }, [loadEvents])

  const runAction = async (body) => {
    const { action, account } = dialog
    await api.adminAction(account.id, action, body)
    setDialog(null)
    toast(`${account.name}: ${ACTION_LABEL[action].toLowerCase()} done`)
    loadSummary(); loadRecruiters(); loadEvents()
  }

  const review = async (e) => {
    await api.reviewEvent(e.id)
    toast('Flag marked as reviewed')
    loadSummary(); loadRecruiters(); loadEvents()
  }

  const showEventsFor = (r) => {
    setEventTarget({ id: r.id, name: r.name })
    setEventKind('all')
    document.getElementById('events-h')?.scrollIntoView({ behavior: 'smooth' })
  }

  const o = overview
  const rec = o?.recruiters || {}

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Admin console</h1>
          <p>Recruiter accounts, totals and security events. Candidate details, resumes, scores and job descriptions are never shown here; only recruiters can see their own.</p>
        </div>
      </div>
      {err && <p className="error" style={{ marginBottom: 16 }}>{err}</p>}

      <section className="stat-grid" aria-label="Totals">
        <div className="card stat"><b>{o ? rec.active : '-'}</b><span>Active recruiters</span></div>
        <div className={`card stat${rec.pending ? ' warn' : ''}`}><b>{o ? rec.pending : '-'}</b><span>Waiting for approval</span></div>
        <div className="card stat"><b>{o ? rec.suspended : '-'}</b><span>Suspended</span></div>
        <div className="card stat"><b>{o ? o.jobs : '-'}</b><span>Jobs</span></div>
        <div className="card stat"><b>{o ? o.resumes : '-'}</b><span>Resumes received{o ? `, ${o.resumes_7d} this week` : ''}</span></div>
        <div className={`card stat${o?.open_flags ? ' alert' : ''}`}><b>{o ? o.open_flags : '-'}</b><span>Open security flags</span></div>
      </section>

      {pending.length > 0 && (
        <section className="card pad" style={{ marginBottom: 20 }} aria-labelledby="pend-h">
          <div className="card-head" style={{ marginBottom: 12 }}><h2 id="pend-h">Waiting for approval</h2></div>
          <div className="pending-list">
            {pending.map((r) => (
              <div key={r.id} className="pending-row">
                <Avatar name={r.name} />
                <div className="grow"><b>{r.name}</b><span className="muted small">{r.email}, signed up {formatDate(r.registered_at, true)}</span></div>
                <button className="btn accent sm" onClick={() => setDialog({ action: 'approve', account: r })}>Approve</button>
                <button className="btn ghost sm danger" onClick={() => setDialog({ action: 'delete', account: r })}>Decline</button>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="card" style={{ marginBottom: 20 }} aria-labelledby="rec-h">
        <div className="table-head">
          <h2 id="rec-h">Recruiters</h2>
          <div className="filters-inline">
            <div className="search" style={{ width: 240 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
              <input type="search" placeholder="Search name or email" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search recruiters" />
            </div>
            <div className="segmented small-seg" role="group" aria-label="Status">
              {STATUS_FILTERS.map(([k, label]) => <button key={k} aria-pressed={status === k} onClick={() => setStatus(k)}>{label}</button>)}
            </div>
          </div>
        </div>
        <div className="data-table">
          <table>
            <thead><tr><th>Recruiter</th><th>Status</th><th>Signed up</th><th>Last login</th><th>Jobs</th><th className="r">Resumes</th><th className="r">Flags</th><th /></tr></thead>
            <tbody>
              {recruiters === null && <tr><td colSpan={8}><div className="skeleton" style={{ height: 40 }} /></td></tr>}
              {recruiters?.length === 0 && <tr><td colSpan={8} className="muted">No recruiters match.</td></tr>}
              {recruiters?.map((r) => (
                <tr key={r.id}>
                  <td>
                    <button className="cell-who linkish" onClick={() => showEventsFor(r)} title="Show this recruiter's activity">
                      <Avatar name={r.name} /><span><b>{r.name}</b><span className="muted small">{r.email}</span></span>
                    </button>
                  </td>
                  <td>
                    <Status value={r.status} />
                    {r.status_reason && r.status !== 'active' && <span className="muted tiny-block" title={r.status_reason}>{r.status_reason}</span>}
                    {r.purge_on && <span className="muted tiny-block">Purged on {formatDate(r.purge_on)}</span>}
                  </td>
                  <td className="muted nowrap">{formatDate(r.registered_at)}</td>
                  <td className="muted">{r.last_login_at ? formatDate(r.last_login_at, true) : 'Never'}<span className="tiny-block">{plural(r.logins_7d, 'login')} this week</span></td>
                  <td className="jobs-cell"><b>{r.job_count}</b>{r.job_titles.length > 0 && <span className="muted tiny-block" title={r.job_titles.join('\n')}>{r.job_titles.slice(0, 2).join(', ')}{r.job_titles.length > 2 ? ` +${r.job_titles.length - 2}` : ''}</span>}</td>
                  <td className="r"><b>{r.resume_count}</b><span className="muted tiny-block">+{r.resumes_7d} this week</span></td>
                  <td className="r">{r.open_flags > 0 ? <button className="flag-count" onClick={() => showEventsFor(r)}>{r.open_flags}</button> : <span className="muted">0</span>}</td>
                  <td className="actions-cell">
                    {actionsFor(r, user).map((a) => (
                      <button key={a} className={`btn sm ${a === 'approve' ? 'accent' : a === 'delete' || a === 'suspend' ? 'ghost danger' : 'secondary'}`} onClick={() => setDialog({ action: a, account: r })}>{ACTION_LABEL[a]}</button>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card" style={{ marginBottom: 20 }} aria-labelledby="events-h">
        <div className="table-head">
          <div>
            <h2 id="events-h">Security and audit log</h2>
            <p className="muted small">Flags are for review only; nobody is blocked automatically. Entries hold counts and ids, never resume content. Click a recruiter's name to see only their activity.</p>
          </div>
          <div className="filters-inline">
            {eventTarget && <span className="chip">{eventTarget.name}<button aria-label="Show everyone" onClick={() => setEventTarget(null)}>x</button></span>}
            <div className="segmented small-seg" role="group" aria-label="Event type">
              {EVENT_FILTERS.map(([k, label]) => <button key={k} aria-pressed={eventKind === k} onClick={() => setEventKind(k)}>{label}</button>)}
            </div>
          </div>
        </div>
        <div className="data-table">
          <table>
            <thead><tr><th>When</th><th>Event</th><th>By</th><th>Account</th><th>Reason</th><th>Details</th><th /></tr></thead>
            <tbody>
              {events === null && <tr><td colSpan={7}><div className="skeleton" style={{ height: 40 }} /></td></tr>}
              {events?.length === 0 && <tr><td colSpan={7} className="muted">{eventKind === 'flagged' ? 'No security flags. All clear.' : 'Nothing here yet.'}</td></tr>}
              {events?.map((e) => (
                <tr key={e.id} className={e.flagged && !e.reviewed ? 'flag-row' : ''}>
                  <td className="muted nowrap">{formatDate(e.created_at, true)}</td>
                  <td>
                    <b>{EVENT_NAMES[e.action] || e.action}</b>
                    {e.outcome !== 'success' && <span className={`status-badge s-${e.outcome}`}>{e.outcome}</span>}
                    {e.flagged && <span className={`status-badge ${e.reviewed ? 's-reviewed' : 's-flag'}`}>{e.reviewed ? 'reviewed' : 'flag'}</span>}
                  </td>
                  <td>{e.actor}</td>
                  <td>{e.target}</td>
                  <td className="reason-cell">{e.reason || <span className="muted">-</span>}</td>
                  <td className="muted">{detailText(e)}</td>
                  <td className="actions-cell">{e.flagged && !e.reviewed && <button className="btn secondary sm" onClick={() => review(e)}>Mark reviewed</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid-2">
        <section className="card" aria-labelledby="adm-h">
          <div className="table-head"><h2 id="adm-h">Admins</h2></div>
          <div className="data-table">
            <table>
              <thead><tr><th>Admin</th><th>Status</th><th>Last login</th><th /></tr></thead>
              <tbody>
                {admins.map((a) => (
                  <tr key={a.id}>
                    <td><div className="cell-who"><Avatar name={a.name} /><div><b>{a.name}{a.id === user.id && <span className="muted small"> (you)</span>}</b><span className="muted small">{a.email}</span></div></div></td>
                    <td><Status value={a.status} /></td>
                    <td className="muted">{a.last_login_at ? formatDate(a.last_login_at, true) : 'Never'}</td>
                    <td className="actions-cell">
                      {actionsFor(a, user).map((x) => <button key={x} className="btn ghost sm" onClick={() => setDialog({ action: x, account: a })}>{ACTION_LABEL[x]}</button>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small pad" style={{ paddingTop: 0 }}>New admins are made only with <code>python scripts/create_admin.py</code> on the server. There must always be one active admin.</p>
        </section>
        <section className="card pad stack" aria-labelledby="pol-h">
          <h2 id="pol-h">Data rules</h2>
          {o && (
            <ul className="points plus small">
              <li>{o.policy.require_approval ? 'New recruiters wait for an admin to approve them.' : 'New recruiters can start right after signing up.'}</li>
              <li>Suspending ends all of that account's sessions at once and keeps its data.</li>
              <li>{o.policy.deletion_grace_days > 0 ? `A deleted recruiter's jobs, resumes and results are kept ${o.policy.deletion_grace_days} days so it can be undone, then removed for good.` : 'Deleting removes the recruiter\'s jobs, resumes and results at once.'}</li>
              <li>Audit and security entries are kept {o.policy.audit_retention_days} days.</li>
              <li>{plural(o.logins_7d, 'login')} and {plural(o.failed_logins_7d, 'failed login')} in the last 7 days.</li>
            </ul>
          )}
        </section>
      </div>

      {dialog && <ActionDialog action={dialog.action} account={dialog.account} policy={o?.policy} onCancel={() => setDialog(null)} onConfirm={runAction} />}
    </>
  )
}
