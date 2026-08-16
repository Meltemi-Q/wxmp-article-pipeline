#!/usr/bin/env python3
"""风格指纹对比：待检文本 vs 用户发布版基准，输出可量化的偏差项。

用法:
  python3 style_fingerprint.py --baseline a.txt b.txt c.txt --target draft.txt [--json out.json]

输入为纯文本（一行一段，图注也算一行）。维度覆盖：
  句长/段长分布与波动（burstiness）、段尾标点、每百字标点、语气词、
  段首模式化、引号密度、emoji、数字密度、字符 bigram 多样性。

设计目的：AI 稿的「统计均匀性」是主要 AI 特征；本工具找出待检文本
相对用户真实发布版「过于均匀 / 过于规整」的维度，指导去均匀化改写。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path

TONE_CHARS = "啊哈嘛呢吧呀啰嗐嘿哦诶咯喽哇"
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF]"
)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？!?…]+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 2]


def cv(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = statistics.mean(values)
    return statistics.stdev(values) / m if m else 0.0


def fingerprint(text: str) -> dict:
    paras = [ln.strip() for ln in text.splitlines() if ln.strip()]
    sents = split_sentences(text)
    chars = re.sub(r"\s", "", text)
    n = len(chars) or 1

    sent_lens = [len(s) for s in sents]
    para_lens = [len(p) for p in paras]

    def per100(pattern: str) -> float:
        return len(re.findall(pattern, text)) * 100.0 / n

    para_end_period = sum(1 for p in paras if p.endswith("。")) / (len(paras) or 1)
    para_end_puncts = sum(1 for p in paras if p[-1] in "。！？…～") / (len(paras) or 1)

    first_chars = [p[0] for p in paras]
    fc = Counter(first_chars)
    top_first_ratio = fc.most_common(1)[0][1] / (len(paras) or 1) if fc else 0
    same_start_adjacent = sum(
        1 for a, b in zip(first_chars, first_chars[1:]) if a == b
    ) / (max(len(paras) - 1, 1))

    bigrams = [chars[i : i + 2] for i in range(len(chars) - 1)]
    bigram_ttr = len(set(bigrams)) / (len(bigrams) or 1)

    return {
        "chars": n,
        "para_count": len(paras),
        "sent_mean_len": round(statistics.mean(sent_lens), 1) if sent_lens else 0,
        "sent_len_cv": round(cv(sent_lens), 3),
        "para_mean_len": round(statistics.mean(para_lens), 1) if para_lens else 0,
        "para_len_cv": round(cv(para_lens), 3),
        "para_end_period_ratio": round(para_end_period, 3),
        "para_end_any_punct_ratio": round(para_end_puncts, 3),
        "comma_per100": round(per100("，"), 2),
        "period_per100": round(per100("。"), 2),
        "question_per100": round(per100("[？?]"), 2),
        "exclaim_per100": round(per100("[！!]"), 2),
        "dunhao_per100": round(per100("、"), 2),
        "colon_per100": round(per100("[：:]"), 2),
        "quote_per100": round(per100("[「」]"), 2),
        "dash_ellipsis_per100": round(per100("——|……"), 2),
        "tone_char_per100": round(per100(f"[{TONE_CHARS}]"), 2),
        "emoji_count": len(EMOJI_RE.findall(text)),
        "digit_per100": round(per100(r"\d"), 2),
        "top_first_char_ratio": round(top_first_ratio, 3),
        "same_start_adjacent_ratio": round(same_start_adjacent, 3),
        "bigram_ttr": round(bigram_ttr, 3),
    }


def compare(baselines: list[dict], target: dict) -> list[dict]:
    """target 相对基准均值的偏差，按 z 值排序（基准间标准差为尺度）。"""
    keys = [k for k in target if k not in ("chars", "para_count", "emoji_count")]
    rows = []
    for k in keys:
        vals = [b[k] for b in baselines]
        m = statistics.mean(vals)
        sd = statistics.stdev(vals) if len(vals) > 1 else 0
        t = target[k]
        if sd > 1e-9:
            z = (t - m) / sd
        else:
            z = None
        rows.append(
            {
                "metric": k,
                "target": t,
                "baseline_mean": round(m, 3),
                "baseline_range": [round(min(vals), 3), round(max(vals), 3)],
                "z": round(z, 2) if z is not None else None,
                "off": (abs(z) > 2) if z is not None else (abs(t - m) > 0.05),
            }
        )
    rows.sort(key=lambda r: (r["z"] is None, -(abs(r["z"]) if r["z"] is not None else 0)))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", nargs="+", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--json")
    args = ap.parse_args()

    baselines = [fingerprint(Path(p).read_text(encoding="utf-8")) for p in args.baseline]
    target = fingerprint(Path(args.target).read_text(encoding="utf-8"))
    rows = compare(baselines, target)

    payload = {"target_fingerprint": target, "baseline_fingerprints": baselines, "diff": rows}
    if args.json:
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"target: {args.target}  ({target['chars']} chars, {target['para_count']} paras)")
    print(f"{'metric':28s} {'target':>8s} {'base_mean':>10s} {'base_range':>18s} {'z':>6s}  flag")
    for r in rows:
        rng = f"[{r['baseline_range'][0]}, {r['baseline_range'][1]}]"
        z = f"{r['z']:.2f}" if r["z"] is not None else "n/a"
        flag = "OFF" if r["off"] else ""
        print(f"{r['metric']:28s} {str(r['target']):>8s} {str(r['baseline_mean']):>10s} {rng:>18s} {z:>6s}  {flag}")


if __name__ == "__main__":
    main()
