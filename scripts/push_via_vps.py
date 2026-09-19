#!/usr/bin/env python3
"""把本机稿子拷到 VPS 再跑 push_article.py。

家宽 / Win 本机 IP 通常不在微信 API 白名单，直接 push 会 40164。
稿子继续在本机写，出口走已经在白名单里的 VPS。

传输层（2026-09-19 提速）：所有文件打成单个 tar.gz，经一条 SSH 连接
流式上传、解压、执行并回读报告。旧的逐文件 scp 在 Tailscale DERP 中继
（RTT ~300ms）下每张图都要重建连接，6 张图常要 2 分钟+；单连接一次
拥塞窗口爬坡，同量级素材 30-60s 内完成。`--legacy` 可切回旧 scp 路径。

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
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPORT_MARKER = "__WXMP_PUSH_REPORT_BEGIN__"

_T0 = time.time()


def log(msg: str) -> None:
    print(f"[+{time.time() - _T0:5.1f}s] {msg}", flush=True)


def run(cmd: list[str]) -> None:
    printable = " ".join(cmd)
    log(f"+ {printable}")
    subprocess.run(cmd, check=True)


def unique_images(images: list[Path], cover: Path | None) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for p in [*images, *([cover] if cover else [])]:
        if p.name not in seen:
            seen.add(p.name)
            out.append(p)
    return out


def push_stream(args, remote_dir: str, runner: str, remote_report: str) -> int:
    """单连接：tar.gz 流上传 -> 解压 -> 执行 run.sh -> 回读报告。"""
    md = Path(args.markdown)
    images = [Path(p) for p in args.images]
    cover = Path(args.cover) if args.cover else None
    video = Path(args.video) if args.video else None

    with tempfile.TemporaryDirectory(prefix="wxmp-push-") as td:
        stage = Path(td)
        shutil.copy2(md, stage / md.name)
        (stage / "images").mkdir()
        for img in unique_images(images, cover):
            shutil.copy2(img, stage / "images" / img.name)
        if video:
            (stage / "videos").mkdir()
            shutil.copy2(video, stage / "videos" / video.name)
        # Win 默认 CRLF 会让远程 bash 把 pipefail 读成 pipefail\r；远程再 sed 兜底
        (stage / "run.sh").write_bytes(runner.encode("utf-8"))

        payload_kb = sum(p.stat().st_size for p in stage.rglob("*") if p.is_file()) // 1024
        log(f"📦 打包 {payload_kb}KB，单连接流式上传+执行 ...")

        remote_sh = (
            "set -e; "
            f"mkdir -p {shlex.quote(remote_dir)} && "
            f"tar xzf - -C {shlex.quote(remote_dir)} && "
            f"sed -i 's/\\r$//' {shlex.quote(remote_dir + '/run.sh')} && "
            f"bash {shlex.quote(remote_dir + '/run.sh')} && "
            f"echo '{REPORT_MARKER}' && "
            f"(cat {shlex.quote(remote_report)} 2>/dev/null || true)"
        )
        # macOS bsdtar 会写入 xattr 扩展头，GNU tar 解压时刷警告；加 --no-xattrs
        tar_version = subprocess.run(
            ["tar", "--version"], capture_output=True, text=True
        ).stdout
        tar_cmd = ["tar", "czf", "-", "-C", str(stage), "."]
        if "bsdtar" in tar_version:
            tar_cmd.insert(3, "--no-xattrs")
        tar = subprocess.Popen(
            tar_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        ssh = subprocess.Popen(
            ["ssh", args.vps, remote_sh],
            stdin=tar.stdout,
            stdout=subprocess.PIPE,
        )
        assert tar.stdout is not None and ssh.stdout is not None
        tar.stdout.close()  # ssh 独占管道读端，tar 可收到 SIGPIPE

        assert ssh.stdout is not None
        report_buf = bytearray()
        in_report = False
        while True:
            chunk = ssh.stdout.readline()
            if not chunk:
                break
            if in_report:
                report_buf.extend(chunk)
            elif chunk.strip().decode("utf-8", "replace") == REPORT_MARKER:
                in_report = True
            else:
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()

        ssh_rc = ssh.wait()
        tar_rc = tar.wait()
        if tar_rc not in (0, None):
            log(f"⚠️ 本地 tar 退出码 {tar_rc}")
        if ssh_rc != 0:
            print(f"❌ 远程推送失败: ssh 退出码 {ssh_rc}")
            return ssh_rc or 1
        if not in_report:
            print("❌ 未收到报告标记，远端 run.sh 可能未完成")
            return 1
        if not report_buf.strip():
            print("⚠️ 远端未产出 push-report.json（dry-run 模式属正常）")
        Path(args.report_file).write_bytes(bytes(report_buf).strip() + b"\n")
        return 0


def push_legacy_scp(args, remote_dir: str, runner: str, remote_report: str) -> int:
    """旧路径：逐文件 scp。tar 不可用时兜底。"""
    md = Path(args.markdown)
    images = [Path(p) for p in args.images]
    cover = Path(args.cover) if args.cover else None
    video = Path(args.video) if args.video else None

    run(["ssh", args.vps, f"mkdir -p {shlex.quote(remote_dir + '/images')}"])
    run(["scp", str(md), f"{args.vps}:{remote_dir}/{md.name}"])
    for img in unique_images(images, cover):
        run(["scp", str(img), f"{args.vps}:{remote_dir}/images/{img.name}"])
    if video:
        run(["ssh", args.vps, f"mkdir -p {shlex.quote(remote_dir + '/videos')}"])
        run(["scp", str(video), f"{args.vps}:{remote_dir}/videos/{video.name}"])

    local_runner = Path(args.report_file).resolve().parent / f".push-via-vps-{int(_T0)}.sh"
    local_runner.write_bytes(runner)
    try:
        run(["scp", str(local_runner), f"{args.vps}:{remote_dir}/run.sh"])
        run(["ssh", args.vps, f"sed -i 's/\\r$//' {remote_dir}/run.sh && bash {remote_dir}/run.sh"])
        run(["scp", f"{args.vps}:{remote_report}", args.report_file])
    finally:
        if local_runner.exists():
            local_runner.unlink()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="经 VPS 推微信草稿箱，绕过本机 IP 白名单")
    parser.add_argument("--article-type", default="news", choices=["news", "newspic"], help="news=普通图文(渲染HTML)；newspic=图片消息/小绿书(纯文本+image_list,≤20图,标题≤32字,正文≤1000字)")
    parser.add_argument("--markdown", required=True)
    parser.add_argument("--images", nargs="+", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--cover", default=None, help="news 必填；newspic 忽略（封面自动取首图）")
    parser.add_argument("--author", default=None, help="作者（默认按账号推断：yulong 为 宇龙，xingchen 为 星辰）")
    parser.add_argument("--digest", default="")
    parser.add_argument("--theme", default="green", choices=["rainbow", "purple", "blue", "green", "dark-gold", "minimal", "twilight", "sunset"])
    parser.add_argument("--account", default="yulong", help="公众号标识 (默认 yulong，可选 xingchen 等，对应 wxmp-{account}.env)")
    parser.add_argument("--env-file", default=None, help="自定义凭据文件路径（可选）")
    parser.add_argument("--video", default=None, help="视频文件路径（可选）")
    parser.add_argument("--vps", default="vps", help="ssh Host，默认 vps")
    parser.add_argument(
        "--remote-script",
        default="/root/.openclaw/skills/wxmp-article-pipeline/scripts/push_article.py",
    )
    parser.add_argument("--report-file", default="push-report.json")
    parser.add_argument("--dry-run", action="store_true", help="远端只渲染不推送（验证传输链路）")
    parser.add_argument("--legacy", action="store_true", help="强制走旧的逐文件 scp 传输")
    args = parser.parse_args()

    author = args.author
    if not author:
        author = "星辰" if args.account == "xingchen" else "宇龙"

    md = Path(args.markdown)
    images = [Path(p) for p in args.images]
    if args.article_type == "news" and not args.cover:
        print("❌ news 类型必须提供 --cover")
        return 1
    cover = Path(args.cover) if args.cover else (images[0] if images else None)
    video = Path(args.video) if args.video else None
    check_paths = [md, *images] + ([cover] if cover else [])
    if video:
        check_paths.append(video)
    for path in check_paths:
        if not path.exists():
            print(f"❌ 文件不存在: {path}")
            return 1

    stamp = time.strftime("%Y%m%d-%H%M%S")
    remote_dir = f"/tmp/wxmp-win-push-{stamp}"
    remote_report = f"{remote_dir}/push-report.json"
    remote_images = [f"{remote_dir}/images/{img.name}" for img in images]
    remote_video_arg = ["--video", f"{remote_dir}/videos/{video.name}"] if video else []
    remote_cmd = [
        "python3",
        args.remote_script,
        "--article-type",
        args.article_type,
        "--markdown",
        f"{remote_dir}/{md.name}",
        "--images",
        *remote_images,
        "--title",
        args.title,
        "--theme",
        args.theme,
        "--account",
        args.account,
        "--author",
        author,
        "--digest",
        args.digest,
        *remote_video_arg,
        "--report-file",
        remote_report,
    ]
    if args.article_type == "news" and cover:
        remote_cmd.extend(["--cover", f"{remote_dir}/images/{cover.name}"])
    if args.env_file:
        remote_cmd.extend(["--env-file", args.env_file])
    if args.dry_run:
        remote_cmd.append("--dry-run")
    runner = "#!/bin/bash\nset -euo pipefail\n" + " ".join(shlex.quote(x) for x in remote_cmd) + "\n"

    use_stream = not args.legacy and shutil.which("tar") is not None
    if not use_stream and not args.legacy:
        log("⚠️ 本机无 tar，自动降级为逐文件 scp")
    rc = (
        push_stream(args, remote_dir, runner, remote_report)
        if use_stream
        else push_legacy_scp(args, remote_dir, runner, remote_report)
    )
    if rc != 0:
        return rc
    log(f"✅ 报告已落地: {args.report_file}")
    log(f"ℹ️  VPS 临时目录保留: {remote_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"❌ 远程推送失败: {exc}")
        sys.exit(exc.returncode or 1)
