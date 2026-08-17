#!/usr/bin/env bash
# 自托管中文 AIGC 检测。无验证码、无限额。装在 VPS。
# 用法: aigc_check.sh <正文纯文本.txt>
# 退出码: 0=pass  1=fail  2=review  10=SKIP
set -euo pipefail
txt="${1:?用法: aigc_check.sh <正文纯文本.txt>}"
here="$(cd "$(dirname "$0")" && pwd)"

run_exit() {
  local out="$1"
  printf '%s\n' "$out"
  if printf '%s' "$out" | grep -q 'gate=fail'; then
    exit 1
  fi
  if printf '%s' "$out" | grep -q 'gate=review'; then
    exit 2
  fi
  if printf '%s' "$out" | grep -q 'gate=pass'; then
    exit 0
  fi
  exit 10
}

if [[ -n "${AIGC_URL:-}" ]]; then
  run_exit "$(curl -sS --max-time 60 -X POST --data-binary @"$txt" "$AIGC_URL")"
fi

if curl -sf --max-time 2 http://127.0.0.1:8767/health >/dev/null 2>&1; then
  run_exit "$(curl -sS --max-time 60 -X POST --data-binary @"$txt" http://127.0.0.1:8767/detect)"
fi

for py in python3.12 python3; do
  if command -v "$py" >/dev/null 2>&1; then
    run_exit "$("$py" "$here/aigc_detect.py" "$txt")"
  fi
done
echo "SKIP: 没有 python3，也没有 127.0.0.1:8767"
exit 10
