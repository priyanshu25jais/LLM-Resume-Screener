async function request(path, { method = 'GET', body, form } = {}) {
  const opts = { method, headers: {} }
  if (form) opts.body = form
  else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(`/api${path}`, opts)
  if (res.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('auth-expired'))
  if (res.status === 204) return null
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join('; ')
      : data.detail
    throw new Error(detail || `Request failed (${res.status})`)
  }
  return data
}

export const api = {
  health: () => request('/health'),
  authOptions: () => request('/auth/options'),
  me: () => request('/auth/me'),
  login: (email, password) => request('/auth/login', { method: 'POST', body: { email, password } }),
  register: (name, email, password) => request('/auth/register', { method: 'POST', body: { name, email, password } }),
  demoLogin: () => request('/auth/demo', { method: 'POST' }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  adminOverview: () => request('/admin/overview'),
  adminRecruiters: (status, q) => request(`/admin/recruiters?${new URLSearchParams({ ...(status && { status }), ...(q && { q }) })}`),
  adminAdmins: () => request('/admin/admins'),
  adminAction: (uid, action, body) => request(`/admin/accounts/${uid}/${action}`, { method: 'POST', body }),
  adminEvents: (kind, targetId) => request(`/admin/events?${new URLSearchParams({ kind, ...(targetId && { target_id: targetId }) })}`),
  reviewEvent: (id) => request(`/admin/events/${id}/review`, { method: 'POST' }),
  demos: () => request('/demo'),
  loadDemo: (key) => request(`/demo/${key}`, { method: 'POST' }),
  jobs: () => request('/jobs'),
  job: (id) => request(`/jobs/${id}`),
  createJob: (body) => request('/jobs', { method: 'POST', body }),
  updateJob: (id, body) => request(`/jobs/${id}`, { method: 'PATCH', body }),
  updateRequirements: (id, body) => request(`/jobs/${id}/requirements`, { method: 'PUT', body }),
  rescreen: (id) => request(`/jobs/${id}/rescreen`, { method: 'POST' }),
  deleteJob: (id) => request(`/jobs/${id}`, { method: 'DELETE' }),
  candidates: (id) => request(`/jobs/${id}/candidates`),
  upload: (id, files) => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    return request(`/jobs/${id}/resumes`, { method: 'POST', form })
  },
  ask: (id, question) => request(`/jobs/${id}/ask`, { method: 'POST', body: { question } }),
  exportUrl: (id) => `/api/jobs/${id}/export.csv`,
  candidate: (cid, reveal = false) => request(`/candidates/${cid}${reveal ? '?reveal=true' : ''}`),
  updateCandidate: (cid, body) => request(`/candidates/${cid}`, { method: 'PATCH', body }),
  reprocess: (cid) => request(`/candidates/${cid}/reprocess`, { method: 'POST' }),
  deleteCandidate: (cid) => request(`/candidates/${cid}`, { method: 'DELETE' }),
}

export const SIGNALS = [
  { key: 'llm', field: 'llm_score', name: 'LLM evaluation', short: 'LLM' },
  { key: 'skills', field: 'skill_score', name: 'Skill coverage', short: 'Skills' },
  { key: 'semantic', field: 'semantic_score', name: 'Semantic match', short: 'Semantic' },
  { key: 'experience', field: 'experience_score', name: 'Experience fit', short: 'Experience' },
]

export const BANDS = ['Strong Fit', 'Good Fit', 'Consider', 'Not a Fit']

export const DECISIONS = {
  pending: 'Not reviewed',
  shortlisted: 'Shortlisted',
  on_hold: 'On hold',
  rejected: 'Rejected',
}

export const skillName = (s) => s.split(' (for ')[0]

export function byWhom(label = '') {
  if (label === 'rule-based') return 'the rule-based evaluator (offline mode, no LLM key)'
  if (label.startsWith('rule-based')) return 'the rule-based evaluator'
  return label.replace(/:/, ' ')
}

export function formatTokens(n = 0) {
  if (n >= 10000) return `${(n / 1000).toFixed(1)}k`
  return n.toLocaleString('en-IN')
}

export const llmFellBack = (label = '') => label.startsWith('rule-based (')

// Server times are UTC; older rows have no timezone mark, so add one before formatting
export function formatDate(iso, withTime = false) {
  if (!iso) return '-'
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`)
  const opts = { day: 'numeric', month: 'short', year: 'numeric', ...(withTime && { hour: 'numeric', minute: '2-digit' }) }
  return d.toLocaleString('en-IN', opts)
}
