#!/usr/bin/env python3
"""多模型交叉盲审竞技场与互相打分系统 (Cross-Model Arena & Peer Review)。

工作流程:
  Phase 1: 各模型独立生成内容优化提案 (Proposals)
  Phase 2: 匿名化打乱各模型提案 (Candidate A, B, C, D...)，交叉分发给所有模型裁判进行盲审打分
  Phase 3: 聚合评分矩阵，生成天梯排行榜与黄金标准样本

用法:
  python3 cross_model_arena.py \
    --article drafts/2026-08-30-xiaowei-update-v2/article.md \
    --out-json drafts/2026-08-30-xiaowei-update-v2/arena-report.json \
    --out-md drafts/2026-08-30-xiaowei-update-v2/arena-leaderboard.md
"""
import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DEFAULT_API_BASE = "https://gbot.iherai.online/v1"
DEFAULT_API_KEY = "sk-yulong-350842e5c28b49d8eb92d69641617674cf153c61"

ARENA_MODELS = [
    {
        "id": "claude-4.8-opus",
        "name": "Claude Opus 4.8",
        "role": "顶级深度思考与商业阳谋裁判"
    },
    {
        "id": "claude-fable-5",
        "name": "Claude Fable 5",
        "role": "前沿叙事与逻辑张力裁判"
    },
    {
        "id": "claude-5-opus",
        "name": "Claude 5 Opus",
        "role": "终极去AI味与真人口吻裁判"
    },
    {
        "id": "kimi-k3",
        "name": "Kimi k3",
        "role": "中文语感与本土网络梗裁判"
    },
    {
        "id": "gemini-3.7-flash",
        "name": "Gemini 3.7 Flash",
        "role": "多模态视觉细节与图注焦点裁判"
    },
    {
        "id": "claude-opus-4-6",
        "name": "Claude Opus 4.6",
        "role": "生态洞察与降维打击分析裁判"
    },
    {
        "id": "o1",
        "name": "o1",
        "role": "技术严谨性与事实抓地力裁判"
    }
]

PROPOSAL_PROMPT = """你现在是宇龙（专注 AI Agent 场景落地的实战派创作者）。
请依据你对宇龙真实口吻的理解（真实动作感强、多用“两只小眼睛/白嫖程序员/脑阔痛/这点它还挺老实”、严禁公关大词和虚浮吹捧、注重事实与数字反差），对输入的文章草稿给出你的最佳改写提案。

请输出合法的纯 JSON 格式：
{
  "titles": [
    "3个短促有力、情绪拉满、极具点开欲望的爆款标题"
  ],
  "captions": [
    {"img_num": 1, "caption": "极其传神、指向图中亮点的口语化图注（严格无句号）"},
    {"img_num": 2, "caption": "极其传神、指向图中亮点的口语化图注（严格无句号）"},
    {"img_num": 3, "caption": "极其传神、指向图中亮点的口语化图注（严格无句号）"}
  ],
  "section_headings": [
    "3个精简有力的自然口语小标题（如：## 2 十一年微信支付账单盘一盘）"
  ],
  "ecosystem_insight": "一段2-3句话的宇龙式深度生态阳谋/商业洞察（不讲大词，用'你细品/这步棋下得挺狠'等大白话讲透背后价值）",
  "call_to_action": "一个带有明确动作和悬念的文末互动引导语（如：让读者查第一年账单金额发评论区）"
}
请确保输出合法的 JSON 格式。"""

JUDGE_PROMPT = """你是一个极其严苛、毒舌且富有专业敏锐度的公众号内容审计总监。
下面是若干个由不同创作者匿名提交的公众号优化提案（Candidate A, B, C, D...）。
目标作者是宇龙（专注 AI Agent 场景落地的实战创作者，核心特征：极简、大白话、动作感、排斥一切AI套话公关词、喜欢用'像模像样/脑阔痛/挺老实/白嫖'）。

请对每一个 Candidate 依据以下 5 项标准严苛打分（各项 1-100 分），并给出犀利的点评：
1. 宇龙真人语感与口头禅还原度 (权重 25%)
2. 彻底去AI味与大词排斥度 (权重 25%)
3. 读者点击欲与悬念设计 (权重 20%)
4. 视觉细节与动作事实抓地力 (权重 20%)
5. 商业洞察与深度思考增量 (权重 10%)

请输出纯 JSON 格式：
{
  "judge_name": "你的模型名称",
  "candidate_scores": {
    "Candidate_A": {
      "score_voice": 88,
      "score_anti_ai": 90,
      "score_click_hook": 85,
      "score_fact_focus": 87,
      "score_insight": 86,
      "total_weighted_score": 87.3,
      "critique": "优点与致命毒舌缺点点评"
    }
  },
  "best_candidate": "Candidate_X",
  "reason_for_best": "为什么这个方案最符合宇龙风格"
}
请确保输出合法的 JSON 格式。"""


def call_api(model_id: str, system_prompt: str, user_content: str, api_base: str, api_key: str, timeout: int = 120) -> dict:
    import requests
    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.7,
        "max_tokens": 4096
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:150]}"}
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        # 清除 markdown 标记
        cleaned = re.sub(r'^```json\s*', '', content, flags=re.MULTILINE)
        cleaned = re.sub(r'^```\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'```$', '', cleaned, flags=re.MULTILINE)
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        return {"raw_text": content}
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="多模型交叉盲审竞技场")
    parser.add_argument("--article", required=True, help="文章 Markdown 路径")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("--out-json", default="arena-report.json")
    parser.add_argument("--out-md", default="arena-leaderboard.md")
    args = parser.parse_args()

    article_text = Path(args.article).read_text(encoding="utf-8")
    print(f"🏟️  【多模型盲审竞技场启动】参评模型: {len(ARENA_MODELS)} 个")

    # ----------------------------------------------------
    # Phase 1: 各模型生成提案
    # ----------------------------------------------------
    print("\n⚡ [Phase 1] 正在并发采集各模型的改写提案...")
    proposals = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_model = {
            executor.submit(call_api, m["id"], PROPOSAL_PROMPT, f"待优化文章：\n\n{article_text}", args.api_base, args.api_key): m
            for m in ARENA_MODELS
        }
        for future in as_completed(future_to_model):
            m = future_to_model[future]
            res = future.result()
            if "error" not in res and not res.get("error"):
                proposals[m["name"]] = res
                print(f"  ✅ [{m['name']}] 提案生成成功")
            else:
                print(f"  ⚠️ [{m['name']}] 提案跳过/超时: {res.get('error')}")

    if len(proposals) < 2:
        print("❌ 有效提案不足 2 个，无法展开交叉竞技")
        sys.exit(1)

    # ----------------------------------------------------
    # Phase 2: 匿名化并分发交叉盲审
    # ----------------------------------------------------
    print(f"\n🎭 [Phase 2] 已收集 {len(proposals)} 份提案，开始匿名化并分发交叉盲审...")
    candidate_keys = [f"Candidate_{chr(65 + idx)}" for idx in range(len(proposals))]
    model_to_candidate = {}
    candidate_to_model = {}
    anonymous_payload = {}

    for idx, (m_name, prop) in enumerate(proposals.items()):
        c_key = candidate_keys[idx]
        model_to_candidate[m_name] = c_key
        candidate_to_model[c_key] = m_name
        anonymous_payload[c_key] = prop

    blind_review_input = f"以下是匿名提交的各 Candidate 优化提案：\n\n{json.dumps(anonymous_payload, ensure_ascii=False, indent=2)}"

    reviews = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_judge = {
            executor.submit(call_api, m["id"], JUDGE_PROMPT, blind_review_input, args.api_base, args.api_key): m
            for m in ARENA_MODELS
        }
        for future in as_completed(future_to_judge):
            m = future_to_judge[future]
            res = future.result()
            if "error" not in res and "candidate_scores" in res:
                reviews[m["name"]] = res
                print(f"  🧑‍⚖️ [{m['name']}] 完成盲审打分与点评")
            else:
                print(f"  ⚠️ [{m['name']}] 盲审打分跳过: {res.get('error')}")

    # ----------------------------------------------------
    # Phase 3: 汇总天梯榜与黄金方案
    # ----------------------------------------------------
    print(f"\n🏆 [Phase 3] 正在汇总天梯榜与交叉打分矩阵...")
    leaderboard = {c_key: {"model_name": candidate_to_model[c_key], "scores": [], "critiques": []} for c_key in candidate_keys}

    for judge_name, rev in reviews.items():
        c_scores = rev.get("candidate_scores", {})
        for c_key, s_info in c_scores.items():
            if c_key in leaderboard and isinstance(s_info, dict):
                score = s_info.get("total_weighted_score") or (
                    s_info.get("score_voice", 80) * 0.25 +
                    s_info.get("score_anti_ai", 80) * 0.25 +
                    s_info.get("score_click_hook", 80) * 0.20 +
                    s_info.get("score_fact_focus", 80) * 0.20 +
                    s_info.get("score_insight", 80) * 0.10
                )
                leaderboard[c_key]["scores"].append(round(score, 1))
                if s_info.get("critique"):
                    leaderboard[c_key]["critiques"].append(f"[{judge_name}]: {s_info.get('critique')}")

    for c_key, data in leaderboard.items():
        if data["scores"]:
            data["avg_score"] = round(sum(data["scores"]) / len(data["scores"]), 2)
        else:
            data["avg_score"] = 0.0

    ranked = sorted(leaderboard.items(), key=lambda x: x[1]["avg_score"], reverse=True)

    # 生成 Markdown 报告
    md_lines = [
        "# 多模型交叉盲审竞技场天梯榜与黄金样本库 (Cross-Model Arena)",
        f"\n> 评测时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 参评模型: {len(proposals)} | 盲审裁判: {len(reviews)}",
        "\n## 🏅 一、模型综合天梯排行榜\n",
        "| 排名 | 匿名编号 | 模型选手 | 综合均分 | 得分明细 |",
        "|:---:|:---:|:---|:---:|:---|"
    ]

    for rank, (c_key, d) in enumerate(ranked, 1):
        medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"
        scores_str = ", ".join(str(s) for s in d["scores"])
        md_lines.append(f"| {medal} | `{c_key}` | **{d['model_name']}** | **{d['avg_score']}** | {scores_str} |")

    md_lines.append("\n---\n\n## 🌟 二、冠军模型方案与最佳实践提取\n")
    if ranked:
        top_c_key, top_data = ranked[0]
        top_model = top_data["model_name"]
        top_prop = proposals[top_model]
        md_lines.append(f"### 🏆 冠军选手: {top_model} (`{top_c_key}`) — 综合得分: {top_data['avg_score']}\n")
        md_lines.append("#### 📌 冠军爆款标题方案：")
        for t in top_prop.get("titles", []):
            md_lines.append(f"- **{t}**")
        md_lines.append("\n#### 📸 冠军图注设计：")
        for c in top_prop.get("captions", []):
            md_lines.append(f"- `图 {c.get('img_num')}`: *{c.get('caption')}*")
        md_lines.append(f"\n#### 💡 冠军深度生态阳谋洞察：\n> {top_prop.get('ecosystem_insight')}\n")
        md_lines.append(f"#### 🛎 冠军文末互动引导：\n> {top_prop.get('call_to_action')}\n")
        md_lines.append("\n#### 🧑‍⚖️ 裁判团核心点评摘录：")
        for crit in top_data["critiques"][:4]:
            md_lines.append(f"- {crit}")

    md_content = "\n".join(md_lines)
    Path(args.out_md).write_text(md_content, encoding="utf-8")
    
    report_data = {
        "ranked_leaderboard": ranked,
        "proposals": proposals,
        "reviews": reviews,
        "candidate_mapping": candidate_to_model
    }
    Path(args.out_json).write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n🎉 交叉竞技评测完成！")
    print(f"📊 Markdown 报告: {args.out_md}")
    print(f"📄 JSON 详细数据: {args.out_json}")


if __name__ == "__main__":
    main()
