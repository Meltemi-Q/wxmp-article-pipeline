#!/usr/bin/env python3
"""飞书 Docx 一键落地：lark-cli API 直出 Markdown + 图片，替代 ego-browser 抓取。

为什么存在：浏览器链路要开 ego-browser、等 networkidle、跑 extract.js、
再逐张下临时签名图，全程分钟级且偶发 PageNavigationTimeout。本脚本走
lark-cli OpenAPI，整篇导出 + 图片并发下载通常 <30s，且无虚拟滚动漏图。

依赖：`lark-cli` 已安装并完成用户授权（需要 docx:document:readonly scope）。
首次报 scope 错误时执行 `lark-cli auth login` 重新授权，或退回
ego-browser + feishu-doc-export/extract.js 兜底链路。

用法：

  python3 scripts/feishu_pull.py \
    --doc "https://my.feishu.cn/docx/XXXX" \
    --outdir drafts/2026-09-19-topic/

产物：outdir/article.md（图片引用已改写为 images/image-XXX.*）、
outdir/images/、stdout 打印 JSON 摘要。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
ATTR_RE = re.compile(r'(\w[\w-]*)\s*=\s*"([^"]*)"')
MD_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")

MAGIC = [
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF8", ".gif"),
    (b"RIFF", ".webp"),  # 需再看 8-12 字节，下面单独校验
]


def run_lark(args: list[str]) -> dict:
    proc = subprocess.run(
        ["lark-cli", *args],
        capture_output=True,
        text=True,
        timeout=120,
    )
    # lark-cli 成功时 JSON 走 stdout，失败时部分版本把错误 JSON 打到 stderr
    data = None
    for stream in (proc.stdout, proc.stderr):
        try:
            data = json.loads(stream)
            break
        except (json.JSONDecodeError, TypeError):
            continue
    if data is None:
        print(f"❌ lark-cli 输出非 JSON: {proc.stdout[:500]}\n{proc.stderr[:500]}")
        sys.exit(2)
    if not data.get("ok"):
        err = data.get("error", {})
        print(f"❌ lark-cli 失败 [{err.get('subtype', err.get('type', '?'))}]: {err.get('message', '')}")
        if err.get("subtype") in ("token_missing", "app_scope_not_applied") or "scope" in str(err):
            print("💡 一次性修复: lark-cli auth login （勾选 docx 只读 scope）；"
                  "或退回 ego-browser + feishu-doc-export/extract.js 兜底链路")
        sys.exit(2)
    return data


def fetch_doc(doc: str, identity: str, doc_format: str) -> str:
    data = run_lark([
        "docs", "+fetch",
        "--as", identity,
        "--doc", doc,
        "--doc-format", doc_format,
        "--scope", "full",
    ])
    return data["data"]["document"]["content"]


def sniff_ext(blob: bytes) -> str:
    for magic, ext in MAGIC:
        if blob.startswith(magic):
            if ext == ".webp" and blob[8:12] != b"WEBP":
                continue
            return ext
    return ".png"


def fetch_image(item: dict, outdir: Path, identity: str) -> dict:
    """优先直 GET img url；无 url 走 lark-cli media-download。"""
    idx, token, url = item["idx"], item.get("token"), item.get("url")
    blob = b""
    if url:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                blob = resp.read()
        except Exception:
            blob = b""
    if not blob and token:
        tmp = outdir / f".dl-{idx}"
        proc = subprocess.run(
            ["lark-cli", "docs", "+media-download", "--as", identity,
             "--token", token, "--output", str(tmp)],
            capture_output=True, text=True, timeout=120,
        )
        cand = tmp if tmp.exists() else next(outdir.glob(f".dl-{idx}.*"), None)
        if proc.returncode == 0 and cand:
            blob = cand.read_bytes()
            cand.unlink()
    if not blob:
        return {**item, "ok": False, "file": None}
    ext = sniff_ext(blob)
    name = f"image-{idx:03d}{ext}"
    (outdir / name).write_bytes(blob)
    return {**item, "ok": True, "file": f"images/{name}", "bytes": len(blob)}


def main() -> int:
    parser = argparse.ArgumentParser(description="lark-cli API 直导飞书文档为本地 Markdown+图片")
    parser.add_argument("--doc", required=True, help="飞书文档 URL 或 token")
    parser.add_argument("--outdir", required=True, help="输出目录（article.md + images/）")
    parser.add_argument("--as", dest="identity", default="user", choices=["user", "bot"])
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    outdir = Path(args.outdir)
    imgdir = outdir / "images"
    imgdir.mkdir(parents=True, exist_ok=True)

    xml = fetch_doc(args.doc, args.identity, "xml")
    imgs: list[dict] = []
    for i, m in enumerate(IMG_TAG_RE.finditer(xml), 1):
        attrs = dict(ATTR_RE.findall(m.group(0)))
        imgs.append({"idx": i, "token": attrs.get("token"), "url": attrs.get("url")})

    md = fetch_doc(args.doc, args.identity, "markdown")

    results: list[dict] = []
    if imgs:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(lambda it: fetch_image(it, imgdir, args.identity), imgs))

    ok_files = [r["file"] for r in results if r["ok"]]
    # 把 markdown 里的图片语法按文档顺序替换为本地相对路径
    it = iter(ok_files)

    def _sub(m: re.Match) -> str:
        f = next(it, None)
        return f"![]({f})" if f else m.group(0)

    md_out = MD_IMG_RE.sub(_sub, md)
    leftover = len(ok_files) - len(MD_IMG_RE.findall(md))
    (outdir / "article.md").write_text(md_out, encoding="utf-8")

    summary = {
        "doc": args.doc,
        "outdir": str(outdir),
        "images_found": len(imgs),
        "images_saved": len(ok_files),
        "images_failed": [r["idx"] for r in results if not r["ok"]],
        "md_image_refs_replaced": len(MD_IMG_RE.findall(md)),
        "images_without_md_ref": max(leftover, 0),
        "article_md": str(outdir / "article.md"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["images_failed"]:
        print("⚠️ 部分图片下载失败，可换 --as bot 重试或走 ego-browser 兜底")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
