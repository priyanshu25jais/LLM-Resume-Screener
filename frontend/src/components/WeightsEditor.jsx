import { SIGNALS } from '../api.js'

export default function WeightsEditor({ value, onChange }) {
  const total = SIGNALS.reduce((s, x) => s + (Number(value[x.key]) || 0), 0) || 1
  return (
    <div className="weights">
      {SIGNALS.map((s) => (
        <div className="weight-row" key={s.key}>
          <label htmlFor={`w-${s.key}`}><span className="swatch" style={{ background: `var(--sig-${s.key})` }} />{s.name}</label>
          <input id={`w-${s.key}`} type="range" min="0" max="100" step="5"
            value={Math.round((value[s.key] || 0) * 100)}
            onChange={(e) => onChange({ ...value, [s.key]: Number(e.target.value) / 100 })} />
          <span className="num small" style={{ textAlign: 'right' }}>{Math.round(((value[s.key] || 0) / total) * 100)}%</span>
        </div>
      ))}
    </div>
  )
}
