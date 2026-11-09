// 前端冒烟：逐页打开，断言页面标题、关键区块、以及控制台没有报错。
// 用系统 Chrome（channel: 'chrome'），不额外下载浏览器。
//   node tests/smoke.mjs http://127.0.0.1:8001
import { chromium } from 'playwright'

const base = process.argv[2] || 'http://127.0.0.1:8001'
const pages = [
  ['#/', '总览', '数据流'],
  ['#/devices', '设备', '最近批次'],
  ['#/analysis', '分析', '时段热力图'],
  ['#/access', '接入', '发现的设备'],
  ['#/settings', '设置', '发件箱'],
]

let failed = 0
const browser = await chromium.launch({ channel: 'chrome', args: ['--no-sandbox'] })
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, ignoreHTTPSErrors: true })

for (const [hash, title, block] of pages) {
  const page = await ctx.newPage()
  const errors = []
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(String(e)))
  try {
    await page.goto(`${base}/${hash}`, { waitUntil: 'networkidle', timeout: 30000 })
    const h1 = await page.locator('h1').first().textContent()
    const hasBlock = await page.getByText(block, { exact: false }).first().isVisible().catch(() => false)
    const bad = []
    if (!h1?.includes(title)) bad.push(`标题是「${h1?.trim()}」，期望「${title}」`)
    if (!hasBlock) bad.push(`没有找到区块「${block}」`)
    if (errors.length) bad.push(`控制台报错：${errors[0].slice(0, 120)}`)
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
