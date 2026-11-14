// 服务控制台。无框架、无构建：状态和日志靠轮询，动作走 POST。
const TOKEN = document.querySelector('meta[name=console-token]').content
const el = (id) => document.getElementById(id)

const state = { mode: '', selected: '', logs: '', busy: false, data: null }

const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])

// starting 是 healthcheck 宽限期，用黄色，别当故障
const tone = (s) => (!s.running ? 'off' : s.health === 'starting' ? 'warn' : s.healthy ? 'ok' : 'bad')

function toast(text, bad = false) {
  const bar = el('snack')
  bar.textContent = text
  bar.style.background = bad ? 'var(--md-error)' : ''
  bar.style.color = bad ? 'var(--md-on-error)' : ''
  bar.hidden = false
  clearTimeout(toast.timer)
  toast.timer = setTimeout(() => (bar.hidden = true), bad ? 6000 : 3200)
}

function ask(title, body) {
  const dlg = el('confirm')
  el('confirm-title').textContent = title
  el('confirm-body').textContent = body
  dlg.showModal()
  return new Promise((resolve) => {
    const done = (answer) => {
      dlg.close()
      resolve(answer)
    }
    dlg.onclick = (e) => {
      const btn = e.target.closest('[data-answer]')
      if (btn) done(btn.dataset.answer === '1')
    }
    dlg.oncancel = (e) => {
      e.preventDefault()
      done(false)
    }
  })
}

// ---------------------------------------------------------------- 渲染

function renderBanner(data) {
  const box = el('banner')
  if (data.error) {
    box.innerHTML = `<div class="banner"><span class="ms-icon">&#xf8b6;</span><div>${esc(data.error)}。可以手动跑：<code>${esc(data.hint)}</code></div></div>`
    return
  }
  const missing = (data.deps || []).filter((d) => !d.running).map((d) => d.name)
  box.innerHTML = missing.length
    ? `<div class="banner banner--info"><div>原生模式要的 ${esc(missing.join('、'))} 还没起来。<button type="button" class="md-btn md-btn--text" data-act="start_deps" style="height:26px;padding:0 8px">只起这几个容器</button></div></div>`
    : ''
}

function renderList(data) {
  const list = el('services')
  if (!data.services.length) {
    list.innerHTML = '<li class="md-muted" style="padding:16px 12px">没有服务</li>'
    return
  }
  list.innerHTML = data.services
    .map((s) => {
      const d = 'dot--' + tone(s)
      const hs = s.health === 'starting' ? '检查中' : s.health && s.health !== 'healthy' ? s.health : ''
      const sub = [s.label !== s.name ? s.name : '', s.ports || s.note, hs]
        .filter(Boolean)
        .join('，')
      const verb = s.running ? 'stop' : 'start'
      return `<li class="svc" role="option" tabindex="0" data-service="${esc(s.name)}" aria-selected="${state.selected === s.name}">
        <span class="dot ${d}" title="${esc(s.state)}"></span>
        <div><div class="svc-name">${esc(s.label)}</div><div class="svc-sub">${esc(sub || s.state)}</div></div>
        <div class="svc-actions">
          <button type="button" class="md-btn md-btn--text" data-act="${verb}" data-service="${esc(s.name)}">${s.running ? '停止' : '启动'}</button>
        </div>
      </li>`
    })
    .join('')
}

function renderDetail(data) {
  const box = el('detail')
  const s = data.services.find((x) => x.name === state.selected)
  if (!s) {
    box.className = 'detail-empty md-muted'
    box.textContent = '选一个服务看详情'
    el('log').textContent = ''
    el('log-meta').textContent = '最近 200 行'
    return
  }
  const stateText = { running: '在跑', starting: '正在启动', stopped: '已停止', absent: '还没创建' }[s.state] || s.state
  const rows = [
    ['状态', stateText],
    ['健康', s.health === 'starting' ? '检查中' : s.health || (s.running ? (data.health_ok ? '接口通' : '接口不通') : '—')],
    ['端口', s.ports || '—'],
    ['容器状态', s.status || '—'],
  ]
  box.className = 'detail'
  box.innerHTML = `<h2>${esc(s.label)}</h2>
    <dl>${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>`
  el('log-meta').textContent = s.name
}

function render(data) {
  state.data = data
  el('title').textContent = data.title || '服务控制台'
  const sum = data.summary || { total: 0, running: 0, bad: 0 }
  el('summary').textContent = `${sum.running}/${sum.total} 在跑${sum.bad ? `，${sum.bad} 个不健康` : data.health_ok ? '，接口正常' : '，接口不通'}`
  el('mode-note').textContent = data.auto ? '自动识别' : '手动锁定'
  document.querySelectorAll('.seg button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === data.mode)))
  el('open-web').href = data.web_url || '#'
  renderBanner(data)
  renderList(data)
  renderDetail(data)
}

// ---------------------------------------------------------------- 取数

async function poll() {
  clearTimeout(poll.timer)
  try {
    const r = await fetch(`/api/state?mode=${encodeURIComponent(state.mode)}`)
    render(await r.json())
  } catch {
    toast('连不上控制台进程，刷新一下页面', true)
  }
  clearTimeout(poll.timer)
  poll.timer = setTimeout(poll, 3000)
}

async function pollLogs() {
  clearTimeout(pollLogs.timer)
  if (state.selected && !state.busy) {
    try {
      const r = await fetch(
        `/api/logs?service=${encodeURIComponent(state.selected)}&mode=${encodeURIComponent(state.mode)}`,
      )
      const { text } = await r.json()
      const pre = el('log')
      const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 24
      if (text !== state.logs) {
        state.logs = text
        pre.textContent = text
        if (atBottom) pre.scrollTop = pre.scrollHeight
      }
    } catch {
      /* 日志拿不到不影响状态 */
    }
  }
  clearTimeout(pollLogs.timer)
  pollLogs.timer = setTimeout(pollLogs, 2000)
}

async function act(action, service = '') {
  if (state.busy) return
  if (action === 'stop_all') {
    if (!(await ask('全部停止', '会停掉所有服务，容器和数据卷都保留。继续？'))) return
  }
  if (action === 'restart_all') {
    if (!(await ask('全部重启', '所有服务会依次重启，这段时间网页和上报会断。继续？'))) return
  }
  state.busy = true
  document.body.style.cursor = 'progress'
  try {
    const r = await fetch('/api/action', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-console-token': TOKEN },
      body: JSON.stringify({ action, service, mode: state.mode }),
    })
    const body = await r.json()
    toast(body.message || (body.ok ? '完成' : '失败'), !body.ok)
  } catch (e) {
    toast('请求没发出去：' + e.message, true)
  }
  state.busy = false
  document.body.style.cursor = ''
  await poll()
  pollLogs()
}

// ---------------------------------------------------------------- 交互

el('services').addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' && e.key !== ' ') return
  const row = e.target.closest('.svc')
  if (!row || e.target.closest('button')) return
  e.preventDefault()
  row.click()
})

el('services').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-act]')
  if (btn) {
    e.stopPropagation()
    act(btn.dataset.act, btn.dataset.service)
    return
  }
  const row = e.target.closest('.svc')
  if (!row) return
  state.selected = row.dataset.service
  state.logs = ''
  // 选中态立刻生效，别等下一次轮询
  document.querySelectorAll('.svc').forEach((r) => r.setAttribute('aria-selected', String(r === row)))
  renderDetail(state.data)
  pollLogs()
})

document.querySelectorAll('.seg button').forEach((b) =>
  b.addEventListener('click', () => {
    state.mode = b.dataset.mode
    state.selected = ''
    poll()
  }),
)

el('refresh').addEventListener('click', () => {
  poll()
  pollLogs()
})

document.querySelectorAll('.footer [data-act]').forEach((b) => b.addEventListener('click', () => act(b.dataset.act)))

el('banner').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-act]')
  if (btn) act(btn.dataset.act)
  const code = e.target.closest('code')
  if (code) navigator.clipboard?.writeText(code.textContent).then(() => toast('命令已复制'))
})

const sun = '\ue518'
const moon = '\ue51c'
function paintTheme() {
  const dark = document.documentElement.dataset.theme === 'dark'
  el('theme-icon').textContent = dark ? sun : moon
  el('theme').setAttribute('aria-label', dark ? '切到亮色' : '切到暗色')
}

el('theme').addEventListener('click', () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = next
  localStorage.setItem('mt-theme', next)
  paintTheme()
})

paintTheme()
poll()
pollLogs()
