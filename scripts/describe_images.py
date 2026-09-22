#!/usr/bin/env python3
"""裸调 Gemini 看图：iherai 中转，并发 N 张，测速用。"""
import base64, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import urllib.request

BASE = os.environ.get("IHERAI_GEMINI_BASE_URL", "https://api.iherai.com/v1beta")
KEY = os.environ.get("IHERAI_API_KEY") or os.environ["GEMINI_API_KEY"]
MODEL = os.environ.get("IHERAI_FLASH_MODEL", "gemini-3.8-flash-high")
PROMPT = sys.argv[1] if len(sys.argv) > 1 else "一句话描述画面内容，15字内"
imgs = [Path(p) for p in sys.argv[2:]]


def one(p: Path):
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    body = {"contents": [{"parts": [{"text": PROMPT}, {"inline_data": {"mime_type": mime, "data": base64.b64encode(p.read_bytes()).decode()}}]}]}
    req = urllib.request.Request(
        f"{BASE}/models/{MODEL}:generateContent",
        data=json.dumps(body).encode(),
        headers={"x-goog-api-key": KEY, "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"},
    )
    t0 = time.time()
    d = json.load(urllib.request.urlopen(req, timeout=120))
    dt = time.time() - t0
    txt = "".join(pt.get("text", "") for pt in d["candidates"][0]["content"]["parts"]).strip()
    return p.name, txt, dt


t0 = time.time()
with ThreadPoolExecutor(max_workers=min(8, len(imgs))) as pool:
    for name, txt, dt in pool.map(one, imgs):
        print(f"{name}: {txt}  ({dt:.1f}s)")
print(f"\n{len(imgs)} 张图总耗时 {time.time()-t0:.1f}s")
