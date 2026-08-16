#!/usr/bin/env bash
# 朱雀 AI 检测一条命令版（本机 ego-browser 驱动）
#
# 用法: zhuque_check.sh <正文纯文本.txt>
# 输出: RESULT: 人工创作特征显著 / 较强 / 较弱
#
# 路由（VPS 没有国内浏览器，不要在美国 IP 上硬跑）:
# 1) 设了 ZHUQUE_URL → POST 到本机检测口（见 zhuque_server.py + ssh -R 反向隧道）
# 2) 本机有 ego-browser 且能打开 matrix.tencent.com → 本地跑
# 3) 否则 SKIP，exit 10。写稿继续，过检留到本机
#
# 说明:
# - 每日 5 次额度记在浏览器站点存储里，脚本自动清存储重置，同 IP 无限测。
# - 偶发图片选择验证码（选柿子这类），脚本检测到会截图并报路径，需人工点一下再重跑。
# - 文本需 >350 字。
set -euo pipefail

txt="${1:?用法: zhuque_check.sh <正文纯文本.txt>}"
cp "$txt" /tmp/zhuque-input.txt

if [[ -n "${ZHUQUE_URL:-}" ]]; then
  echo "ZHUQUE: 走远端检测口 $ZHUQUE_URL"
  curl -sS --max-time 180 -X POST --data-binary @"$txt" "$ZHUQUE_URL"
  exit $?
fi

if ! command -v ego-browser >/dev/null 2>&1; then
  echo "SKIP: 这台机器没有 ego-browser。朱雀只在能打开 matrix.tencent.com 的本机跑。"
  echo "HINT: 本机先 python3 scripts/zhuque_server.py，再 ssh -N -R 8765:127.0.0.1:8765 vps"
  echo "HINT: VPS 设 ZHUQUE_URL=http://127.0.0.1:8765/detect 后重跑本命令"
  exit 10
fi

if ! curl -sI --connect-timeout 6 https://matrix.tencent.com/ai-detect/ >/dev/null 2>&1; then
  echo "SKIP: 打不开 matrix.tencent.com（多半是 VPS 美国 IP）。朱雀不在这边跑。"
  echo "HINT: 本机 python3 scripts/zhuque_server.py + ssh -N -R 8765:127.0.0.1:8765 vps"
  echo "HINT: VPS 设 ZHUQUE_URL=http://127.0.0.1:8765/detect"
  exit 10
fi

ego-browser nodejs <<'EOF'
const fs = await import('node:fs')
const task = await useOrCreateTaskSpace('zhuque ai detect')

await openOrReuseTab('https://matrix.tencent.com/ai-detect/', { wait: true, timeout: 30 })
// 重置额度
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
  const r = await js(String.raw`(() => { const m = document.body.innerText.match(/人工创作特征(显著|较强|较弱)/); return m ? m[0] : '' })()`)
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
