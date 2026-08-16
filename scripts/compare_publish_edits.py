#!/usr/bin/env python3
"""对比「发布前草稿 content.md」和「真正发布版 published.html」，归类用户手改规律。

用法:
  # 单篇（存档目录含 content.md + published.html）
  python3 compare_publish_edits.py --archive-dir <dir>

  # 批量（archives/published/ 下所有成对目录）
  python3 compare_publish_edits.py --all [--archives-root <root>] [--json out.json]

  # 三层对比（可选加用户原稿）
  python3 compare_publish_edits.py --archive-dir <dir> --user-draft <口述稿.md>

改动分类:
  punct_only   纯标点改动（去句号、加感叹号等，文字不变）
  split        一段拆成多段（断行）
  tweak        用词微调（相似度 >= 0.6 的替换）
  rewrite      重写（相似度 < 0.6 的替换）
  added        发布版新增的句子
  removed      发布版删掉的句子
  caption_period  图注句尾句号被删
"""
from __future__ import annotations

import argparse
import difflib
import html as htmllib
import json
import re
from pathlib import Path

NOISE_LINES = {
    "预览时标签不可点",
    "微信扫一扫",
    "关注该公众号",
    "使用小程序",
    "微信扫一扫可打开此内容，",
    "使用完整服务",
    "知道了",
    "取消",
    "允许",
    "×",
    "分析",
    "视频",
    "小程序",
    "赞",
    "，轻点两下取消赞",
    "在看",
    "，轻点两下取消在看",
    "分享",
    "留言",
    "收藏",
    "听过",
    "在小说阅读器读本章",
    "去阅读",
    "在小说阅读器中沉浸阅读",
    "原创",
    "轻点两下取消赞",
    "轻点两下取消在看",
    "继续滑动看下一个",
    "轻触阅读原文",
    "向上滑动看下一个",
    "当前内容可能存在未经审核的第三方商业营销信息，请确认是否继续访问。",
}

PUNCT_STRIP = "。．.！!？?，,、；;：:…~～ 　"


def norm_nopunct(s: str) -> str:
    return re.sub(f"[{re.escape(PUNCT_STRIP)}]", "", s)


def is_noise(line: str) -> bool:
    if line in NOISE_LINES:
        return True
    if len(line) <= 2 and not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", line):
        return True
    return False


def unescape_jsx(raw: str) -> str:
    """微信新版页面把正文塞进 JS 字符串（\\x3c 转义），先解码成真 HTML。"""
    if "\\x3c" not in raw:
        return raw
    return re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), raw)


def html_blocks(raw: str) -> tuple[str, list[dict]]:
    """从发布版 HTML 提正文块。返回 (标题, blocks)。block: {kind, text}."""
    title = ""
    tm = re.search(r'property="og:title"\s+content="([^"]*)"', raw)
    if tm:
        title = htmllib.unescape(tm.group(1)).strip()
    raw = unescape_jsx(raw)
    # 可能出现多个 js_content 片段（DOM 空壳 + JS 内嵌完整版），取最长的
    candidates = re.findall(r'<div[^>]*id="js_content"[^>]*>(.*?)(?:<div[^>]*id="js_tags"|$)', raw, re.S)
    body = max(candidates, key=len) if candidates else raw
    body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    body = re.sub(r"<style.*?</style>", "", body, flags=re.S)

    blocks: list[dict] = []

    # 线性扫描：img / center 行 / blockquote 形态 section（border-left）/ 常规块级元素
    token_re = re.compile(
        r"<img[^>]*>"
        r"|<center[^>]*>(?P<c>.*?)</center>"
        r"|<section(?=[^>]*border-left)[^>]*>(?P<q>.*?)</section>"
        r"|<(?P<tag>p|h[1-6]|blockquote|li)(?P<attrs>[^>]*)>(?P<inner>.*?)</(?P=tag)>",
        re.S,
    )
    for pm in token_re.finditer(body):
        if pm.group(0).startswith("<img"):
            if "mmbiz" in pm.group(0):
                blocks.append({"kind": "img", "text": "[IMG]"})
            continue
        if pm.group("c") is not None or pm.group("q") is not None:
            is_quote = pm.group("q") is not None
            text = htmllib.unescape(re.sub(r"<[^>]+>", "", pm.group("c") or pm.group("q")))
            for seg in text.splitlines():
                seg = re.sub(r"\s+", " ", seg).strip()
                if seg and not is_noise(seg):
                    blocks.append({"kind": "quote" if is_quote else "p", "text": seg})
            continue
        tag, attrs, inner = pm.group("tag"), pm.group("attrs"), pm.group("inner")
        has_img = bool(re.search(r"<img[^>]*mmbiz[^>]*>", inner))
        text = re.sub(r"<img[^>]*>", "", inner)
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = htmllib.unescape(text)
        if has_img:
            blocks.append({"kind": "img", "text": "[IMG]"})
        for seg in text.splitlines():
            seg = re.sub(r"\s+", " ", seg).strip()
            if not seg or is_noise(seg):
                continue
            kind = "p"
            style = attrs.lower()
            if tag.startswith("h"):
                kind = "h"
            elif ("rgb(153, 153, 153)" in style or "#999" in style) and "center" in style:
                kind = "cap"
            elif tag == "blockquote":
                kind = "quote"
            blocks.append({"kind": kind, "text": seg})

    # 兜底：如果上面块级抽取太少（结构非常规），退回行级抽取
    if len(blocks) < 5:
        body2 = re.sub(r"<img[^>]*>", "\n[IMG]\n", body)
        body2 = re.sub(r"</(p|section|h\d|blockquote|li|center)>", "\n", body2)
        body2 = re.sub(r"<br\s*/?>", "\n", body2)
        text = htmllib.unescape(re.sub(r"<[^>]+>", "", body2))
        blocks = []
        for seg in text.splitlines():
            seg = re.sub(r"\s+", " ", seg).strip()
            if not seg or is_noise(seg):
                continue
            blocks.append({"kind": "img" if seg == "[IMG]" else "p", "text": seg})

    # 合并连续 [IMG]
    out: list[dict] = []
    for b in blocks:
        if b["kind"] == "img" and out and out[-1]["kind"] == "img":
            continue
        out.append(b)
    return title, out


DELIVERY_MARKERS = ("副标题（单独发给用户", "图文对照表：", "图文对照 / 图片顺序表", "待确认项：")


def md_blocks(raw: str) -> tuple[str, list[dict]]:
    """从推送版/口述稿 markdown 提正文块。交付区三块截断。"""
    title = ""
    blocks: list[dict] = []
    lines = raw.splitlines()
    prev_img = False
    for line in lines:
        s = line.strip()
        if any(s.startswith(mk) for mk in DELIVERY_MARKERS):
            break
        if not s:
            continue
        if s.startswith("# ") and not title:
            title = s[2:].strip()
            continue
        if re.match(r"^!\[[^\]]*\]\([^)]+\)\s*$", s):
            if not prev_img:
                blocks.append({"kind": "img", "text": "[IMG]"})
            prev_img = True
            continue
        m = re.match(r"^\*([^*].*?)\*\s*$", s)
        if m and prev_img:
            blocks.append({"kind": "cap", "text": m.group(1).strip()})
            prev_img = False
            continue
        prev_img = False
        if s.startswith("## "):
            blocks.append({"kind": "h", "text": s[3:].strip()})
            continue
        if s.startswith("> "):
            blocks.append({"kind": "quote", "text": s[2:].strip()})
            continue
        if s.startswith("<"):
            text = htmllib.unescape(re.sub(r"<[^>]+>", "", s)).strip()
            if text:
                blocks.append({"kind": "p", "text": re.sub(r"\s+", " ", text)})
            continue
        blocks.append({"kind": "p", "text": re.sub(r"\s+", " ", s)})
    return title, blocks


def classify_replace(a: list[str], b: list[str]) -> list[dict]:
    """把一个 replace 块细分。"""
    findings: list[dict] = []
    # 拆段：a 一块 == b 多块拼接（忽略空白）
    if len(a) == 1 and len(b) > 1 and norm_nopunct(a[0]) == norm_nopunct("".join(b)):
        findings.append({"type": "split", "before": a[0], "after": " ⏎ ".join(b)})
        return findings
    if len(a) == len(b):
        for x, y in zip(a, b):
            if x == y:
                continue
            if norm_nopunct(x) == norm_nopunct(y):
                findings.append({"type": "punct_only", "before": x, "after": y})
            else:
                ratio = difflib.SequenceMatcher(a=x, b=y).ratio()
                findings.append(
                    {"type": "tweak" if ratio >= 0.6 else "rewrite", "before": x, "after": y, "ratio": round(ratio, 2)}
                )
        return findings
    findings.append({"type": "rewrite", "before": " / ".join(a), "after": " / ".join(b)})
    return findings


def compare(pushed: list[dict], published: list[dict]) -> dict:
    a = [b["text"] for b in pushed]
    b = [x["text"] for x in published]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    findings: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            findings.extend(classify_replace(a[i1:i2], b[j1:j2]))
        elif tag == "insert":
            for x in b[j1:j2]:
                if x != "[IMG]":
                    findings.append({"type": "added", "after": x})
        elif tag == "delete":
            for x in a[i1:i2]:
                if x != "[IMG]":
                    findings.append({"type": "removed", "before": x})

    # 图注句号统计
    cap_push = [x["text"] for x in pushed if x["kind"] == "cap"]
    cap_pub = [x["text"] for x in published if x["kind"] == "cap"]
    cap_period = {
        "pushed_total": len(cap_push),
        "pushed_with_period": sum(1 for c in cap_push if c.rstrip().endswith(("。", "."))),
        "published_total": len(cap_pub),
        "published_with_period": sum(1 for c in cap_pub if c.rstrip().endswith(("。", "."))),
    }
    return {"findings": findings, "caption_period": cap_period}


def run_one(archive_dir: Path, user_draft: Path | None = None) -> dict:
    pub_file = archive_dir / "published.html"
    md_file = archive_dir / "content.md"
    result: dict = {"archive": archive_dir.name}
    if not pub_file.exists() or not md_file.exists():
        result["error"] = "missing files"
        return result
    pub_raw = pub_file.read_text(encoding="utf-8", errors="replace")
    md_raw = md_file.read_text(encoding="utf-8", errors="replace")
    if "下载失败" in pub_raw[:50] or len(pub_raw) < 200:
        result["error"] = "published.html invalid"
        return result
    pub_title, pub_blocks = html_blocks(pub_raw)
    md_title, push_blocks = md_blocks(md_raw)
    result["pushed_title"] = md_title
    result["published_title"] = pub_title
    result["title_changed"] = bool(md_title and pub_title and norm_nopunct(md_title) != norm_nopunct(pub_title))
    result.update(compare(push_blocks, pub_blocks))
    if user_draft and user_draft.exists():
        _, ud_blocks = md_blocks(user_draft.read_text(encoding="utf-8", errors="replace"))
        result["user_draft_vs_pushed"] = compare(ud_blocks, push_blocks)
    return result


def summarize(results: list[dict]) -> dict:
    stats: dict[str, int] = {}
    cap = {"pushed_with_period": 0, "pushed_total": 0, "published_with_period": 0, "published_total": 0}
    titles_changed = []
    for r in results:
        if r.get("error"):
            continue
        for f in r.get("findings", []):
            stats[f["type"]] = stats.get(f["type"], 0) + 1
        cp = r.get("caption_period", {})
        for k in cap:
            cap[k] += cp.get(k, 0)
        if r.get("title_changed"):
            titles_changed.append({"before": r["pushed_title"], "after": r["published_title"]})
    return {"finding_counts": stats, "caption_period_total": cap, "titles_changed": titles_changed}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive-dir")
    ap.add_argument("--user-draft")
    ap.add_argument("--all", action="store_true")
    ap.add_argument(
        "--archives-root",
        default="/root/.openclaw/skills/wxmp-article-pipeline/references/archives/published",
    )
    ap.add_argument("--json")
    ap.add_argument("--max-print", type=int, default=200)
    args = ap.parse_args()

    results: list[dict] = []
    if args.all:
        root = Path(args.archives_root)
        for d in sorted(root.iterdir()):
            if d.is_dir():
                results.append(run_one(d))
    elif args.archive_dir:
        results.append(run_one(Path(args.archive_dir), Path(args.user_draft) if args.user_draft else None))
    else:
        ap.error("--archive-dir 或 --all 至少一个")

    payload = {"results": results, "summary": summarize(results)}
    if args.json:
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved: {args.json}")

    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    shown = 0
    for r in results:
        if r.get("error"):
            print(f"\n## {r['archive']}  SKIP: {r['error']}")
            continue
        print(f"\n## {r['archive']}")
        if r.get("title_changed"):
            print(f"  标题: {r['pushed_title']}  ->  {r['published_title']}")
        cp = r.get("caption_period", {})
        print(
            f"  图注句号: 推送 {cp.get('pushed_with_period')}/{cp.get('pushed_total')}"
            f" -> 发布 {cp.get('published_with_period')}/{cp.get('published_total')}"
        )
        for f in r.get("findings", []):
            if shown >= args.max_print:
                print("  ...(截断)")
                return
            t = f["type"]
            if t in ("added", "removed"):
                print(f"  [{t}] {f.get('after') or f.get('before')}"[:150])
            else:
                print(f"  [{t}] {f.get('before','')[:70]}  ->  {f.get('after','')[:70]}")
            shown += 1


if __name__ == "__main__":
    main()
