#!/usr/bin/env python3
"""删除微信草稿箱草稿（经 VPS，供链路测试/误推回滚用）。

本机直连微信 API 会 40164（IP 不在白名单），与 push_via_vps.py 同理走 ssh vps。
删除后自动用 draft/get 反查确认草稿已消失。

支持两种用法：
  单个删除：--media-id <draft_media_id>（可重复多个）
  登记批量删除：--registry <jsonl路径>
    每行一个 JSON：{"media_id": "...", "title": "...", ...}（至少含 media_id）
    或纯文本一行一个 media_id。测试推送后往该文件追加登记，验收完统一清理。
    全部删除成功后会清空该文件。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REMOTE_SNIPPET = r"""
import json, sys, urllib.request
sys.path.insert(0, "/root/.openclaw/skills/wxmp-article-pipeline/scripts")
from pathlib import Path
from push_article import resolve_credentials, get_access_token

appid, secret = resolve_credentials(Path("/root/.openclaw/secrets/wxmp-{account}.env"))
token = get_access_token(appid, secret)
mids = json.loads('{mids_json}')

def call(api, payload):
    req = urllib.request.Request(
        f"https://api.weixin.qq.com/cgi-bin/{{api}}?access_token={{token}}",
        data=json.dumps(payload).encode(),
        headers={{"Content-Type": "application/json"}})
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())

results = []
for mid in mids:
    r = call("draft/delete", {{"media_id": mid}})
    ok = r.get("errcode") == 0
    verified_gone = False
    if ok:
        check = call("draft/get", {{"media_id": mid}})
        verified_gone = bool(check.get("errcode") or not check.get("news_item"))
    results.append({{"media_id": mid, "delete": r, "verified_gone": verified_gone}})
    print("RESULT", json.dumps(results[-1], ensure_ascii=False))
print("SUMMARY", json.dumps({{"total": len(mids), "deleted": sum(1 for x in results if x["delete"].get("errcode") == 0), "verified": sum(1 for x in results if x["verified_gone"])}}, ensure_ascii=False))
"""


def collect_media_ids(args) -> tuple[list[str], Path | None]:
    ids: list[str] = list(args.media_id or [])
    registry: Path | None = None
    if args.registry:
        registry = Path(args.registry)
        if not registry.exists():
            print(f"❌ registry 不存在: {registry}")
            sys.exit(1)
        for line in registry.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ids.append(json.loads(line)["media_id"])
            except (json.JSONDecodeError, KeyError, TypeError):
                ids.append(line)  # 纯文本一行一个 id
    seen, uniq = set(), []
    for m in ids:
        if m and m not in seen:
            seen.add(m)
            uniq.append(m)
    return uniq, registry


def main() -> int:
    parser = argparse.ArgumentParser(description="经 VPS 删除微信草稿箱草稿（支持批量登记清理）")
    parser.add_argument("--media-id", action="append", help="draft media_id，可重复")
    parser.add_argument("--registry", help="测试推送登记文件（jsonl 或每行一个 media_id），删完清空")
    parser.add_argument("--account", default="yulong")
    parser.add_argument("--vps", default="vps")
    args = parser.parse_args()

    mids, registry = collect_media_ids(args)
    if not mids:
        parser.error("需要 --media-id 或 --registry")

    snippet = REMOTE_SNIPPET.format(
        account=args.account,
        mids_json=json.dumps(mids).replace("'", "\\'"))
    remote = "python3 - <<'PYEOF'\n" + snippet + "\nPYEOF"
    proc = subprocess.run(["ssh", args.vps, remote], capture_output=True, text=True, timeout=180)
    sys.stdout.write(proc.stdout)
    if proc.stderr.strip():
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        print(f"❌ 删除失败: ssh 退出码 {proc.returncode}")
        return proc.returncode

    all_ok = True
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            r = json.loads(line[7:])
            mid = r["media_id"]
            if r["delete"].get("errcode") == 0 and r["verified_gone"]:
                print(f"✅ {mid[:40]}… 已删除并确认消失")
            else:
                all_ok = False
                print(f"⚠️ {mid[:40]}… delete={r['delete']} verified_gone={r['verified_gone']}")
    if all_ok and registry:
        registry.write_text("")
        print(f"🧹 已清空登记文件: {registry}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
