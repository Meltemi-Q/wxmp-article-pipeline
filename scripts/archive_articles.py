#!/usr/bin/env python3
"""
archive_articles.py — 从微信后台拉取已发布文章，自动存档到 references/archives/published/

用法:
  python3 archive_articles.py              # 拉全部文章
  python3 archive_articles.py --since 2026-03-01  # 只拉指定日期之后的
  python3 archive_articles.py --force      # 强制覆盖已存档的文章
  python3 archive_articles.py --dry-run   # 只显示要拉哪些，不实际下载
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


def run_wxdown(args: list[str]) -> str:
    """在 wxdown 目录下执行 wxdown-manage.py"""
    cmd = ["python3", "scripts/wxdown-manage.py"] + args
    result = subprocess.run(
        cmd,
        cwd=WXDOWN_DIR,
        capture_output=True,
        text=True,
        timeout=60,
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

    # 解析 "## 「findyi」最新文章" 格式
    # 格式: 1. **标题** 作者: xxx 发布: YYYY-MM-DD HH:MM 摘要: xxx 链接: https://...
    current = {}
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 文章编号行
        m = re.match(r"^\d+\.\s+\*\*(.+?)\*\*", line)
        if m:
            if current:
                articles.append(current)
            current = {"title": m.group(1)}
            continue
        # 发布日期
        m = re.match(r"发布:\s*(\d{4}-\d{2}-\d{2})", line)
        if m:
            current["date"] = m.group(1)
            continue
        # 链接
        m = re.match(r"链接:\s*(https://mp\.weixin\.qq\.com/s/\S+)", line)
        if m:
            current["url"] = m.group(1)
            continue
        # 摘要
        m = re.match(r"摘要:\s*(.+)", line)
        if m:
            current["abstract"] = m.group(1)
            continue

    if current:
        articles.append(current)

    return articles


def slugify(title: str) -> str:
    """标题转 slug: 去掉特殊字符，取前20字"""
    s = re.sub(r"[^\w\s\u4e00-\u9fff]", "", title)
    s = re.sub(r"\s+", "-", s)
    # 取前20字符
    return s[:20] if len(s) > 20 else s


def archive_filename(article: dict) -> str:
    """生成存档文件名: YYYY-MM-DD-slug-published.md"""
    date = article.get("date", datetime.now().strftime("%Y-%m-%d"))
    slug = slugify(article["title"])
    return f"{date}-{slug}-published.md"


def download_article(url: str) -> str:
    """下载单篇文章内容（原始markdown）"""
    output = run_wxdown(["download", url, "--format", "md"])
    return output


def already_archived(article: dict, force: bool = False) -> bool:
    """检查是否已存档"""
    fname = archive_filename(article)
    fpath = ARCHIVE_DIR / fname
    if not fpath.exists():
        return False
    if force:
        print(f"  → 强制覆盖: {fname}")
        return False
    print(f"  ✓ 已存档，跳过: {fname}")
    return True


def update_hist_index(articles: list[dict]):
    """更新 HISTORICAL-ARTICLES.md 的已发布文章表格"""
    # 读取现有内容
    if HIST_INDEX.exists():
        content = HIST_INDEX.read_text()
    else:
        content = ""

    # 提取已有链接（避免重复写入）
    existing_urls = set(re.findall(r"https://mp\.weixin\.qq\.com/s/\S+", content))

    # 生成新行
    new_lines = []
    for a in articles:
        if a.get("url") in existing_urls:
            continue
        date = a.get("date", "")
        title = a.get("title", "")
        url = a.get("url", "")
        abstract = a.get("abstract", "")
        new_lines.append(f"| {date} | {title} | {url} | {abstract} |")

    if not new_lines:
        print("  ✓ HISTORICAL-ARTICLES.md 已是最新的")
        return

    # 找到表格最后一行（| ---- | 之后的第一行），在其后插入
    if "| 日期 | 标题 | 链接 | 摘要 |" in content:
        # 找到表格结束位置（最后一个 | --- | 行之后）
        last_sep = content.rfind("|------|")
        if last_sep != -1:
            end = content.find("\n", last_sep)
            if end != -1:
                insert_pos = end + 1
                new_content = content[:insert_pos] + "\n".join(new_lines) + "\n" + content[insert_pos:]
                HIST_INDEX.write_text(new_content)
                print(f"  ✓ HISTORICAL-ARTICLES.md 新增 {len(new_lines)} 条记录")
                return

    # 兜底：直接追加
    HIST_INDEX.write_text(content + "\n" + "\n".join(new_lines) + "\n")
    print(f"  ✓ HISTORICAL-ARTICLES.md 追加 {len(new_lines)} 条记录")


def main():
    parser = argparse.ArgumentParser(description="从微信后台拉取已发布文章并存档")
    parser.add_argument("--since", default="", help="只拉此日期之后的文章，如 2026-03-01")
    parser.add_argument("--force", action="store_true", help="强制覆盖已存档的文章")
    parser.add_argument("--dry-run", action="store_true", help="只显示要拉哪些，不实际下载")
    args = parser.parse_args()

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    print("📋 获取文章列表...")
    articles = get_articles(limit=20)
    print(f"  → 获取到 {len(articles)} 篇文章")

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
        return

    print("\n📥 开始存档...")
    archived = []
    for a in articles:
        fname = archive_filename(a)
        fpath = ARCHIVE_DIR / fname

        if already_archived(a, args.force):
            continue

        if args.dry_run:
            print(f"  [dry-run] 将存档: {fname}")
            continue

        print(f"  下载中: {a.get('title', 'unknown')[:30]}...")
        content = download_article(a["url"])
        if content:
            fpath.write_text(content)
            archived.append(a)
            print(f"  ✓ 已存档: {fname}")
        else:
            print(f"  ⚠️ 下载失败: {a.get('url')}")

    if archived:
        print("\n📝 更新索引...")
        update_hist_index(archived)

    print(f"\n✅ 完成。共存档 {len(archived) if not args.dry_run else 0} 篇（dry-run 显示 {len([a for a in articles if not already_archived(a, args.force)])} 篇待存）")


if __name__ == "__main__":
    main()
