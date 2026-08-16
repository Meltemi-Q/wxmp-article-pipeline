#!/usr/bin/env bash
# 朱雀 AI 检测一条命令版
#
# 用法: zhuque_check.sh <正文纯文本.txt>
# 输出: RESULT: 人工创作特征显著 / 较强 / 较弱
#
# 路由:
# 1) 设了 ZHUQUE_URL → POST
# 2) 本机 127.0.0.1:8765/health 通 → 视为隧道已打到 tx，POST 过去
# 3) 本机有 Playwright 且能打开 matrix.tencent.com → python3 zhuque_detect.py
# 4) 本机有 ego-browser 且能打开 matrix → 旧浏览器路径
# 5) 否则 SKIP，exit 10。写稿继续
#
# 固定拓扑: tx 跑 zhuque_server.py；VPS 打
#   ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 tx
# 公网 22 不通，Host tx 走 Tailscale 100.102.105.22
set -euo pipefail

txt="${1:?用法: zhuque_check.sh <正文纯文本.txt>}"
here="$(cd "$(dirname "$0")" && pwd)"

if [[ -z "${ZHUQUE_URL:-}" ]]; then
  if curl -sf --max-time 2 http://127.0.0.1:8765/health >/dev/null 2>&1; then
    ZHUQUE_URL="http://127.0.0.1:8765/detect"
  fi
fi

if [[ -n "${ZHUQUE_URL:-}" ]]; then
  echo "ZHUQUE: 走远端检测口 $ZHUQUE_URL"
  curl -sS --max-time 180 -X POST --data-binary @"$txt" "$ZHUQUE_URL"
  exit $?
fi

if curl -sI --connect-timeout 6 https://matrix.tencent.com/ai-detect/ >/dev/null 2>&1; then
  if python3 -c "from playwright.sync_api import sync_playwright" >/dev/null 2>&1; then
    echo "ZHUQUE: 本机 Playwright"
    exec python3 "$here/zhuque_detect.py" "$txt"
  fi
  if command -v ego-browser >/dev/null 2>&1; then
    echo "ZHUQUE: 本机 ego-browser"
    cp "$txt" /tmp/zhuque-input.txt
    exec ego-browser nodejs <<'EOF'
const fs = await import('node:fs')
const task = await useOrCreateTaskSpace('zhuque ai detect')

await openOrReuseTab('https://matrix.tencent.com/ai-detect/', { wait: true, timeout: 30 })
await js(String.raw`(() => { try { localStorage.clear(); sessionStorage.clear(); } catch(e){}; document.cookie.split(';').forEach(c => { document.cookie = c.replace(/^ +/, '').replace(/=.*/, '=;expires=' + new Date().toUTCString() + ';path=/'); }); return 'ok' })()`)
await gotoAndWait('https://matrix.tencent.com/ai-detect/', { timeout: 30 })
await wait(3)

await js(String.raw`(() => { const b = [...document.querySelectorAll('button')].find(x => x.innerText.trim() === '清空'); if (b) b.click(); return 'ok' })()`)
await wait(2)

const filled = await js(String.raw`(() => {
  const ta = document.querySelector('textarea')
  if (!ta) return 'no-textarea'
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set
  setter.call(ta, ${JSON.stringify((await import('node:fs')).readFileSync('/tmp/zhuque-input.txt', 'utf-8'))})
  ta.dispatchEvent(new Event('input', { bubbles: true }))
  return 'filled ' + ta.value.length
})()`)
if (String(filled).startsWith('no-')) { cliLog('FAIL: 输入框未就绪'); process.exit(2) }

const st = await js(String.raw`(() => { const b = [...document.querySelectorAll('button')].find(x => x.innerText.includes('立即检测')); if (!b || b.disabled) return 'unavailable:' + (b ? b.innerText : 'none'); b.click(); return 'clicked' })()`)
if (st !== 'clicked') { cliLog('FAIL: ' + st); process.exit(2) }

for (let i = 0; i < 25; i++) {
  await wait(3)
  const r = await js(String.raw`(() => {
    const cards = [...document.querySelectorAll('.el-alert, .rst')].map(x => x.innerText).join('\n')
    const m = cards.match(/人工创作特征(显著|较强|较弱)/)
    return m ? m[0] : ''
  })()`)
  if (r) { cliLog('RESULT: ' + r); process.exit(0) }
  const cap = await js(String.raw`(() => { const c = document.querySelector('iframe[src*="captcha"], [id*=tcaptcha]'); if (!c) return false; const r = c.getBoundingClientRect(); return r.width > 80 && r.height > 80 && getComputedStyle(c).visibility !== 'hidden' })()`)
  if (cap && i > 2) {
    const shot = await captureScreenshot()
    cliLog('CAPTCHA: 弹了图片验证码，截图 ' + JSON.stringify(shot) + '，人工点掉后重跑本命令')
    process.exit(3)
  }
}
cliLog('TIMEOUT: 75 秒未出结果')
process.exit(4)
EOF
  fi
fi

echo "SKIP: 这边打不开朱雀，也没有到 tx 的 8765 隧道。"
echo "HINT: tx 上先跑 python3 scripts/zhuque_server.py"
echo "HINT: VPS 打 ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 tx   # Host tx = Tailscale 100.102.105.22"
exit 10
