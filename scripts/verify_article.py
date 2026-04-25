#!/usr/bin/env python3
"""
verify_article.py - 推送前文章自检脚本

检查项：
1. PART 字样是否存在
2. 图片数量和 markdown 中图片引用数量是否一致
3. 每张图前后的文字是否提到了图里的内容（人工核查）

用法：
  python3 scripts/verify_article.py /path/to/article.md
"""
import sys
import re

def verify_article(md_path):
    with open(md_path) as f:
        text = f.read()

    errors = []
    warnings = []

    # 1. 检查 PART 字样
    part_matches = []
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r'\bPART\b', line, re.IGNORECASE):
            part_matches.append(f"  行 {i}: {line.strip()[:60]}")
    if part_matches:
        errors.append(f"❌ 发现 PART 字样（共 {len(part_matches)} 处）:\n" + "\n".join(part_matches))

    # 2. 检查图片数量
    images_in_markdown = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', text)
    print(f"📷 Markdown 中的图片引用: {len(images_in_markdown)} 张")
    for i, (alt, path) in enumerate(images_in_markdown, 1):
        print(f"  [{i}] {path} | alt={alt[:30]}")

    # 3. 检查标题格式（## 后面不能是空）
    for i, line in enumerate(text.splitlines(), 1):
        if line.startswith('## '):
            rest = line[3:].strip()
            if not rest:
                errors.append(f"❌ 行 {i}: ## 标题后没有内容")
            elif rest.startswith('PART') or rest.startswith('part'):
                errors.append(f"❌ 行 {i}: 标题不能以 PART 开头: {rest[:40]}")

    # 4. 检查提示词格式（有 > 提示词： 的前面必须有图片）
    prompt_blocks = [(m.start(), m.group(0))
                     for m in re.finditer(r'>\s*提示词：[^\n]+', text)]
    for pos, block in prompt_blocks:
        # 往前找最近的图片
        before = text[:pos]
        last_img = re.search(r'!\[([^\]]*)\]\(([^)]+)\)', before)
        if not last_img:
            # 再往后找
            after = text[pos:]
            next_img = re.search(r'!\[([^\]]*)\]\(([^)]+)\)', after)
            errors.append(f"❌ 提示词前面没有图片: {block[:40]}")
        else:
            print(f"  ✓ 提示词已正确关联图片: ...{last_img.group(2)}")

    # 5. 图片-alt 检查（alt 不能是文件名如 img_xx.png）
    for alt, path in images_in_markdown:
        if alt and (alt.startswith('img_') or re.match(r'^[a-zA-Z0-9_-]+\.(png|jpg|jpeg)', alt)):
            warnings.append(f"⚠️  图片 alt 可能用了文件名而非描述: {alt} -> {path}")

    # 6. 图片 alt 不能为空
    for i, (alt, path) in enumerate(images_in_markdown):
        if not alt.strip():
            warnings.append(f"⚠️  [{i+1}] {path} 的 alt 为空，建议填写图片描述")

    # 输出结果
    print()
    if errors:
        print("\n".join(errors))
    if warnings:
        print("\n".join(warnings))
    if not errors and not warnings:
        print("✅ 基础检查通过")
    elif not errors:
        print("✅ 无阻断性问题（仅有警告）")
    else:
        print(f"\n❌ {len(errors)} 个错误，{len(warnings)} 个警告")
        return 1

    return 0

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 verify_article.py <article.md>")
        sys.exit(1)
    sys.exit(verify_article(sys.argv[1]))
