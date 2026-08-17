#!/usr/bin/env python3
"""本机/VPS 可跑的中文 AIGC 检测（无验证码、无限额）。

模型：yuchuantian/AIGC_detector_zhv3 的 ONNX INT8
      Eslzzyl/aigc-detector-zh-onnx（~98MB，CPU 即可）
不是朱雀四档。流水线自动化走这里；朱雀网页只抽查。

用法:
  python3 scripts/aigc_detect.py 正文.txt
  python3 scripts/aigc_detect.py --text "一段中文"
  python3 scripts/aigc_detect.py --json 正文.txt
  python3 scripts/aigc_detect.py --batch a.txt b.txt
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MAX_LEN = 512
# 中文大约 1 字 ≈ 1 token；700 字窗口，重叠一半
WIN_CHARS = 700
WIN_STRIDE = 350
# 2026-08-17 用朱雀已测原文校准，不是朱雀四档
# 显著锚点: 30美元短评 ai=0.020；8/16 v5 正文 ai=0.108 / max=0.229
# 10个AI进群(未发现) mean=0.151 但 max=0.315，不能只看均值
ANCHOR_MEAN = 0.16
ANCHOR_MAX = 0.25
FAIL_MEAN = 0.55
FAIL_MAX = 0.90

DEFAULT_DIRS = [
    Path.home() / ".aigc-detector-zh-onnx",
    Path("/root/.aigc-detector-zh-onnx"),
    Path("/tmp/aigc-detector-zh-onnx"),
]
DELIVERY = re.compile(r"(副标题|图文对照|待确认项|待确认：)")

_TOKENIZER = None
_SESSION = None
_MODEL_KEY = None


def find_model(root: Path | None) -> tuple[Path, Path]:
    cands = [root] if root else []
    cands.extend(DEFAULT_DIRS)
    for d in cands:
        if not d:
            continue
        tok = d / "tokenizer.json"
        onnx = d / "onnx" / "model_quantized.onnx"
        if not onnx.exists():
            onnx = d / "model_quantized.onnx"
        if tok.exists() and onnx.exists():
            return tok, onnx
    raise SystemExit(
        "SKIP: 没找到模型。先跑 scripts/aigc_fetch_model.sh\n"
        "期望：~/.aigc-detector-zh-onnx/tokenizer.json 和 onnx/model_quantized.onnx"
    )


def plain_body(text: str) -> str:
    text = text or ""
    m = DELIVERY.search(text)
    if m:
        text = text[: m.start()]
    text = re.sub(r"!\[.*?\]\([^)]+\)", "", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.M)
    return text.strip()


def char_windows(text: str) -> list[str]:
    if len(text) <= WIN_CHARS:
        return [text]
    out = []
    start = 0
    while start < len(text):
        end = min(start + WIN_CHARS, len(text))
        out.append(text[start:end])
        if end == len(text):
            break
        start += WIN_STRIDE
    return out


def softmax2(logits) -> tuple[float, float]:
    import numpy as np

    x = np.asarray(logits, dtype=np.float64).reshape(-1)
    x = x - x.max()
    e = np.exp(x)
    p = e / e.sum()
    return float(p[0]), float(p[1])


def load_runtime(model_dir: Path | None = None):
    global _TOKENIZER, _SESSION, _MODEL_KEY
    tok_path, onnx_path = find_model(model_dir)
    key = f"{tok_path}:{onnx_path}"
    if _SESSION is not None and _MODEL_KEY == key:
        return _TOKENIZER, _SESSION
    from tokenizers import Tokenizer
    import onnxruntime as ort

    tokenizer = Tokenizer.from_file(str(tok_path))
    tokenizer.enable_truncation(max_length=MAX_LEN)
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    _TOKENIZER, _SESSION, _MODEL_KEY = tokenizer, sess, key
    return tokenizer, sess


def score_chunk(text: str, tokenizer, sess) -> tuple[float, float]:
    import numpy as np

    enc = tokenizer.encode(text)
    logits = sess.run(
        None,
        {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
            "token_type_ids": np.array([enc.type_ids], dtype=np.int64),
        },
    )[0]
    return softmax2(logits)


def detect(text: str, model_dir: Path | None = None) -> dict:
    text = plain_body(text)
    compact = re.sub(r"\s", "", text)
    if len(compact) < 80:
        raise SystemExit("FAIL: 文本太短，至少 80 字再测")

    tokenizer, sess = load_runtime(model_dir)
    chunks = []
    for i, piece in enumerate(char_windows(text)):
        human, ai = score_chunk(piece, tokenizer, sess)
        chunks.append({"i": i, "chars": len(piece), "human": round(human, 4), "ai": round(ai, 4)})

    mean_ai = sum(c["ai"] for c in chunks) / len(chunks)
    max_ai = max(c["ai"] for c in chunks)
    combo = 0.5 * mean_ai + 0.5 * max_ai
    if mean_ai <= ANCHOR_MEAN and max_ai <= ANCHOR_MAX:
        verdict, gate = "接近锚点", "pass"
    elif mean_ai >= FAIL_MEAN or max_ai >= FAIL_MAX:
        verdict, gate = "偏AI", "fail"
    else:
        verdict, gate = "中间", "review"
    return {
        "engine": "aigc-detector-zhv3-onnx",
        "chars": len(compact),
        "windows": len(chunks),
        "human": round(1.0 - mean_ai, 4),
        "ai": round(mean_ai, 4),
        "ai_max_window": round(max_ai, 4),
        "combo": round(combo, 4),
        "verdict": verdict,
        "gate": gate,
        "note": "自托管中文检测，不是朱雀四档。pass=接近 8/16 v5 / 短评锚点。",
        "chunks": chunks,
    }


def format_line(result: dict, name: str = "") -> str:
    prefix = f"{name}  " if name else ""
    return (
        f"{prefix}RESULT: {result['verdict']}  gate={result['gate']}  "
        f"ai={result['ai']:.3f}  max_win={result['ai_max_window']:.3f}  "
        f"combo={result.get('combo', 0):.3f}  windows={result['windows']}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="中文 AIGC 检测（CPU/ONNX）")
    ap.add_argument("file", nargs="?", help="正文纯文本或 article.md")
    ap.add_argument("--text")
    ap.add_argument("--model-dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--batch", nargs="+", help="一次测多篇，复用模型")
    args = ap.parse_args()
    model_dir = Path(args.model_dir) if args.model_dir else None

    if args.batch:
        rows = []
        for path in args.batch:
            p = Path(path)
            result = detect(p.read_text(encoding="utf-8", errors="replace"), model_dir)
            result["file"] = str(p)
            rows.append(result)
            if not args.json:
                print(format_line(result, p.name))
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if args.text:
        text = args.text
        name = ""
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8", errors="replace")
        name = Path(args.file).name
    else:
        ap.print_help()
        return 2
    result = detect(text, model_dir)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_line(result, name if args.file else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
