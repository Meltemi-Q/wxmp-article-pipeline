#!/usr/bin/env python3
"""历史文章深度语料挖宝脚本 (Mine Voice Treasure)。

遍历 references/archives/published/ 和 drafts/ 下所有历史文章，
提取宇龙标志性的高频金句、转折词、自嘲调侃、动作指令与互动句式，
沉淀出系统化的语料宝库 references/yulong-voice-treasure-vault.md。
"""
import html as htmllib
import json
import re
from pathlib import Path

ARCHIVES_DIR = Path("skills/wxmp-article-pipeline/references/archives/published")
DRAFTS_DIR = Path("drafts")

PATTERNS = {
    "openers": [],
    "action_phrases": [],
    "emotions_and_humor": [],
    "judgments_and_insights": [],
    "transitions": [],
    "closers_and_ctas": []
}

def clean_html(raw: str) -> list[str]:
    raw = re.sub(r'<script.*?</script>', '', raw, flags=re.S)
    raw = re.sub(r'<style.*?</style>', '', raw, flags=re.S)
    lines = []
    for m in re.finditer(r'<(?:p|h[1-6]|li|section|blockquote)[^>]*>(.*?)</(?:p|h[1-6]|li|section|blockquote)>', raw, re.S):
        text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        text = htmllib.unescape(text)
        if text and len(text) > 3 and not text.startswith("http") and not "微信扫一扫" in text:
            lines.append(text)
    return lines

def mine():
    all_articles = []
    
    # 1. 扫描 archives
    if ARCHIVES_DIR.exists():
        for d in sorted(ARCHIVES_DIR.iterdir()):
            if d.is_dir():
                pub_file = d / "published.html"
                md_file = d / "content.md"
                if pub_file.exists():
                    lines = clean_html(pub_file.read_text(encoding="utf-8", errors="replace"))
                    if lines:
                        all_articles.append({"title": d.name, "lines": lines})
                elif md_file.exists():
                    lines = [l.strip() for l in md_file.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip() and not l.startswith("#")]
                    all_articles.append({"title": d.name, "lines": lines})

    # 2. 扫描 drafts
    if DRAFTS_DIR.exists():
        for d in sorted(DRAFTS_DIR.iterdir()):
            if d.is_dir():
                push_file = d / "article-push.md"
                art_file = d / "article.md"
                f = push_file if push_file.exists() else art_file if art_file.exists() else None
                if f:
                    lines = [l.strip() for l in f.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip() and not l.startswith("#")]
                    all_articles.append({"title": d.name, "lines": lines})

    print(f"📚 成功加载 {len(all_articles)} 篇历史文章，开始深度语料挖宝...")

    # 提取特征
    treasure_vault = {
        "开门见山（Hook 开篇句）": set(),
        "现场动作与操作句（Action Verbs）": set(),
        "幽默自嘲与情绪感叹（Humor & Emotion）": set(),
        "转折与轻量校准（Transitions）": set(),
        "商业判断与生态洞察（Deep Insights）": set(),
        "文末互动与号召（CTA & Closers）": set(),
    }

    for art in all_articles:
        lines = art["lines"]
        if not lines:
            continue
        
        # 开篇句
        first_p = lines[0] if len(lines) > 0 else ""
        if 8 <= len(first_p) <= 80:
            treasure_vault["开门见山（Hook 开篇句）"].add(first_p)

        for line in lines:
            # 情绪/自嘲
            if re.search(r'(哈哈哈|好家伙|666|脑阔痛|偷懒|白嫖|像模像样|真刺激|离谱|折腾|老实|有点慌|救命|搞事情)', line):
                if 10 <= len(line) <= 90:
                    treasure_vault["幽默自嘲与情绪感叹（Humor & Emotion）"].add(line)

            # 现场动作
            if re.search(r'(手机上发|点开|两只小眼睛|一戳|随便发挥|一句话|手搓|薅着|调出|盘一盘|甩过来|立规矩)', line):
                if 10 <= len(line) <= 80:
                    treasure_vault["现场动作与操作句（Action Verbs）"].add(line)

            # 转折/校准
            if re.search(r'(不过|话说回来|但只要你|说白了|不是.*而是|仔细一琢磨|这还没完|有意思的是)', line):
                if 10 <= len(line) <= 80:
                    treasure_vault["转折与轻量校准（Transitions）"].add(line)

            # 商业洞察/判断
            if re.search(r'(阳谋|生态|这步棋|降维打击|算力|壁垒|飞轮|底层逻辑|借力|各取所需)', line):
                if 15 <= len(line) <= 100:
                    treasure_vault["商业判断与生态洞察（Deep Insights）"].add(line)

            # 文末互动
            if re.search(r'(评论区|聊聊|你最想|赌|试试|👇|留言)', line):
                if 10 <= len(line) <= 80:
                    treasure_vault["文末互动与号召（CTA & Closers）"].add(line)

    # 导出 Markdown
    md_out = ["# 宇龙专属高频金句与语感宝库 (Yulong Voice Treasure Vault)\n",
              "> 来源：从 60+ 篇历史已发布文章与手改草稿中全量萃取。这是宇龙最真实、最具辨识度的大白话资产。\n"]

    for category, items in treasure_vault.items():
        md_out.append(f"\n## 💎 {category} (共 {len(items)} 条)\n")
        sorted_items = sorted(list(items), key=lambda x: len(x))
        for item in sorted_items[:25]:  # 挑前 25 条精华
            md_out.append(f"- 「{item}」")

    out_file = Path("skills/wxmp-article-pipeline/references/yulong-voice-treasure-vault.md")
    out_file.write_text("\n".join(md_out), encoding="utf-8")
    print(f"✨ 挖宝完成！宝库已生成: {out_file}")

if __name__ == "__main__":
    mine()
