#!/usr/bin/env python3
"""
archive_articles.py — 从微信后台拉取已发布文章，自动存档到 references/archives/published/

存档结构（每篇文章一个文件夹）：
  references/archives/published/YYYY-MM-DD-标题slug/
    published.html   ← 微信发布版原文（真实渲染HTML）
    content.md       ← 净化版Markdown（原写作稿）

用法:
  python3 archive_articles.py                  # 拉全部文章（跳过已存档）
  python3 archive_articles.py --since 2026-03-01  # 只拉指定日期之后的
  python3 archive_articles.py --force           # 强制覆盖已存档的文章
  python3 archive_articles.py --dry-run         # 只显示要拉哪些，不实际下载
  python3 archive_articles.py --latest           # 只拉最新一篇文章（发布后触发）
"""

import argparse
import subprocess
import json
import re
import sys
import os
from datetime import datetime
from pathlib import Path

# 路径配置
SCRIPT_DIR = Path(__file__).parent
WXDOWN_DIR = SCRIPT_DIR.parent.parent / "wxmp-wxdown"
ARCHIVE_DIR = SCRIPT_DIR.parent / "references" / "archives" / "published"
HIST_INDEX = SCRIPT_DIR.parent / "references" / "HISTORICAL-ARTICLES.md"


def run_wxdown(args: list[str], timeout: int = 60) -> str:
    """在 wxdown 目录下执行 wxdown-manage.py"""
    cmd = ["python3", "scripts/wxdown-manage.py"] + args
    result = subprocess.run(
        cmd,
        cwd=WXDOWN_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        print(f"  ⚠️ wxdown 命令失败: {' '.join(args)}", file=sys.stderr)
        print(f"  {result.stderr}", file=sys.stderr)
        return ""
    return result.stdout


def get_articles(limit: int = 20) -> list[dict]:
    """获取文章列表，解析输出"""
    output = run_wxdown(["articles", "findyi", "--size", str(limit)])
    articles = []

    current = {}
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^\d+\.\s+\*\*(.+?)\*\*", line)
        if m:
            if current:
                articles.append(current)
            current = {"title": m.group(1)}
            continue
        m = re.match(r"发布:\s*(\d{4}-\d{2}-\d{2})", line)
        if m:
            current["date"] = m.group(1)
            continue
        m = re.match(r"链接:\s*(https://mp\.weixin\.qq\.com/s/\S+)", line)
        if m:
            current["url"] = m.group(1)
            continue
        m = re.match(r"摘要:\s*(.+)", line)
        if m:
            current["abstract"] = m.group(1)
            continue

    if current:
        articles.append(current)

    return articles


def slugify(title: str) -> str:
    """标题转 slug: 去掉特殊字符，取前12字（文件夹名要短）"""
    s = re.sub(r"[^\w\s\u4e00-\u9fff]", "", title)
    s = re.sub(r"\s+", "-", s)
    return s[:12] if len(s) > 12 else s


def archive_foldername(article: dict) -> str:
    """生成存档文件夹名: YYYY-MM-DD-slug"""
    date = article.get("date", datetime.now().strftime("%Y-%m-%d"))
    slug = slugify(article["title"])
    return f"{date}-{slug}"


def is_archived(article: dict) -> bool:
    """检查是否已存档（published.html 存在即为完整存档）"""
    folder = archive_foldername(article)
    folder_path = ARCHIVE_DIR / folder
    return (folder_path / "published.html").exists()


def download_both(url: str) -> tuple[str, str]:
    """同时下载 HTML 和 MD 格式，返回 (html, md)"""
    html = run_wxdown(["download", url, "--format", "html"], timeout=90)
    md = run_wxdown(["download", url, "--format", "md"], timeout=90)
    return html, md


def clean_md(content: str) -> str:
    """净化 wxdown 下载的 md：去掉微信 HTML wrapper"""
    import re
    content = re.sub(r'^::: \{[^}]*\}[^\n]*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'\n:::\s*$', '\n', content)
    return content


def save_article(article: dict, html: str, md: str, force: bool = False) -> bool:
    """保存文章到文件夹"""
    folder = archive_foldername(article)
    folder_path = ARCHIVE_DIR / folder
    folder_path.mkdir(parents=True, exist_ok=True)

    (folder_path / "published.html").write_text(html)
    (folder_path / "content.md").write_text(clean_md(md))
    return True


def update_hist_index(articles: list[dict]):
    """更新 HISTORICAL-ARTICLES.md 的已发布文章表格"""
    if not HIST_INDEX.exists():
        print("  ⚠️ HISTORICAL-ARTICLES.md 不存在，跳过索引更新")
        return

    content = HIST_INDEX.read_text()
    existing_urls = set(re.findall(r"https://mp\.weixin\.qq\.com/s/\S+", content))

    new_lines = []
    for a in articles:
        if a.get("url") in existing_urls:
            continue
        date = a.get("date", "")
        title = a.get("title", "")
        url = a.get("url", "")
        abstract = a.get("abstract", "")
        folder = archive_foldername(a)
        new_lines.append(f"| {date} | {title} | {folder}/ | {url} | {abstract} |")

    if not new_lines:
        print("  ✓ HISTORICAL-ARTICLES.md 已是最新的")
        return

    last_sep = content.rfind("|------|")
    if last_sep != -1:
        end = content.find("\n", last_sep)
        if end != -1:
            insert_pos = end + 1
            new_content = content[:insert_pos] + "\n".join(new_lines) + "\n" + content[insert_pos:]
            HIST_INDEX.write_text(new_content)
            print(f"  ✓ HISTORICAL-ARTICLES.md 新增 {len(new_lines)} 条记录")
            return

    HIST_INDEX.write_text(content + "\n" + "\n".join(new_lines) + "\n")
    print(f"  ✓ HISTORICAL-ARTICLES.md 追加 {len(new_lines)} 条记录")


def main():
    parser = argparse.ArgumentParser(description="从微信后台拉取已发布文章并存档")
    parser.add_argument("--since", default="", help="只拉此日期之后的文章，如 2026-03-01")
    parser.add_argument("--force", action="store_true", help="强制覆盖已存档的文章")
    parser.add_argument("--dry-run", action="store_true", help="只显示要拉哪些，不实际下载")
    parser.add_argument("--latest", action="store_true", help="只拉最新一篇文章（发布后立即触发）")
    parser.add_argument("--json", action="store_true", help="stdout 输出结构化 JSON（供 freeze-latest 等上层 CLI 消费）, 人类日志改走 stderr")
    args = parser.parse_args()

    # When --json, redirect all human-readable prints to stderr so stdout stays clean
    import sys as _sys
    _json_mode = args.json
    import builtins as _builtins
    _log_fn = _builtins.print

    def print(*a, **kw):  # noqa: A001
        if _json_mode:
            kw.setdefault("file", _sys.stderr)
        _log_fn(*a, **kw)

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    print("📋 获取文章列表...")
    articles = get_articles(limit=20)
    print(f"  → 获取到 {len(articles)} 篇文章")

    if args.latest:
        articles = articles[:1]
        print(f"  → 只拉最新: {articles[0]['title'][:30]}")

    if args.since:
        from datetime import datetime as dt
        since = dt.strptime(args.since, "%Y-%m-%d")
        articles = [
            a for a in articles
            if a.get("date") and dt.strptime(a["date"], "%Y-%m-%d") >= since
        ]
        print(f"  → 过滤后 {len(articles)} 篇（{args.since} 之后）")

    if not articles:
        print("没有文章需要存档")
        if args.json:
            print(json.dumps({"ok": False, "articles": [], "reason": "no articles returned from wxdown"}, ensure_ascii=False))
        return

    print("\n📥 开始存档...")
    archived = []
    skipped = 0
    for a in articles:
        folder = archive_foldername(a)
        folder_path = ARCHIVE_DIR / folder

        if is_archived(a) and not args.force:
            print(f"  ✓ 已存档，跳过: {folder}/")
            skipped += 1
            continue

        if args.dry_run:
            status = "覆盖" if folder_path.exists() else "新建"
            print(f"  [dry-run] {status}: {folder}/")
            continue

        print(f"  下载中: {a.get('title', 'unknown')[:30]}...")
        html, md = download_both(a["url"])
        if html and md:
            save_article(a, html, md, args.force)
            archived.append(a)
            print(f"  ✓ 已存档: {folder}/")
        else:
            print(f"  ⚠️ 下载失败: {a.get('url')}")

    if archived:
        print("\n📝 更新索引...")
        update_hist_index(archived)

    done = len(archived) if not args.dry_run else 0
    todo = len([a for a in articles if not is_archived(a)]) if not args.dry_run else 0
    print(f"\n✅ 完成。共存档 {done} 篇，跳过 {skipped} 篇（dry-run 显示 {todo} 篇待存）")

    if args.json:
        # Emit structured result to real stdout
        result_articles = []
        for a in articles:
            folder = archive_foldername(a)
            folder_path = ARCHIVE_DIR / folder
            if a in archived:
                status = "archived"
            elif is_archived(a):
                status = "skipped"  # already existed
            else:
                status = "failed"
            result_articles.append({
                "folder": folder,
                "path": str(folder_path),
                "title": a.get("title", ""),
                "date": a.get("date", ""),
                "url": a.get("url", ""),
                "status": status,
            })
        payload = {"ok": True, "articles": result_articles}
        print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
