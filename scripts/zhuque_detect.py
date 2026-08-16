#!/usr/bin/env python3
"""朱雀检测（Playwright）。给 tx / 本机用，不依赖 ego-browser。

用法: python3 zhuque_detect.py <正文纯文本.txt>
输出: RESULT: 人工创作特征显著|较强|较弱
退出: 0 成功 / 2 失败 / 3 验证码 / 4 超时
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

URL = "https://matrix.tencent.com/ai-detect/"


def _state(page) -> dict:
    return page.evaluate(
        """() => {
      const cards = [...document.querySelectorAll('.el-alert, .rst')]
        .map(x => (x.innerText || '').trim())
        .filter(Boolean);
      const joined = cards.join('\\n');
      const m = joined.match(/人工创作特征(显著|较强|较弱)/);
      const btn = [...document.querySelectorAll('button')].find(x =>
        x.innerText.includes('立即检测') || x.innerText.includes('已用完'));
      const cap = document.querySelector('iframe[src*="captcha"], [id*=tcaptcha]');
      let captcha = false;
      if (cap) {
        const r = cap.getBoundingClientRect();
        captcha = r.width > 80 && r.height > 80 && getComputedStyle(cap).visibility !== 'hidden';
      }
      return {
        result: m ? m[0] : '',
        btn: btn ? btn.innerText.trim() : '',
        captcha,
      };
    }"""
    )


def detect_text(text: str) -> str:
    from playwright.sync_api import sync_playwright

    text = text.strip()
    if len(text) < 350:
        raise SystemExit("FAIL: 文本需 >350 字")

    with sync_playwright() as p:
        args = ["--disable-dev-shm-usage", "--no-sandbox"]
        try:
            browser = p.chromium.launch(headless=True, args=args)
        except Exception:
            browser = None
            for cand in (
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path.home() / "Library/Caches/ms-playwright/chromium-1169/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
                Path.home() / "Library/Caches/ms-playwright/chromium-1208/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
                Path("/root/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome"),
                Path.home() / ".cache/ms-playwright/chromium-1208/chrome-linux64/chrome",
            ):
                if cand.exists():
                    browser = p.chromium.launch(
                        headless=True, args=args, executable_path=str(cand)
                    )
                    break
            if browser is None:
                raise SystemExit("FAIL: 找不到 Playwright Chromium")
        page = browser.new_page(locale="zh-CN", viewport={"width": 1280, "height": 900})
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.evaluate(
            """() => {
          try { localStorage.clear(); sessionStorage.clear(); } catch (e) {}
          document.cookie.split(';').forEach(c => {
            document.cookie = c.replace(/^ +/, '').replace(/=.*/, '=;expires=' + new Date().toUTCString() + ';path=/');
          });
        }"""
        )
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)

        page.evaluate(
            """() => {
          const b = [...document.querySelectorAll('button')].find(x => x.innerText.trim() === '清空');
          if (b) b.click();
        }"""
        )
        page.wait_for_timeout(600)
        filled = page.evaluate(
            """(text) => {
          const ta = document.querySelector('textarea');
          if (!ta) return 'no-textarea';
          const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
          setter.call(ta, text);
          ta.dispatchEvent(new Event('input', { bubbles: true }));
          return 'filled ' + ta.value.length;
        }""",
            text,
        )
        if str(filled).startswith("no-"):
            browser.close()
            raise SystemExit("FAIL: 输入框未就绪")

        clicked = page.evaluate(
            """() => {
          const b = [...document.querySelectorAll('button')].find(x => x.innerText.includes('立即检测'));
          if (!b) return 'no-btn';
          if (b.disabled) return 'disabled:' + b.innerText;
          b.click();
          return 'clicked';
        }"""
        )
        if clicked != "clicked":
            browser.close()
            raise SystemExit("FAIL: " + clicked)

        shot_dir = Path("/tmp/zhuque-shots")
        shot_dir.mkdir(exist_ok=True)
        for i in range(28):
            page.wait_for_timeout(2000)
            st = _state(page)
            if st.get("result"):
                result = st["result"]
                browser.close()
                return result
            if st.get("captcha") and i >= 2:
                shot = shot_dir / f"captcha-{int(time.time())}.png"
                page.screenshot(path=str(shot), full_page=True)
                browser.close()
                raise SystemExit(f"CAPTCHA: 弹了图片验证码，截图 {shot}，点掉后重跑")
        shot = shot_dir / f"timeout-{int(time.time())}.png"
        page.screenshot(path=str(shot), full_page=True)
        browser.close()
        raise SystemExit(f"TIMEOUT: 75 秒未出结果，截图 {shot}")


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: zhuque_detect.py <正文纯文本.txt>", file=sys.stderr)
        raise SystemExit(2)
    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")
    try:
        result = detect_text(text)
    except SystemExit as e:
        msg = str(e)
        print(msg)
        if msg.startswith("CAPTCHA"):
            raise SystemExit(3)
        if msg.startswith("TIMEOUT"):
            raise SystemExit(4)
        raise SystemExit(2)
    print("RESULT: " + result)


if __name__ == "__main__":
    main()
