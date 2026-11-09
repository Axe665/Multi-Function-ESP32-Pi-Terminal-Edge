// 接口封装：所有请求都走这里，错误统一抛出去由页面兜住
export async function api(path, options = {}) {
  const res = await fetch(`/api/v1${path}`, {
    headers: { 'content-type': 'application/json' },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail?.message || body.detail || body.message || detail
      if (typeof detail === 'object') detail = JSON.stringify(detail)
    } catch { /* 非 JSON 错误就用状态码文案 */ }
    throw new Error(`${res.status} ${detail}`)
  }
  return res.status === 204 ? null : res.json()
}

export const fmtNum = (v, d = 1) =>
  v === null || v === undefined || Number.isNaN(v)
    ? '—'
    : Number(v).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d })

export const fmtTime = (ms, withSeconds = false) => {
  if (!ms) return '—'
  const d = new Date(ms)
  return d.toLocaleTimeString('zh-CN', {
    hour: '2-digit', minute: '2-digit', ...(withSeconds ? { second: '2-digit' } : {}),
  })
}

export const fmtDay = (iso) => (iso || '').slice(5).replace('-', '/')
