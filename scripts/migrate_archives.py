#!/usr/bin/env python3
"""
migrate_archives.py — 将 published 目录从"一个md文件平铺"迁移到"每篇文章一个文件夹"结构

结构：
  2026-04-09-ai外挂-副业自动化/
    original.md      ← wxdown 下载的原版（含 HTML 样式）
    content.md       ← 净化版（去掉微信 wrapper，保留正文）
"""

import re
import os
import shutil
from pathlib import Path

PUBLISHED = Path(__file__).parent.parent / "references" / "archives" / "published"
DRAFTS = Path(__file__).parent.parent / "references" / "archives" / "drafts"


def slug_to_foldername(filename: str) -> str:
    """文件名转文件夹名: 2026-04-09-xxx-published.md → 2026-04-09-xxx"""
    s = re.sub(r'-published\.md$', '', filename)
    return s


def clean_wxdown_md(content: str) -> str:
    """净化微信 wxdown 下载的 md：
    - 去掉顶部的 ::: {.section ...} 和底部的 :::
    - 保留所有正文内容（包括 hr 分隔线、图片引用、markdown 格式）
    """
    import re
    # 删除顶部的 ::: {.section...} 行
    content = re.sub(r'^::: \{[^}]*\}[^\n]*\n', '', content, flags=re.MULTILINE)
    # 删除尾部的单独 ::: 行
    content = re.sub(r'\n:::\s*$', '\n', content)
    return content


def main(dry_run: bool = True):
    md_files = sorted(PUBLISHED.glob("*.md"))
    print(f"找到 {len(md_files)} 个 md 文件")

    groups: dict[str, list[Path]] = {}
    for f in md_files:
        folder = slug_to_foldername(f.name)
        groups.setdefault(folder, []).append(f)

    if dry_run:
        print("\n=== 迁移计划 ===")

    for folder, files in groups.items():
        folder_path = PUBLISHED / folder
        if len(files) == 1:
            if dry_run:
                print(f"  ✓ 单文件 → {folder}/")
            else:
                folder_path.mkdir(exist_ok=True)
                shutil.copy2(files[0], folder_path / "original.md")
                clean = clean_wxdown_md(files[0].read_text())
                (folder_path / "content.md").write_text(clean)
                files[0].unlink()
        else:
            best = max(files, key=lambda f: f.stat().st_size)
            others = [f for f in files if f != best]
            if dry_run:
                print(f"  ⚠️ {folder}/ 重复 {len(files)} 个，保留: {best.name}")
            else:
                folder_path.mkdir(exist_ok=True)
                shutil.copy2(best, folder_path / "original.md")
                clean = clean_wxdown_md(best.read_text())
                (folder_path / "content.md").write_text(clean)
                best.unlink()
                for o in others:
                    o.unlink()
                print(f"  ✓ {folder}/ (删{len(others)}重复)")

    if dry_run:
        print("\n[dry-run 模式] 去掉 --confirm 执行")
    else:
        print("\n✅ 迁移完成")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true", help="确认执行迁移")
    args = parser.parse_args()
    main(dry_run=not args.confirm)
