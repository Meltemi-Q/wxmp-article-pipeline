#!/usr/bin/env python3
"""把本机稿子拷到 VPS 再跑 push_article.py。

家宽 / Win 本机 IP 通常不在微信 API 白名单，直接 push 会 40164。
稿子继续在本机写，出口走已经在白名单里的 VPS。

用法与 push_article.py 对齐：

  python push_via_vps.py \
    --markdown article-push.md \
    --images images/a.png \
    --title "标题" \
    --cover images/a.png \
    --theme green \
    --author 宇龙 \
    --digest "摘要"
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from pathlib import Path


def run(cmd: list[str]) -> None:
    printable = " ".join(cmd)
    print(f"+ {printable}")
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="经 VPS 推微信草稿箱，绕过本机 IP 白名单")
    parser.add_argument("--markdown", required=True)
    parser.add_argument("--images", nargs="+", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--cover", required=True)
    parser.add_argument("--author", default="宇龙")
    parser.add_argument("--digest", default="")
    parser.add_argument("--theme", default="green", choices=["rainbow", "purple", "blue", "green"])
    parser.add_argument("--vps", default="vps", help="ssh Host，默认 vps")
    parser.add_argument(
        "--remote-script",
        default="/root/.openclaw/skills/wxmp-article-pipeline/scripts/push_article.py",
    )
    parser.add_argument("--report-file", default="push-report.json")
    args = parser.parse_args()

    md = Path(args.markdown)
    cover = Path(args.cover)
    images = [Path(p) for p in args.images]
    for path in [md, cover, *images]:
        if not path.exists():
            print(f"❌ 文件不存在: {path}")
            return 1

    stamp = time.strftime("%Y%m%d-%H%M%S")
    remote_dir = f"/tmp/wxmp-win-push-{stamp}"
    run(["ssh", args.vps, f"mkdir -p {shlex.quote(remote_dir + '/images')}"])

    run(["scp", str(md), f"{args.vps}:{remote_dir}/{md.name}"])
    remote_images: list[str] = []
    copied = set()
    for img in images:
        remote_img = f"{remote_dir}/images/{img.name}"
        run(["scp", str(img), f"{args.vps}:{remote_img}"])
        remote_images.append(remote_img)
        copied.add(img.name)
    remote_cover = f"{remote_dir}/images/{cover.name}"
    if cover.name not in copied:
        run(["scp", str(cover), f"{args.vps}:{remote_cover}"])

    remote_report = f"{remote_dir}/push-report.json"
    remote_cmd = [
        "python3",
        args.remote_script,
        "--markdown",
        f"{remote_dir}/{md.name}",
        "--images",
        *remote_images,
        "--title",
        args.title,
        "--cover",
        remote_cover,
        "--theme",
        args.theme,
        "--author",
        args.author,
        "--digest",
        args.digest,
        "--report-file",
        remote_report,
    ]
    runner = "#!/bin/bash\nset -euo pipefail\n" + " ".join(shlex.quote(x) for x in remote_cmd) + "\n"
    local_runner = Path(args.report_file).resolve().parent / f".push-via-vps-{stamp}.sh"
    # Win 默认 CRLF 会让远程 bash 把 pipefail 读成 pipefail\r
    local_runner.write_bytes(runner.encode("utf-8"))
    remote_runner = f"{remote_dir}/run.sh"
    try:
        run(["scp", str(local_runner), f"{args.vps}:{remote_runner}"])
        run([
            "ssh",
            args.vps,
            f"sed -i 's/\\r$//' {shlex.quote(remote_runner)} && bash {shlex.quote(remote_runner)}",
        ])
        run(["scp", f"{args.vps}:{remote_report}", args.report_file])
    finally:
        if local_runner.exists():
            local_runner.unlink()
    print(f"✅ 已从 VPS 拉回报告: {args.report_file}")
    print(f"ℹ️  VPS 临时目录保留: {remote_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"❌ 远程推送失败: {exc}")
        sys.exit(exc.returncode or 1)
