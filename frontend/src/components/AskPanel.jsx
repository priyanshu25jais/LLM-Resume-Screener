import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, formatTokens } from '../api.js'

const IDEAS = ['Who has deployed to AWS?', 'Who has led a team?', 'Which candidates have used Docker?']

export default function AskPanel({ jobId, disabled }) {
  const [q, setQ] = useState('')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const ask = async (question) => {
    if (!question.trim()) return
    setBusy(true); setErr('')
    try { setRes(await api.ask(jobId, question)) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <section className="card pad ask" aria-labelledby="ask-h">
      <div className="card-head" style={{ marginBottom: 12 }}>
        <div>
          <h2 id="ask-h">Ask about the candidates</h2>
          <p>Answers come only from the uploaded resumes</p>
        </div>
      </div>
      <form onSubmit={(e) => { e.preventDefault(); ask(q) }}>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Who has used Kafka?" aria-label="Question" disabled={disabled} />
        <button className="btn accent" disabled={busy || disabled}>{busy ? <span className="spinner" /> : 'Ask'}</button>
      </form>
      {!res && !disabled && (
        <div className="suggest">
          {IDEAS.map((i) => <button key={i} type="button" onClick={() => { setQ(i); ask(i) }}>{i}</button>)}
        </div>
      )}
      {err && <p className="error" style={{ marginTop: 12 }}>{err}</p>}
      {res && (
        <div className="answer">
          <p>{res.answer}</p>
          {res.sources.length > 0 && (
            <ul className="sources">
              {res.sources.map((s, i) => (
                <li key={i}><Link to={`/candidates/${s.candidate_id}`}>{s.display_name}</Link><br />{s.snippet}</li>
              ))}
            </ul>
          )}
          <p className="muted small" style={{ marginTop: 10 }}>
            Answered by {res.answered_by.replace(':', ' ')}{res.tokens ? `, ${formatTokens(res.tokens)} tokens` : ''}
          </p>
        </div>
      )}
    </section>
  )
}
