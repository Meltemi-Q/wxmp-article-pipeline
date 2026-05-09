#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


PROCESS_PATTERNS = [
    r"^Now I have",
    r"现在开始写",
    r"已读取完毕",
    r"草稿台里的原始素材已读取",
    r"图都确认完了",
    r"图片.*已上传",
    r"已上传到 mmbiz",
    r"我确认到的事实是",
]

FAKE_ACTION_PATTERNS = [
    r"已上传到 mmbiz",
    r"已经推送",
    r"已经保存",
    r"已经创建",
    r"草稿箱.*已",
]

AI_FLAVOR_PATTERNS = [
    r"真正能打开的结果",
    r"可访问的结果",
    r"把任务往后推",
    r"一点点往前磨",
    r"讲得太大",
    r"单点能力",
    r"工具接力",
    r"这条链路稳定",
    r"等.*链路.*底气",
    r"链路跑顺",
    r"底气就不一样",
    r"底气不一样",
    r"迁移到别的地方只是时间问题",
    r"同样的方式做",
    r"全流程没碰过代码",
    r"两个 AI 协作，一个管视觉，一个管听觉",
    r"这也是我觉得现在最值得折腾的地方",
    r"未来的样子",
    r"我们正在进入一个阶段",
    r"开始真实了",
    r"比.+更重要的是",
    r"这件事以后可能不只是",
    r"当然，现在还没那么丝滑",
    r"不是某个 AI 工具突然天下无敌",
    r"不是.*AI.*天下无敌",
    r"这就是现在的效率",
    r"效率被.*拉高",
    r"电子世界里可以呼风唤雨",
    r"框架是存在的",
    r"大概也是同样的思路",
]

HARD_SALES_PATTERNS = [
    r"我可以承接",
    r"我是宇龙",
    r"承接企业",
    r"企业真正需要",
    r"AI 员工落地",
    r"AI 转型负责人",
    r"CRM",
]

UNSUPPORTED_CLAIM_PATTERNS = [
    r"翘班",
    r"薅.*羊毛",
    r"游戏公司工作室门口",
    r"图纸",
    r"怪物.*乖物",
    r"GPT-?image2?.*音效",
    r"半小时",
    r"前后.*半个小时",
    r"十来分钟",
    r"15分钟",
    r"15 分钟",
    r"我没急着排队",
    r"站着看了一会儿",
]


def uncaptioned_body_images(output_text: str) -> list[str]:
    lines = output_text.splitlines()
    missing = []
    for idx, line in enumerate(lines):
        m = re.match(r"!\[[^\]]*\]\(([^)]+)\)\s*$", line.strip())
        if not m:
            continue
        nxt = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
        if not re.match(r"^\*[^*]+\*\s*$", nxt):
            missing.append(Path(m.group(1).strip()).name)
    return missing


def loose_part_headings(output_text: str) -> list[str]:
    out = []
    for line in output_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("PART ") and not stripped.startswith("#"):
            out.append(stripped)
    return out


def part_token_hits(output_text: str) -> list[str]:
    hits = []
    for line in output_text.splitlines():
        if re.search(r"\bPART\b", line):
            hits.append(line.strip())
    return hits


def image_order_mismatches(expected: list[str], refs: list[str]) -> list[dict]:
    mismatches = []
    for idx, (want, got) in enumerate(zip(expected, refs), start=1):
        if want != got:
            mismatches.append({"position": idx, "expected": want, "actual": got})
    return mismatches


def expected_images(prompt_text: str) -> list[str]:
    names = re.findall(r"(?<![\w.-])([A-Za-z0-9_-]+\.(?:png|jpe?g|webp|gif))(?![\w.-])", prompt_text, re.I)
    seen = set()
    out = []
    for name in names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def body_image_refs(output_text: str) -> list[str]:
    refs = []
    for _, path in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", output_text):
        refs.append(Path(path.strip()).name)
    return refs


def has_preface(output_text: str) -> bool:
    first = output_text.strip().splitlines()[0].strip() if output_text.strip() else ""
    return not (first in {"正文", "## 正文", "**正文**"} or first.startswith("# "))


def section_present(output_text: str, keyword: str) -> bool:
    return keyword in output_text


def pattern_hits(patterns: list[str], text: str) -> list[str]:
    return [p for p in patterns if re.search(p, text, re.M)]


def score(prompt_text: str, output_text: str) -> dict:
    expected = expected_images(prompt_text)
    refs = body_image_refs(output_text)
    missing = [name for name in expected if name not in refs]
    extra_refs = [name for name in refs if expected and name not in expected]

    process_hits = pattern_hits(PROCESS_PATTERNS, output_text)
    fake_hits = pattern_hits(FAKE_ACTION_PATTERNS, output_text)
    ai_flavor_hits = pattern_hits(AI_FLAVOR_PATTERNS, output_text)
    hard_sales_hits = pattern_hits(HARD_SALES_PATTERNS, output_text)
    unsupported_claim_hits = pattern_hits(UNSUPPORTED_CLAIM_PATTERNS, output_text)
    uncaptioned = uncaptioned_body_images(output_text)
    loose_parts = loose_part_headings(output_text)
    part_hits = part_token_hits(output_text)
    order_mismatches = image_order_mismatches(expected, refs) if expected else []
    has_subtitle = section_present(output_text, "副标题")
    has_mapping = section_present(output_text, "图文对照")
    has_todo = section_present(output_text, "待确认")

    points = 100
    if has_preface(output_text):
        points -= 12
    points -= min(30, len(missing) * 3)
    points -= min(15, len(process_hits) * 8)
    points -= min(15, len(fake_hits) * 10)
    points -= min(24, len(ai_flavor_hits) * 4)
    points -= min(18, len(hard_sales_hits) * 6)
    points -= min(24, len(unsupported_claim_hits) * 6)
    points -= min(18, len(uncaptioned) * 2)
    points -= min(16, len(loose_parts) * 4)
    points -= min(20, len(part_hits) * 3)
    points -= min(16, len(order_mismatches) * 4)
    if not has_subtitle:
        points -= 10
    if not has_mapping:
        points -= 10
    if not has_todo:
        points -= 5
    if "PART " in output_text and not re.search(r"(?m)^#{1,3}\s*(?:\d+\s*)?PART\s+\d+", output_text):
        points -= 8

    return {
        "score": max(points, 0),
        "expected_image_count": len(expected),
        "body_image_count": len(refs),
        "missing_body_images": missing,
        "extra_body_images": extra_refs,
        "has_preface_or_process_lead": has_preface(output_text),
        "process_pattern_hits": process_hits,
        "fake_action_hits": fake_hits,
        "ai_flavor_hits": ai_flavor_hits,
        "hard_sales_hits": hard_sales_hits,
        "unsupported_claim_hits": unsupported_claim_hits,
        "uncaptioned_body_images": uncaptioned,
        "loose_part_headings": loose_parts,
        "part_token_hits": part_hits,
        "image_order_mismatches": order_mismatches,
        "has_subtitle": has_subtitle,
        "has_image_mapping": has_mapping,
        "has_todo": has_todo,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt")
    parser.add_argument("--expected-images", help="Comma-separated expected image filenames.")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.prompt:
        prompt_text = Path(args.prompt).read_text(encoding="utf-8", errors="replace")
    else:
        names = [x.strip() for x in (args.expected_images or "").split(",") if x.strip()]
        prompt_text = "\n".join(names)
    output_text = Path(args.output).read_text(encoding="utf-8", errors="replace")
    print(json.dumps(score(prompt_text, output_text), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
