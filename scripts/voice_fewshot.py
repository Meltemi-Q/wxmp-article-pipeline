#!/usr/bin/env python3
"""从本机语料里捞跟本篇相关的口吻 few-shot。

写公众号前必跑。只提炼表达方式，不把隐私事实写进稿。
本机没有语料时打印 SKIP（exit 10），写稿继续用 personal-voice-rules。

用法:
  python3 scripts/voice_fewshot.py --query "Grok bot 过不了验证码" --n 8
  python3 scripts/voice_fewshot.py --scene moments --query "早起 播客" --n 6
  python3 scripts/voice_fewshot.py --rebuild
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

HOME = Path.home()
CORPUS = HOME / "Documents/WeChatArchive/corpus"
MOMENTS_JSONL = HOME / "Documents/yulong/pyq/output/moments_all.jsonl"
ARTICLE_ROOTS = [
    HOME / "Documents/yulong/weixin-write/archives/yulong-ai",
    Path(__file__).resolve().parents[1] / "references/archives/published",
]
CACHE_DIR = CORPUS / "voice_bank"
CACHE = CACHE_DIR / "index.jsonl"

COMMUNITY_ALLOW = {
    "屿龙AI陪伴群",
    "Agent 商业变现营",
    "第 2 期 Ai（Agent）商业变现营",
}
PITCH_HEAD = re.compile(
    r"^(首先|我来做个自我介绍|我先说结论|好了～|好了~|第\s*[①②③④⑤1-5]|1️⃣|2️⃣|3️⃣)"
)
PII = re.compile(
    r"(wxid_|1[3-9]\d{9}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r"|到账|转账|退回|凑\s*\d+w|\d{4,}元|银行卡)"
)
FAMILY = re.compile(r"(宝宝|爸。|妈妈|老婆|结婚证|身份证)")
TOKEN_RE = re.compile(r"[A-Za-z]{2,}|\d+")
HAN_RE = re.compile(r"[\u4e00-\u9fff]+")
SKIP = 10


def skip(msg: str) -> int:
    print(f"SKIP: {msg}", file=sys.stderr)
    return SKIP


def norm(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def tokens(text: str) -> set[str]:
    out = {m.group(0).lower() for m in TOKEN_RE.finditer(text or "")}
    for block in HAN_RE.findall(text or ""):
        if len(block) >= 2:
            out.update(block[i : i + 2] for i in range(len(block) - 1))
        if len(block) >= 3:
            out.update(block[i : i + 3] for i in range(len(block) - 2))
    return out


def safe_text(text: str) -> bool:
    if not text or PII.search(text) or FAMILY.search(text):
        return False
    if "@" in text or "wxid" in text:
        return False
    return True


def source_stamp() -> str:
    parts = []
    for p in [CORPUS / "my_corpus_natural.jsonl", MOMENTS_JSONL]:
        if p.exists():
            st = p.stat()
            parts.append(f"{p}:{st.st_mtime_ns}:{st.st_size}")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def load_cache() -> list[dict] | None:
    meta = CACHE_DIR / "meta.json"
    if not CACHE.exists() or not meta.exists():
        return None
    try:
        info = json.loads(meta.read_text())
        if info.get("stamp") != source_stamp():
            return None
        rows = []
        with CACHE.open() as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows
    except Exception:
        return None


def add_row(rows: list[dict], scene: str, year: int | str, text: str) -> None:
    text = norm(text)
    if not safe_text(text):
        return
    n = len(text)
    if n < 12 or n > 280:
        return
    rows.append({"scene": scene, "year": int(year) if str(year).isdigit() else 0, "n": n, "text": text})


def build_index() -> list[dict]:
    rows: list[dict] = []

    natural = CORPUS / "my_corpus_natural.jsonl"
    if natural.exists():
        with natural.open() as f:
            for line in f:
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chat = o.get("chat") or ""
                text = o.get("text") or ""
                if chat not in COMMUNITY_ALLOW:
                    continue
                scene = "community_pitch" if PITCH_HEAD.search(text.strip()) else "community_reply"
                year = 2026
                t = o.get("t")
                if isinstance(t, int) and t > 1_000_000_000:
                    year = 1970 + int(t) // 31557600
                add_row(rows, scene, year, text)

    if MOMENTS_JSONL.exists():
        with MOMENTS_JSONL.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = o.get("text") or ""
                year = o.get("year") or 0
                add_row(rows, "moments", year, text)

    for root in ARTICLE_ROOTS:
        if not root.exists():
            continue
        for md in root.rglob("*.md"):
            if md.name not in {"article.md", "content.md", "published.md"}:
                continue
            body = md.read_text(encoding="utf-8", errors="replace")
            year = 2026
            m = re.search(r"20\d{2}", md.as_posix())
            if m:
                year = int(m.group(0))
            for para in re.split(r"\n+", body):
                s = para.strip()
                if not s or s.startswith(("#", "!", "作者", "<", "---", "相关文章", "我是宇龙")):
                    continue
                if s.startswith("[") and "](" in s:
                    continue
                add_row(rows, "article", year, s)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with CACHE.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (CACHE_DIR / "meta.json").write_text(
        json.dumps({"stamp": source_stamp(), "n": len(rows)}, ensure_ascii=False, indent=2)
    )
    return rows


def scene_set(name: str) -> set[str]:
    if name == "article":
        return {"moments", "community_reply", "article"}
    if name == "moments":
        return {"moments"}
    if name == "community":
        return {"community_reply", "community_pitch"}
    if name == "all":
        return {"moments", "community_reply", "community_pitch", "article"}
    return {name}


def score(row: dict, q_tokens: set[str]) -> float:
    t_tokens = tokens(row["text"])
    if not q_tokens:
        return 0.0
    overlap = len(q_tokens & t_tokens)
    if overlap == 0:
        return 0.0
    boost = {"moments": 1.15, "community_reply": 1.1, "article": 1.05, "community_pitch": 0.7}.get(
        row["scene"], 1.0
    )
    recency = 1.0 + min(max(row.get("year", 0) - 2023, 0), 3) * 0.05
    return overlap * boost * recency / (1.0 + row["n"] / 180.0)


ORAL = re.compile(r"(哈哈|好嘛|咔咔|哎|嗐|666|挺香|就这|弄好|成了|咱们|这家伙|安排|嘎嘎|～|没毛病|说白了)")


def retrieve(rows: list[dict], query: str, scene: str, n: int) -> list[dict]:
    allowed = scene_set(scene)
    cand = [r for r in rows if r["scene"] in allowed]
    q_tokens = tokens(query)
    ranked = []
    seen = set()
    for row in cand:
        key = row["text"][:40]
        if key in seen:
            continue
        s = score(row, q_tokens)
        if s <= 0:
            continue
        seen.add(key)
        ranked.append((s, row))
    ranked.sort(key=lambda x: x[0], reverse=True)
    hits = [r for _, r in ranked[:n]]
    if hits:
        return hits
    fallback = []
    for row in cand:
        key = row["text"][:40]
        if key in seen or not ORAL.search(row["text"]):
            continue
        if row["n"] > 160:
            continue
        seen.add(key)
        recency = row.get("year", 0)
        fallback.append((recency, -row["n"], row))
    fallback.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [r for _, _, r in fallback[:n]]


def main() -> int:
    ap = argparse.ArgumentParser(description="从本机语料捞口吻 few-shot")
    ap.add_argument("--query", default="", help="本篇主题/关键动作，用来对齐场景")
    ap.add_argument("--scene", default="article", choices=["article", "moments", "community", "all"])
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not CORPUS.exists() and not MOMENTS_JSONL.exists():
        return skip("本机没有 WeChatArchive / pyq 语料")

    rows = None if args.rebuild else load_cache()
    if rows is None:
        rows = build_index()
    if not rows:
        return skip("语料在，但筛完没有可公开用的句子")

    if not args.query:
        counts = Counter(r["scene"] for r in rows)
        print("voice bank ready:", dict(counts), "total", len(rows))
        print("再带 --query 才能捞 few-shot")
        return 0

    hits = retrieve(rows, args.query, args.scene, args.n)
    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return 0

    print(f"# 口吻 few-shot · scene={args.scene} · query={args.query}")
    print()
    print("只学句式和口气，不搬原句里的事实、人名、数字、地点。")
    print()
    if not hits:
        print("没有对上关键词。换个更口语的 query，或 `--scene all`。")
        return 0
    for i, row in enumerate(hits, 1):
        one = row["text"].replace("\n", " / ")
        print(f"{i}. [{row['scene']}/{row['year']}/{row['n']}字] {one}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
