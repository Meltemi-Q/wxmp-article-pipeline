#!/usr/bin/env python3
"""多模型综合评测与文章/Skill优化脚本。

调用模型弹药库（Claude 3.7 Sonnet / Opus 4.6 / GPT-4o / o1 / Kimi-k3 / Grok-3 / Gemini 2.0 等），
对草稿与 Skill 规则进行多维度评分、评审与深度改写建议。

用法:
  python3 multi_model_refine.py \
    --article drafts/2026-08-30-xiaowei-update-v2/article.md \
    --out-report drafts/2026-08-30-xiaowei-update-v2/multi-model-review.json
"""
import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DEFAULT_API_BASE = "https://gbot.iherai.online/v1"
DEFAULT_API_KEY = "sk-yulong-350842e5c28b49d8eb92d69641617674cf153c61"

MODELS_TO_EVALUATE = [
    {
        "name": "Claude Opus 4.6",
        "model_id": "claude-opus-4-6",
        "focus": "深度思考、商业价值与生态阳谋洞察提炼"
    },
    {
        "name": "Claude 3.7 Sonnet",
        "model_id": "claude-3.7-sonnet",
        "focus": "文章结构逻辑、去 AI 味与真人口吻微操建议"
    },
    {
        "name": "GPT-4o",
        "model_id": "gpt-4o",
        "focus": "爆款标题公式化生成、读者点击心理学与悬念设计"
    },
    {
        "name": "o1",
        "model_id": "o1",
        "focus": "技术严谨性、看图说话细节与防捏造约束"
    },
    {
        "name": "o3-mini",
        "model_id": "o3-mini",
        "focus": "逻辑推理与段落节奏优化"
    },
    {
        "name": "Kimi k3",
        "model_id": "kimi-k3",
        "focus": "中文语感、本土网络热梗与口语化节奏适配"
    },
    {
        "name": "Gemini 3.7 Flash",
        "model_id": "gemini-3.7-flash",
        "focus": "视觉信息提取、图文对照表与图注优化"
    }
]

SYSTEM_PROMPT = """你是一个顶级的公众号内容专家与内容审计官。
你的任务是依据宇龙（一位专注 AI Agent 场景落地的实战派创作者）的个人风格，对输入的公众号草稿进行极其严苛、接地气且富有建设性的多维度评审。

宇龙的核心口吻特征：
1. 真实、现场、动作感强（多用“手机上发一句”、“两只小眼睛”、“像模像样”、“这样婶儿的”、“白嫖程序员”、“脑阔痛”、“这点它还挺老实”）。
2. 极其排斥 AI 腔和空洞大词（杜绝“赋能”、“闭环”、“重塑生产力”、“范式颠覆”、“不仅而且”、“毋庸置疑”）。
3. 事实为本：数字、配置、账单严格以截图和真实数据为准，不夸张不吹嘘，少罗列枯燥百分比，多给轻量口语评价。
4. 标题短促有力、情绪拉满（如“又双叒叕”），小标题采用口语化自然编号 1、2、3、4、5。
5. 图注必须指引读者看图里的具体亮点，且末尾严格不加句号。

请根据你的专长领域，输出纯 JSON 格式的评审结果，字段包括：
{
  "expert_role": "你的评审侧重",
  "score_overall": 85,
  "score_voice_authenticity": 90,
  "score_viral_title": 88,
  "score_visual_caption": 86,
  "viral_title_candidates": [
    "5个极具吸引力、符合宇龙口吻的爆款标题方案（包含理由）"
  ],
  "caption_enhancements": [
    {"image_index": 1, "original": "原图注", "enhanced": "优化后极具人味且无句号的图注", "reason": "理由"}
  ],
  "voice_corrections": [
    {"original_sentence": "过于AI味或偏书面的原句", "user_style_sentence": "宇龙口吻改写", "critique": "点评"}
  ],
  "expansion_and_retention_rules": [
    "针对如何既保留作者原味又做高质量扩充的具体可落地规则（2-3条）"
  ],
  "summary_verdict": "一句话总体裁决与核心改进点"
}
请确保输出合法的 JSON 格式。"""

def extract_json(raw_text: str) -> dict:
    text = raw_text.strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except Exception:
            pass
    return {"raw_response": text}

def call_model(model_info: dict, article_text: str, api_base: str, api_key: str) -> dict:
    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = {
        "model": model_info["model_id"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请针对以下文章草稿进行专项评审（你的侧重点：{model_info['focus']}）：\n\n{article_text}"}
        ],
        "temperature": 0.7,
        "max_tokens": 4096
    }
    
    try:
        import requests
        resp = requests.post(url, headers=headers, json=payload, timeout=240)
        if resp.status_code != 200:
            return {
                "model_name": model_info["name"],
                "model_id": model_info["model_id"],
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}"
            }
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        parsed = extract_json(content)
        parsed["model_name"] = model_info["name"]
        parsed["model_id"] = model_info["model_id"]
        return parsed
    except Exception as e:
        return {
            "model_name": model_info["name"],
            "model_id": model_info["model_id"],
            "error": str(e)
        }

def main():
    parser = argparse.ArgumentParser(description="多模型文章与Skill综合评测工具")
    parser.add_argument("--article", required=True, help="待评测的 Markdown 文章路径")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="API Base URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API Key")
    parser.add_argument("--out-report", default="multi-model-review.json", help="输出评测报告路径")
    args = parser.parse_args()

    article_path = Path(args.article)
    if not article_path.exists():
        print(f"❌ 文章文件不存在: {article_path}")
        sys.exit(1)

    article_text = article_path.read_text(encoding="utf-8")
    print(f"🚀 开始调用 {len(MODELS_TO_EVALUATE)} 个顶级模型并发评测...")

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(call_model, m, article_text, args.api_base, args.api_key): m
            for m in MODELS_TO_EVALUATE
        }
        for future in as_completed(futures):
            m_info = futures[future]
            try:
                res = future.result()
                results.append(res)
                status = "✅ 成功" if "error" not in res else f"❌ 失败: {res.get('error')}"
                print(f"  [{m_info['name']}] {status}")
            except Exception as exc:
                print(f"  [{m_info['name']}] ❌ 异常: {exc}")

    out_file = Path(args.out_report)
    out_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📊 评测完成！综合评审报告已保存至: {out_file}")

if __name__ == "__main__":
    main()
