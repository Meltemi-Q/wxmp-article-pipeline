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


def score(prompt_text: str, output_text: str) -> dict:
    expected = expected_images(prompt_text)
    refs = body_image_refs(output_text)
    missing = [name for name in expected if name not in refs]
    extra_refs = [name for name in refs if expected and name not in expected]

    process_hits = [p for p in PROCESS_PATTERNS if re.search(p, output_text, re.M)]
    fake_hits = [p for p in FAKE_ACTION_PATTERNS if re.search(p, output_text)]
    has_subtitle = section_present(output_text, "副标题")
    has_mapping = section_present(output_text, "图文对照")
    has_todo = section_present(output_text, "待确认")

    points = 100
    if has_preface(output_text):
        points -= 12
    points -= min(30, len(missing) * 3)
    points -= min(15, len(process_hits) * 8)
    points -= min(15, len(fake_hits) * 10)
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
