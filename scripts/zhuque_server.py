#!/usr/bin/env python3
"""本机朱雀检测口。VPS 没有国内浏览器，检测只在这台能打开 matrix.tencent.com 的机器上跑。

用法（本机）:
  python3 scripts/zhuque_server.py          # 127.0.0.1:8765
  python3 scripts/zhuque_server.py --bind 0.0.0.0 --port 8765

VPS 要自动测，先从本机打一条反向隧道，再设环境变量:
  ssh -N -R 8765:127.0.0.1:8765 vps
  # 在 VPS:
  ZHUQUE_URL=http://127.0.0.1:8765/detect scripts/zhuque_check.sh /tmp/plain.txt

POST /detect
  body: 纯文本，或 JSON {"text": "..."}
  返回: RESULT: 人工创作特征显著|较强|较弱
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECK = HERE / "zhuque_check.sh"


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
        env = os.environ.copy()
        env.pop("ZHUQUE_URL", None)
        try:
            proc = subprocess.run(
                ["bash", str(CHECK), path],
                capture_output=True,
                text=True,
                env=env,
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
