import { SIGNALS } from '../api.js'

const CUTS = [45, 60, 75] // recommendation band boundaries

// Stacked bar: each coloured part is one weighted signal
export function contributions(c, weights) {
  return SIGNALS.map((s) => ({ ...s, value: 100 * (weights?.[s.key] ?? 0) * (c[s.field] ?? 0) }))
}

export default function ScoreBar({ candidate, weights, large = false }) {
  const parts = contributions(candidate, weights)
  let left = 0
  const label = parts.map((p) => `${p.name} ${p.value.toFixed(1)}`).join(', ')
  return (
    <div className={`scorebar${large ? ' large' : ''}`}>
      <span className="score">{Math.round(candidate.final_score)}</span>
      <div className="track" role="img" aria-label={`Score ${candidate.final_score} of 100: ${label}`}>
        {parts.map((p) => {
          const seg = (
            <span key={p.key} className={`seg ${p.key}`} style={{ left: `${left}%`, width: `${p.value}%` }}
              title={`${p.name}: ${p.value.toFixed(1)} points`} />
          )
          left += p.value
          return seg
        })}
        {CUTS.map((x) => <span key={x} className="cut" style={{ left: `${x}%` }} />)}
      </div>
    </div>
  )
}

export function Legend() {
  return (
    <div className="legend" aria-label="Score bar colours">
      {SIGNALS.map((s) => (
        <span key={s.key}><i style={{ background: `var(--sig-${s.key})` }} />{s.name}</span>
      ))}
      <span>Lines at 45, 60 and 75 mark the fit bands</span>
    </div>
  )
}
