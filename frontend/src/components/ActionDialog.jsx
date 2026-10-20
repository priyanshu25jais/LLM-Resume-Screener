import { useEffect, useRef, useState } from 'react'

// What each admin action means; serious ones need a reason and an explicit confirmation
export const ACTIONS = {
  approve: { title: 'Approve recruiter', button: 'Approve', serious: false, text: 'They can log in and use recruiter features straight away.' },
  reactivate: { title: 'Reactivate account', button: 'Reactivate', serious: false, text: 'The account can log in again. A deleted account can only be restored before its data is purged.' },
  suspend: { title: 'Suspend account', button: 'Suspend', serious: true, text: 'All of their sessions end now and they cannot log in. Their jobs and resumes are kept untouched.' },
  delete: { title: 'Delete account', button: 'Delete account', serious: true, text: '' },
  demote: { title: 'Remove admin role', button: 'Remove admin role', serious: true, text: 'This person becomes a recruiter and is logged out.' },
}

export default function ActionDialog({ action, account, policy, onCancel, onConfirm }) {
  const info = ACTIONS[action]
  const [reason, setReason] = useState('')
  const [checked, setChecked] = useState(false)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const first = useRef(null)

  useEffect(() => {
    first.current?.focus()
    const esc = (e) => { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onCancel])

  const grace = policy?.deletion_grace_days ?? 30
  const text = action === 'delete'
    ? (grace > 0
      ? `The account is disabled now. Their jobs, resumes and results are kept for ${grace} days so this can be undone, then removed for good.`
      : 'The account is disabled and all of their jobs, resumes and results are removed for good right away.')
    : info.text
  const ready = !info.serious || (reason.trim().length >= 5 && checked && (action !== 'delete' || typed.trim().toLowerCase() === account.email))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try { await onConfirm({ reason: reason.trim(), confirm: checked || !info.serious }) } catch (ex) { setErr(ex.message); setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel() }}>
      <form className="modal card" role="dialog" aria-modal="true" aria-labelledby="dlg-h" onSubmit={submit}>
        <h2 id="dlg-h">{info.title}</h2>
        <p className="who-line"><b>{account.name}</b> <span className="muted">{account.email}</span></p>
        <p className="muted small">{text}</p>
        <label className="field">
          Reason {info.serious ? <span className="hint">Required, saved in the audit log</span> : <span className="hint">Optional</span>}
          <textarea ref={first} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500}
            placeholder={info.serious ? 'For example: repeated failed logins, account no longer needed' : ''} />
        </label>
        {action === 'delete' && (
          <label className="field">Type their email to confirm
            <input type="text" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={account.email} />
          </label>
        )}
        {info.serious && (
          <label className="switch">
            <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
            <div><strong>I understand what this does</strong></div>
          </label>
        )}
        {err && <p className="error small">{err}</p>}
        <div className="btn-row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn ghost" onClick={onCancel}>Cancel</button>
          <button className={`btn ${info.serious ? 'danger-fill' : 'accent'}`} disabled={!ready || busy}>{busy ? <span className="spinner" /> : info.button}</button>
        </div>
      </form>
    </div>
  )
}
