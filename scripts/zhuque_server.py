#!/usr/bin/env python3
"""朱雀检测口。默认绑 127.0.0.1:8765，只给 SSH 隧道用，不要对公网开放。

固定拓扑:
  tx  (能开 matrix.tencent.com) 跑本进程 + Playwright
  vps (美国，写稿/推草稿) 打本地转发:
      ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 tx
  公网 22 不通，Host tx 必须走 Tailscale（100.102.105.22）

POST /detect
  body: 纯文本，或 JSON {"text": "..."}
  返回: RESULT: 人工创作特征显著|较强|较弱
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DETECT = HERE / "zhuque_detect.py"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print("[zhuque-server]", fmt % args)

    def do_GET(self) -> None:
        if self.path in ("/", "/health"):
            self._send(200, "ok\n")
            return
        self._send(404, "not found\n")

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/detect":
            self._send(404, "not found\n")
            return
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", errors="replace")
        text = raw
        if raw.lstrip().startswith("{"):
            try:
                text = json.loads(raw).get("text") or ""
            except json.JSONDecodeError:
                pass
        text = text.strip()
        if len(text) < 350:
            self._send(400, "FAIL: 文本需 >350 字\n")
            return
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            proc = subprocess.run(
                [sys.executable, str(DETECT), path],
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            self._send(504, "TIMEOUT\n")
            return
        finally:
            Path(path).unlink(missing_ok=True)
        out = (proc.stdout or "") + (proc.stderr or "")
        code = 200 if proc.returncode == 0 else 502
        self._send(code, out if out.endswith("\n") else out + "\n")

    def _send(self, code: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    httpd = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"zhuque server on http://{args.bind}:{args.port}/detect")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
