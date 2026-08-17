#!/usr/bin/env python3
"""自托管中文 AIGC 检测口。默认绑 127.0.0.1:8767，不要对公网开放。

装在 VPS（写稿机）。模型常驻内存，避免每次加载 98MB。

POST /detect
  body: 纯文本，或 JSON {"text": "..."}
  返回: RESULT: 更像人工|AI较弱|AI较强  gate=pass|fail
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import aigc_detect  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print("[aigc-server]", fmt % args)

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
        want_json = "application/json" in (self.headers.get("Accept") or "")
        if raw.lstrip().startswith("{"):
            try:
                payload = json.loads(raw)
                text = payload.get("text") or ""
                want_json = True
            except json.JSONDecodeError:
                pass
        try:
            result = aigc_detect.detect(text)
        except SystemExit as e:
            self._send(400, f"{e}\n")
            return
        if want_json:
            self._send(200, json.dumps(result, ensure_ascii=False) + "\n", "application/json")
            return
        self._send(200, aigc_detect.format_line(result) + "\n")

    def _send(self, code: int, body: str, ctype: str = "text/plain; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8767)
    p.add_argument("--model-dir")
    args = p.parse_args()
    aigc_detect.load_runtime(Path(args.model_dir) if args.model_dir else None)
    httpd = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"aigc server on http://{args.bind}:{args.port}/detect")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
