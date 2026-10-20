export const BAND_CLASS = { 'Strong Fit': 'strong', 'Good Fit': 'good', Consider: 'consider', 'Not a Fit': 'not' }

export default function Band({ value, large = false }) {
  if (!value) return null
  return <span className={`band ${BAND_CLASS[value] || 'not'}${large ? ' lg' : ''}`}>{value}</span>
}

export function initials(name = '') {
  const m = name.match(/^Candidate (\d+)$/)
  if (m) return `C${m[1]}`
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?'
}

export function Avatar({ name, top = false, large = false }) {
  return <span className={`avatar${top ? ' top' : ''}${large ? ' lg' : ''}`} aria-hidden="true">{initials(name)}</span>
}

export function MiniDist({ counts, total, className = '' }) {
  const order = [['Strong Fit', 'b-strong'], ['Good Fit', 'b-good'], ['Consider', 'b-consider'], ['Not a Fit', 'b-not']]
  const label = order.map(([b]) => `${b}: ${counts?.[b] || 0}`).join(', ')
  return (
    <div className={`mini-dist ${className}`} role="img" aria-label={total ? label : 'No screened resumes yet'}>
      {total > 0 && order.map(([b, cls]) => (counts?.[b] ? <span key={b} className={cls} style={{ width: `${(counts[b] / total) * 100}%` }} title={`${b}: ${counts[b]}`} /> : null))}
    </div>
  )
}
