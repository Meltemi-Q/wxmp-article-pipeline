#!/usr/bin/env python3
"""像不像用户本人：按文章类型对照口吻。

自动化验收走 aigc_check.sh，口吻是过检方法。两个都要。
为过检硬贴口头禅，检测和像他都会掉——8/14 数据文加「说白了」就是。

用法:
  python3 scripts/voice_match.py --target drafts/.../article.md
  python3 scripts/voice_match.py --target a.md --scene data
  python3 scripts/voice_match.py --compare like.md unlike.md
  python3 scripts/voice_match.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DELIVERY = re.compile(r"(副标题|图文对照|待确认项|待确认：)")

# 长文实测：8/15 发布版 + 8/16 v5 里真正出现过的反应句
STORY_LIKE = [
    "这家伙",
    "话不多说",
    "咱们现在开始",
    "哎实在没办法",
    "那我来吧",
    "然后没想到",
    "挺香",
    "好嘛",
    "就这",
    "弄好了",
    "还是得我",
    "根本过不去",
    "随口问",
    "完全 ok",
    "咔咔",
    "那验证啰",
]

# 数据复盘：8/14 原稿自己的判断句，不是朋友圈口头禅
DATA_LIKE = [
    "这意味着啥",
    "不是的",
    "这还没完",
    "有好的该夸夸",
    "不咋地的点",
    "我看看",
    "对对",
    "这个靠谱",
]

# 贴图：短、清单、一句判断
NEWSPIC_LIKE = [
    "就是因为它不懂你",
    "赶紧多挖",
    "一定是可以",
]

# 教程：一步一图，不要发明新口头禅
TUTORIAL_LIKE = [
    "一步步",
    "别怕",
    "没想到还真成了",
    "试水",
    "嚯个茶",
]

# 贴到错类型上，既不像他，朱雀也更差
DATA_WRONG = [
    "说白了",
    "话不多说",
    "哎实在没办法",
    "这家伙",
    "咱们现在开始",
    "那验证啰",
]

EXPLAIN = [
    "它查了",
    "回来说",
    "它解释了",
    "它马上切",
    "掰开讲",
    "它先回",
    "摸完一圈",
    "它捋的逻辑",
    "以它的脑子",
    "它会先想",
    "查完跟我说",
    "它翻出",
    "它建了",
]

AI_PHRASE = [
    "从本质上",
    "综上所述",
    "值得注意的是",
    "具有重要的实践意义",
    "我们正在进入",
    "未来的样子",
    "这意味着我们",
    "可以这样收",
    "把这条链路打通",
    "在这个 AI 时代",
]

# 语料库和发布版里几乎没有，是模型编的「像人」
FAKE_ORAL = [
    "香哈哈",
    "奈斯",
    "嘎嘎香",
    "贼拉香",
    "太香了捏",
]

OVERUSE = {
    "成了": 3,
    "说白了": 1,
    "哈哈": 3,
    "这意味着啥": 4,
    "咱们": 3,
}

SCENE_HINTS = {
    "data": ["这意味着啥", "柱状图", "中位数", "四张图", "近九成", "1万7千"],
    "tutorial": ["一步步", "附教程", "复制进去", "先在屏幕", "左下角搜索"],
    "newspic": ["#AI", "#宇龙", "1️⃣"],
}


def strip_delivery(text: str) -> str:
    m = DELIVERY.search(text)
    return text[: m.start()] if m else text


def detect_scene(text: str, article_type: str = "news") -> str:
    if article_type == "newspic":
        return "newspic"
    body = strip_delivery(text)
    compact = re.sub(r"\s", "", body)
    if len(compact) < 600 and re.search(r"#\w", body):
        return "newspic"
    scores = {k: sum(1 for h in hints if h in body) for k, hints in SCENE_HINTS.items()}
    best = max(scores, key=scores.get)
    if scores[best] >= 2:
        return best
    if scores["data"] >= 1 and "这意味着啥" in body:
        return "data"
    if scores["tutorial"] >= 1 and re.search(r"```", body):
        return "tutorial"
    return "story"


def like_lexicon(scene: str) -> list[str]:
    return {
        "story": STORY_LIKE,
        "data": DATA_LIKE,
        "newspic": NEWSPIC_LIKE,
        "tutorial": TUTORIAL_LIKE,
    }.get(scene, STORY_LIKE)


def found(text: str, phrases: list[str]) -> list[str]:
    return [p for p in phrases if p in text]


def count_phrase(text: str, phrase: str) -> int:
    if phrase == "成了":
        return len(re.findall(r"(?:「成了」|成了[。，！\s])", text))
    return text.count(phrase)


def strip_quotes(text: str) -> str:
    """引号里常是反例（「首先、其次、综上所述」），不当正文口气。"""
    return re.sub(r"「[^」]*」|“[^”]*”|\"[^\"]*\"", "", text)


def assess(text: str, scene: str = "auto", article_type: str = "news") -> dict:
    body = strip_delivery(text)
    if scene == "auto":
        scene = detect_scene(body, article_type)
    bare = strip_quotes(body)

    like = found(body, like_lexicon(scene))
    explain = found(bare, EXPLAIN)
    ai = found(bare, AI_PHRASE)
    fake = found(body, FAKE_ORAL)
    wrong: list[str] = []
    if scene == "data":
        wrong = found(bare, DATA_WRONG)

    overuse = []
    for phrase, limit in OVERUSE.items():
        n = count_phrase(body, phrase)
        if n > limit:
            overuse.append(f"{phrase}×{n}>{limit}")

    # 长文里「说白了」只许当短判断出现一次；数据文已经算 wrong
    if scene == "story" and body.count("说白了") > 1:
        overuse.append("说白了×%d>1" % body.count("说白了"))

    hits: list[str] = []
    for p in wrong:
        hits.append(f"错类型口头禅「{p}」（数据复盘不要贴长文/社群口气）")
    for p in explain:
        hits.append(f"解说腔「{p}」")
    for p in ai:
        hits.append(f"书面/总结腔「{p}」")
    for p in fake:
        hits.append(f"编出来的口头禅「{p}」（语料里几乎没有）")
    for item in overuse:
        hits.append(f"同词堆砌 {item}")

    score = 60
    score += 6 * min(len(like), 5)
    score -= 10 * len(wrong)
    score -= 8 * len(explain)
    score -= 6 * len(ai)
    score -= 10 * len(fake)
    score -= 6 * len(overuse)
    if scene in {"story", "data"} and not like and not hits:
        score -= 8
        hits.append("对上的本人口气太少，先跑 voice_fewshot.py 再写反应句")
    score = max(0, min(100, score))

    if fake:
        verdict = "UNLIKE"
    elif hits:
        verdict = "UNLIKE" if score < 55 else "MIXED"
    elif score >= 72:
        verdict = "LIKE"
    elif score >= 48:
        verdict = "MIXED"
    else:
        verdict = "UNLIKE"

    return {
        "scene": scene,
        "score": score,
        "verdict": verdict,
        "like": like,
        "wrong_scene": wrong,
        "explain": explain,
        "ai": ai,
        "fake_oral": fake,
        "overuse": overuse,
        "hits": hits,
        "note": "aigc_check 要过；过检靠像他写的，不要为刷分改口气",
    }


def print_report(path: str, result: dict) -> None:
    print(f"# 口吻对照  {path}")
    print(f"scene={result['scene']}  score={result['score']}  verdict={result['verdict']}")
    print(f"对上的口气: {', '.join(result['like']) or '（无）'}")
    if result["hits"]:
        print("要改：")
        for h in result["hits"]:
            print(f"  - {h}")
    else:
        print("要改：无")
    print(result["note"])


KNOWN = {
    "d-816-v5": (
        Path.home() / "Documents/yulong/weixin-write/drafts/2026-08-16-grok-bot-wechat/article.md",
        "LIKE",
    ),
    "p-815-grok": (
        Path.home()
        / "Documents/yulong/weixin-write/archives/yulong-ai/published-2026-08-15-grok-bot-claude/content.md",
        "LIKE",
    ),
    "d-814-orig": (
        Path.home() / "Documents/yulong/weixin-write/drafts/2026-08-14-wechat-self-portrait/article.md",
        "LIKE",
    ),
    "d-814-v2": (
        Path.home() / "Documents/yulong/weixin-write/drafts/2026-08-17-zhuque-ablation/long-wechat4w-v2.md",
        "MIXED",
    ),
    "d-816-grokcli": (
        Path.home() / "Documents/yulong/weixin-write/drafts/2026-08-16-grok-bot-wechat-grokcli/article.md",
        "UNLIKE",
    ),
    "d-kindle": (
        Path.home() / "Documents/yulong/weixin-write/drafts/2026-06-03-kindle-ai-skill/article.md",
        "UNLIKE",
    ),
    "d-win": (
        Path.home() / "Documents/yulong/weixin-write/drafts/2026-06-22-windows-openclaw/article.md",
        "UNLIKE",
    ),
}


def selftest() -> int:
    rows = []
    failed = 0
    for name, (path, expect) in KNOWN.items():
        if not path.exists():
            print(f"SKIP {name} missing {path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        result = assess(text)
        ok = result["verdict"] == expect
        if not ok:
            failed += 1
        mark = "OK" if ok else "FAIL"
        rows.append((mark, name, result))
        print(
            f"{mark:4s} {name:16s} expect={expect:6s} got={result['verdict']:6s} "
            f"score={result['score']:3d} scene={result['scene']} like={result['like']}"
        )
        if result["hits"]:
            print("     " + " | ".join(result["hits"][:4]))
    by_name = {name: r for _, name, r in rows}
    if "d-814-orig" in by_name and "d-814-v2" in by_name:
        a, b = by_name["d-814-orig"]["score"], by_name["d-814-v2"]["score"]
        if a <= b:
            failed += 1
            print(f"FAIL rank 814-orig {a} should beat 814-v2 {b}")
        else:
            print(f"OK   rank 814-orig {a} > 814-v2 {b}")
    if "d-816-v5" in by_name and "d-816-grokcli" in by_name:
        a, b = by_name["d-816-v5"]["score"], by_name["d-816-grokcli"]["score"]
        if a <= b:
            failed += 1
            print(f"FAIL rank 816-v5 {a} should beat grokcli {b}")
        else:
            print(f"OK   rank 816-v5 {a} > grokcli {b}")
    print(f"failed={failed}")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="按类型对照口吻，像不像用户本人")
    ap.add_argument("--target")
    ap.add_argument("--scene", default="auto", choices=["auto", "story", "data", "newspic", "tutorial"])
    ap.add_argument("--article-type", default="news", choices=["news", "newspic"])
    ap.add_argument("--compare", nargs=2, metavar=("LIKE", "UNLIKE"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.compare:
        texts = []
        for p in args.compare:
            t = Path(p).read_text(encoding="utf-8", errors="replace")
            r = assess(t, scene=args.scene, article_type=args.article_type)
            texts.append((p, r))
            if not args.json:
                print_report(p, r)
                print()
        if args.json:
            print(json.dumps({p: r for p, r in texts}, ensure_ascii=False, indent=2))
        return 0

    if not args.target:
        ap.print_help()
        return 2

    text = Path(args.target).read_text(encoding="utf-8", errors="replace")
    result = assess(text, scene=args.scene, article_type=args.article_type)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(args.target, result)
    return 0 if result["verdict"] != "UNLIKE" else 1


if __name__ == "__main__":
    sys.exit(main())
