// 前端冒烟：逐页打开，断言顶栏标题、关键区块、控制台无报错、总览整屏不滚动。
// 用系统 Chrome（channel: 'chrome'），不额外下载浏览器。
//   node tests/smoke.mjs http://127.0.0.1:8001
import { chromium } from 'playwright'

const base = process.argv[2] || 'http://127.0.0.1:8001'
const pages = [
  ['#/', '总览', '待处理'],
  ['#/devices', '设备', '最近批次'],
  ['#/analysis', '分析', '时段热力图'],
  ['#/access', '接入', '证书'],
  ['#/settings', '设置', '隐私计数'],
]

let failed = 0
const browser = await chromium.launch({ channel: 'chrome', args: ['--no-sandbox'] })
const ctx = await browser.newContext({ viewport: { width: 1900, height: 1040 }, ignoreHTTPSErrors: true })

for (const [hash, title, block] of pages) {
  const page = await ctx.newPage()
  const errors = []
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(String(e)))
  try {
    // 页面每 20 s 轮询一次，networkidle 永远等不到，用 load + 等标题
    await page.goto(`${base}/${hash}`, { waitUntil: 'load', timeout: 30000 })
    await page.locator('.appbar-title').waitFor({ timeout: 15000 })
    await page.waitForTimeout(1500)
    const shown = (await page.locator('.appbar-title').textContent())?.trim()
    const hasBlock = await page.getByText(block, { exact: false }).first().isVisible().catch(() => false)
    const bad = []
    if (shown !== title) bad.push(`顶栏是「${shown}」，期望「${title}」`)
    if (!hasBlock) bad.push(`没有找到区块「${block}」`)
    if (errors.length) bad.push(`控制台报错：${errors[0].slice(0, 120)}`)
    if (hash === '#/') {
      // 1900×1040 下总览应当整屏放下，表变长才滚动
      const over = await page.evaluate(() => {
        const c = document.querySelector('.content')
        return c ? c.scrollHeight - c.clientHeight : 0
      })
      if (over > 1) bad.push(`总览纵向溢出 ${over}px`)
    }
    if (bad.length) {
      failed++
      console.log(`  [FAIL] ${hash}  ${bad.join('；')}`)
    } else {
      console.log(`  [OK]   ${hash}  ${title} / ${block}`)
    }
  } catch (e) {
    failed++
    console.log(`  [FAIL] ${hash}  ${String(e).slice(0, 140)}`)
  } finally {
    await page.close()
  }
}

await browser.close()
console.log(failed ? `\nSMOKE: ${failed} 页失败` : '\nSMOKE: 全部通过')
process.exit(failed ? 1 : 0)
