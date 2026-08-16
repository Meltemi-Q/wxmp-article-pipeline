#!/usr/bin/env python3
"""朱雀交互检测口：常驻浏览器，验证码可截图+点选。只绑 127.0.0.1。"""
from __future__ import annotations

import json
import queue
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

URL = "https://matrix.tencent.com/ai-detect/"
SHOT = Path("/tmp/zhuque-captcha.png")
JOBS: queue.Queue = queue.Queue()
STATE: dict[str, Any] = {"page": None, "browser": None}


def _vm_js(body: str) -> str:
    return f"""() => {{
      const btn = [...document.querySelectorAll('button')]
        .find(x => /已用完|立即检测|检测中/.test(x.innerText));
      let vm = btn && btn.__vue__;
      while (vm && !('aiGenTxtRemainingCount' in (vm.$data || {{}}))) vm = vm.$parent;
      if (!vm) return null;
      return ({body});
    }}"""


def _ensure_page():
    if STATE.get("page"):
        return STATE["page"]
    pw = sync_playwright().start()
    STATE["pw"] = pw
    browser = pw.chromium.launch(
        headless=True,
        args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(locale="zh-CN", viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)
    STATE["browser"] = browser
    STATE["page"] = page
    return page


def _fresh_fp(page) -> str:
    fp = secrets.token_hex(16)
    page.evaluate(
        """(fp) => {
          localStorage.setItem('fp', fp);
          localStorage.setItem('aiGenTxtRemainingCount', '5');
          localStorage.setItem('aiGenTxtLastCheckDate', new Date().toLocaleDateString());
        }""",
        fp,
    )
    page.evaluate(
        _vm_js(
            """(() => {
              vm.aiGenTxtRemainingCount = 5;
              vm.remainingRequests = 5;
              vm.processing = false;
              vm.pendingMessage = null;
              vm.data = {};
              try { if (vm.websock) vm.websock.close(); } catch (e) {}
              vm.wsConnected = false;
              vm.init = false;
              if (vm.initWebSocket) vm.initWebSocket();
              return true;
            })()"""
        )
    )
    page.wait_for_timeout(800)
    return fp


def _state(page) -> dict:
    return page.evaluate(
        """() => {
          const cards = [...document.querySelectorAll('.el-alert, .rst')]
            .map(x => (x.innerText || '').trim()).filter(Boolean).join('\\n');
          const m = cards.match(/人工创作特征(显著|较强|较弱)/);
          const btn = [...document.querySelectorAll('button')]
            .find(x => /立即检测|已用完|检测中/.test(x.innerText));
          const cap = document.querySelector('iframe[src*="gtimg"], iframe[src*="captcha"]');
          let captcha = null;
          if (cap) {
            const r = cap.getBoundingClientRect();
            captcha = {x: r.x, y: r.y, w: r.width, h: r.height, vis: r.width > 80 && r.y > -100};
          }
          let vm = btn && btn.__vue__;
          while (vm && !('aiGenTxtRemainingCount' in (vm.$data || {}))) vm = vm.$parent;
          return {
            result: m ? m[0] : '',
            cards: cards.slice(0, 240),
            btn: btn ? btn.innerText.trim() : '',
            captcha,
            remain: localStorage.getItem('aiGenTxtRemainingCount'),
            vueRemain: vm ? vm.aiGenTxtRemainingCount : null,
            processing: vm ? vm.processing : null,
            dataStatus: vm && vm.data ? vm.data.status : null,
            timeout: document.body.innerText.includes('服务超时'),
          };
        }"""
    )


def _captcha_text(page) -> str:
    for fr in page.frames:
        if "gtimg" in fr.url or "captcha" in fr.url:
            try:
                return fr.evaluate("() => document.body.innerText").strip()[:300]
            except Exception:
                return ""
    return ""


def _shot(page) -> bool:
    st = _state(page)
    cap = st.get("captcha") or {}
    if not cap.get("vis"):
        return False
    page.screenshot(
        path=str(SHOT),
        clip={"x": cap["x"], "y": cap["y"], "width": cap["w"], "height": cap["h"]},
    )
    return True


def _click_tile(page, row: int, col: int) -> None:
    st = _state(page)
    cap = st.get("captcha") or {}
    if not cap.get("vis"):
        raise RuntimeError("no captcha")
    tile_w, tile_h = 340 / 3, 243 / 2
    x = cap["x"] + 10 + tile_w * col + tile_w / 2
    y = cap["y"] + 73.5 + tile_h * row + tile_h / 2
    page.mouse.click(x, y)


def _confirm(page) -> None:
    st = _state(page)
    cap = st.get("captcha") or {}
    if not cap.get("vis"):
        raise RuntimeError("no captcha")
    page.mouse.click(cap["x"] + 305, cap["y"] + 337)


def handle(cmd: str, payload: dict) -> dict:
    page = _ensure_page()
    if cmd == "health":
        return {"ok": True}
    if cmd == "state":
        st = _state(page)
        st["capText"] = _captcha_text(page)
        return st
    if cmd == "reset":
        fp = _fresh_fp(page)
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1200)
        fp = _fresh_fp(page)
        return {"fp": fp, **_state(page)}
    if cmd == "fill":
        text = (payload.get("text") or "").strip()
        page.evaluate(
            """() => {
              const b = [...document.querySelectorAll('button')].find(x => x.innerText.trim() === '清空');
              if (b) b.click();
            }"""
        )
        page.wait_for_timeout(250)
        page.evaluate(
            """(t) => {
              const ta = document.querySelector('textarea');
              const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
              setter.call(ta, t);
              ta.dispatchEvent(new Event('input', { bubbles: true }));
              const btn = [...document.querySelectorAll('button')].find(x => /已用完|立即检测/.test(x.innerText));
              let vm = btn && btn.__vue__;
              while (vm && !('aiGenTxtRemainingCount' in (vm.$data || {}))) vm = vm.$parent;
              if (vm) vm.text = t;
            }""",
            text,
        )
        return {"filled": len(text), **_state(page)}
    if cmd == "submit":
        page.evaluate(
            _vm_js(
                """(() => {
                  vm.processing = false;
                  vm.aiGenTxtRemainingCount = 5;
                  vm.remainingRequests = 5;
                  const orig = vm.websocketSend.bind(vm);
                  vm.websocketSend = function () {
                    var t = this;
                    var e = JSON.stringify({text: this.text || void 0, cos: this.text ? void 0 : this.cos || void 0});
                    try {
                      this.resetInactivityTimer();
                      this.websock.send(e);
                      this.wsTimeout = setTimeout(function () {
                        if (t.processing) {
                          t.processing = false;
                          t.$message.error(t.$t('message.detectError.timeout'));
                          t.reconnect();
                        }
                      }, 90000);
                    } catch (n) {
                      this.pendingMessage = e;
                      this.reconnect();
                    }
                  };
                  vm.submit();
                  return true;
                })()"""
            )
        )
        page.wait_for_timeout(1200)
        shot = _shot(page)
        st = _state(page)
        st["capText"] = _captcha_text(page)
        st["shot"] = shot
        return st
    if cmd == "shot":
        ok = _shot(page)
        st = _state(page)
        st["capText"] = _captcha_text(page)
        st["shot"] = ok
        return st
    if cmd == "click":
        _click_tile(page, int(payload["r"]), int(payload["c"]))
        page.wait_for_timeout(200)
        return _state(page)
    if cmd == "confirm":
        _confirm(page)
        page.wait_for_timeout(1200)
        st = _state(page)
        st["capText"] = _captcha_text(page)
        if st.get("captcha", {}).get("vis"):
            _shot(page)
            st["shot"] = True
        return st
    if cmd == "poll":
        page.wait_for_timeout(int(payload.get("ms") or 1500))
        st = _state(page)
        st["capText"] = _captcha_text(page)
        if st.get("captcha", {}).get("vis"):
            _shot(page)
            st["shot"] = True
        return st
    return {"error": "unknown cmd " + cmd}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print("[zhuque-session]", fmt % args)

    def do_GET(self) -> None:
        if self.path in ("/", "/health"):
            self._json(200, {"ok": True})
            return
        if self.path == "/shot.png":
            if SHOT.exists():
                data = SHOT.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self._json(404, {"error": "no shot"})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", errors="replace") if n else "{}"
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            payload = {"text": raw}
        cmd = self.path.strip("/").split("/")[0] or payload.get("cmd") or ""
        try:
            out = call(cmd, payload)
            self._json(200, out)
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _json(self, code: int, obj: dict) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def call(cmd: str, payload: dict) -> dict:
    box: dict[str, Any] = {}
    done = threading.Event()

    def finish(ok: bool, val: Any) -> None:
        box["ok"] = ok
        box["val"] = val
        done.set()

    JOBS.put((cmd, payload, finish))
    if not done.wait(120):
        raise TimeoutError("playwright worker timeout")
    if not box.get("ok"):
        raise RuntimeError(str(box.get("val")))
    return box["val"]


def worker() -> None:
    while True:
        cmd, payload, finish = JOBS.get()
        try:
            finish(True, handle(cmd, payload))
        except Exception as e:
            finish(False, e)


def main() -> None:
    threading.Thread(target=worker, daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", 8766), Handler)
    print("zhuque session on http://127.0.0.1:8766")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
