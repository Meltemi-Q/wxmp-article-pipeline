#!/usr/bin/env python3
"""腾讯云文本内容安全 · AI 生成识别（TEXT_AIGC）。

比网页朱雀稳：无验证码、走官方 API。不是开源，要开通套餐。
密钥只读环境变量，不要写进仓库或本目录。

环境变量:
  TENCENTCLOUD_SECRET_ID
  TENCENTCLOUD_SECRET_KEY
  TMS_BIZTYPE          控制台「AI 生成检测配套策略」里的 BizType
  TMS_REGION           默认 ap-guangzhou

用法:
  python3 scripts/tencent_tms_aigc.py 正文.txt
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="腾讯云 TEXT_AIGC（可选）")
    ap.add_argument("file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    sid = os.environ.get("TENCENTCLOUD_SECRET_ID", "").strip()
    sk = os.environ.get("TENCENTCLOUD_SECRET_KEY", "").strip()
    biz = os.environ.get("TMS_BIZTYPE", "").strip()
    region = os.environ.get("TMS_REGION", "ap-guangzhou").strip()
    if not sid or not sk or not biz:
        print(
            "SKIP: 未开通腾讯云 TEXT_AIGC。需要环境变量 "
            "TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY / TMS_BIZTYPE"
        )
        return 10

    try:
        from tencentcloud.common import credential
        from tencentcloud.tms.v20201229 import models, tms_client
    except ImportError:
        print("SKIP: 先 pip3 install tencentcloud-sdk-python-tms")
        return 10

    text = Path(args.file).read_text(encoding="utf-8", errors="replace").strip()
    if len(text) < 80:
        print("FAIL: 文本太短")
        return 2

    cred = credential.Credential(sid, sk)
    client = tms_client.TmsClient(cred, region)
    req = models.TextModerationRequest()
    req.Content = base64.b64encode(text.encode("utf-8")).decode("ascii")
    req.BizType = biz
    req.Type = "TEXT_AIGC"
    req.SourceLanguage = "zh"
    resp = client.TextModeration(req)
    payload = json.loads(resp.to_json_string())
    suggestion = payload.get("Suggestion") or ""
    score = payload.get("Score")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"RESULT: {suggestion}  score={score}  engine=tencent-tms-TEXT_AIGC")
    if suggestion == "Pass":
        return 0
    if suggestion == "Review":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
