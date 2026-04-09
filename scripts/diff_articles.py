#!/usr/bin/env python3
"""
diff_articles.py — 对比原稿（content.md）和发布版（published.html）的差异

用法:
  python3 diff_articles.py "2026-04-09-我给AI装上了外挂它能自"
  python3 diff_articles.py "2026-04-09"        # 模糊匹配（日期开头）
  python3 diff_articles.py --list               # 列出所有可对比的文章
"""

import argparse
import re
import sys
from pathlib import Path
from html.parser import HTMLParser

SCRIPT_DIR = Path(__file__).parent
ARCHIVE_DIR = SCRIPT_DIR.parent / "references" / "archives" / "published"


class TextExtractor(HTMLParser):
    """从 HTML 中提取纯文本，保留段落和标题结构"""
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.skip = False
        self.in_style = False
        self.indent_level = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in ('style', 'script'):
            self.in_style = True
        elif tag == 'p':
            self.text_parts.append('\n')
        elif tag == 'br':
            self.text_parts.append('\n')
        elif tag in ('h1', 'h2', 'h3'):
            self.text_parts.append('\n\n## ')
        elif tag in ('li',):
            self.text_parts.append('\n- ')
        elif tag in ('blockquote',):
            self.text_parts.append('\n> ')
        elif tag == 'hr':
            self.text_parts.append('\n---\n')

    def handle_endtag(self, tag):
        if tag == 'style':
            self.in_style = False
        elif tag in ('p', 'h1', 'h2', 'h3'):
            self.text_parts.append('')
        elif tag == 'br':
            self.text_parts.append('\n')

    def handle_data(self, data):
        if not self.in_style:
            self.text_parts.append(data.strip())

    def get_text(self) -> str:
        text = ''.join(self.text_parts)
        # 清理多余空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


def extract_html_text(html: str) -> str:
    """从 HTML 提取纯文本"""
    parser = TextExtractor()
    try:
        parser.feed(html)
        return parser.get_text()
    except Exception:
        # fallback: 简单 strip tag
        text = re.sub(r'<[^>]+>', '', html)
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


def extract_md_text(md: str) -> str:
    """从 Markdown 提取纯文本（去掉格式符号）"""
    text = md
    # 去掉标题符号
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # 去掉加粗斜体
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)
    # 去掉链接，保留文字
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # 去掉图片
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # 去掉 hr
    text = re.sub(r'^[-*_]{3,}$', '', text, flags=re.MULTILINE)
    # 去掉 blockquote 符号
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    # 清理
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def normalize_text(text: str) -> list[str]:
    """把文本切成句子列表，方便逐句对比"""
    # 按句号/感叹号/问号/换行分割
    sentences = re.split(r'(?<=[。！？.!?])\s*', text)
    result = []
    for s in sentences:
        s = s.strip()
        if s and len(s) > 1:
            result.append(s)
    return result


def simple_diff(lines_a: list[str], lines_b: list[str]) -> dict:
    """朴素 diff：找出新增、删除、保留的句子"""
    set_a = set(lines_a)
    set_b = set(lines_b)

    removed = [l for l in lines_a if l not in set_b]
    added = [l for l in lines_b if l not in set_a]
    common = [l for l in lines_a if l in set_b]

    return {
        'added': added,
        'removed': removed,
        'common': common,
    }


def find_folder(keyword: str) -> Path | None:
    """根据关键字（日期/标题片段）找文章文件夹"""
    keyword = keyword.strip()
    folders = sorted(ARCHIVE_DIR.iterdir())

    # 精确匹配文件夹名
    for f in folders:
        if f.is_dir() and f.name == keyword:
            return f

    # 日期开头匹配
    for f in folders:
        if f.is_dir() and f.name.startswith(keyword):
            return f

    # 模糊匹配（关键字在文件夹名里）
    matches = [f for f in folders if f.is_dir() and keyword in f.name]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"⚠️ 找到多个匹配：")
        for m in matches:
            print(f"  - {m.name}/")
        return None

    # 搜索所有子文件夹
    for f in folders:
        if not f.is_dir():
            continue
        html_file = f / "published.html"
        md_file = f / "content.md"
        if html_file.exists() and md_file.exists() and keyword.lower() in open(html_file).read(200).lower():
            return f

    return None


def diff_article(folder: Path) -> dict:
    """对比单篇文章的 content.md 和 published.html"""
    md_file = folder / "content.md"
    html_file = folder / "published.html"

    if not md_file.exists():
        return {'error': f'content.md 不存在: {folder}'}
    if not html_file.exists():
        return {'error': f'published.html 不存在: {folder}'}

    md_text = extract_md_text(md_file.read_text())
    html_text = extract_html_text(html_file.read_text())

    md_lines = normalize_text(md_text)
    html_lines = normalize_text(html_text)

    diff = simple_diff(md_lines, html_lines)

    return {
        'folder': folder.name,
        'md_sentences': len(md_lines),
        'html_sentences': len(html_lines),
        'common_count': len(diff['common']),
        'added': diff['added'],
        'removed': diff['removed'],
        'md_preview': md_text[:300],
        'html_preview': html_text[:300],
    }


def print_diff(result: dict):
    """打印对比结果"""
    if 'error' in result:
        print(f"❌ {result['error']}")
        return

    print(f"\n📄 {result['folder']}/")
    print(f"   原稿句子数: {result['md_sentences']}  |  发布版句子数: {result['html_sentences']}  |  共同: {result['common_count']}")
    print(f"\n  【发布版新增的内容】")
    if result['added']:
        for s in result['added'][:10]:
            print(f"  + {s[:100]}")
        if len(result['added']) > 10:
            print(f"  ... 还有 {len(result['added']) - 10} 句")
    else:
        print("  （无）")

    print(f"\n  【原稿有但发布版没有的】")
    if result['removed']:
        for s in result['removed'][:10]:
            print(f"  - {s[:100]}")
        if len(result['removed']) > 10:
            print(f"  ... 还有 {len(result['removed']) - 10} 句")
    else:
        print("  （无）")

    print(f"\n  【原稿前100字】")
    print(f"  {result['md_preview'][:100]}")
    print(f"\n  【发布版前100字】")
    print(f"  {result['html_preview'][:100]}")


def list_articles():
    """列出所有可对比的文章"""
    folders = sorted([f for f in ARCHIVE_DIR.iterdir() if f.is_dir()])
    print("所有可对比的文章：")
    for f in folders:
        has_html = (f / "published.html").exists()
        has_md = (f / "content.md").exists()
        status = "✅" if (has_html and has_md) else "⚠️"
        print(f"  {status} {f.name}/  (html={has_html}, md={has_md})")


def main():
    parser = argparse.ArgumentParser(description="对比原稿和发布版差异")
    parser.add_argument("keyword", nargs='?', default="", help="文章关键字或日期（支持模糊匹配）")
    parser.add_argument("--list", action="store_true", help="列出所有可对比的文章")
    args = parser.parse_args()

    if args.list or not args.keyword:
        list_articles()
        return

    folder = find_folder(args.keyword)
    if not folder:
        print(f"❌ 找不到匹配 '{args.keyword}' 的文章")
        list_articles()
        return

    result = diff_article(folder)
    print_diff(result)


if __name__ == "__main__":
    main()
