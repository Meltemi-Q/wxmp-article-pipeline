#!/usr/bin/env python3
"""upload_draft_images_to_mmbiz.py — 把一个 wxmp-studio draft 的所有图片上传到 mmbiz.

为什么需要这个: 腾讯公众号编辑器的后端 fetcher 对外部图片域名有信任机制,
wxmp.meltemi.fun 这类自建域被静默 abort (2-3ms broken pipe). 所有公众号排版
工具 (mdnice/秀米/墨滴) 都通过 media/uploadimg API 把图先上传到 mmbiz.qpic.cn,
然后在 HTML 里引用 mmbiz URL. 这个脚本做同样的事, 让本地草稿图也能被编辑器
正确识别.

用法:
  python3 upload_draft_images_to_mmbiz.py --draft-id 20260409-090548-2207dd
  python3 upload_draft_images_to_mmbiz.py --draft-id xxx --force  # 重上传已缓存的

幂等: 已上传过的图 (meta.json 的 mmbiz_urls 字段里有 key) 默认跳过, 只上传新的.

输出: 把 mmbiz URL 写回 drafts/{id}/meta.json 的 mmbiz_urls 字段:
  {
    "title": ...,
    "content": ...,
    "images": [{filename:..., note:...}, ...],
    "mmbiz_urls": {                    # 新增
      "090709-ece9.png": "https://mmbiz.qpic.cn/...",
      ...
    }
  }
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Reuse push_article.py's credential + uploadimg functions
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from push_article import (  # noqa: E402
    DEFAULT_ENV_FILE,
    get_access_token,
    resolve_credentials,
    upload_article_image,
)

DRAFTS_DIR = Path("/root/.openclaw/workspace/projects/wxmp-studio/drafts")


def main() -> int:
    parser = argparse.ArgumentParser(description="上传 wxmp-studio draft 的图片到 mmbiz 并缓存 URL")
    parser.add_argument("--draft-id", required=True, help="draft 目录名, 如 20260409-090548-2207dd")
    parser.add_argument("--force", action="store_true", help="重新上传已缓存的图 (默认跳过)")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="wxmp env file")
    parser.add_argument("--json", action="store_true", help="stdout 发 JSON 结果 (人类日志走 stderr)")
    args = parser.parse_args()

    # When --json, redirect prints to stderr for clean stdout
    _real_print = print

    def _p(*a, **kw):
        if args.json:
            kw.setdefault("file", sys.stderr)
        _real_print(*a, **kw)

    draft_dir = DRAFTS_DIR / args.draft_id
    meta_path = draft_dir / "meta.json"
    images_dir = draft_dir / "images"

    if not meta_path.exists():
        _p(f"❌ draft not found: {meta_path}")
        return 2

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    images = meta.get("images") or []
    if not images:
        _p(f"⚠️  draft has no images field (empty images array)")
        if args.json:
            _real_print(json.dumps({"ok": True, "uploaded": 0, "skipped": 0, "mmbiz_urls": {}}, ensure_ascii=False))
        return 0

    existing: dict = dict(meta.get("mmbiz_urls") or {})

    to_upload: list[tuple[str, Path]] = []
    for img in images:
        fname = img.get("filename")
        if not fname:
            continue
        if fname in existing and not args.force:
            continue
        fpath = images_dir / fname
        if not fpath.exists():
            _p(f"⚠️  image file missing: {fpath} — skipping")
            continue
        to_upload.append((fname, fpath))

    _p(f"📸 draft {args.draft_id}: 共 {len(images)} 张图, 已缓存 {len(existing)}, 待上传 {len(to_upload)}")

    if not to_upload:
        _p("✅ 全部已缓存, 无需上传")
        if args.json:
            _real_print(json.dumps({"ok": True, "uploaded": 0, "skipped": len(existing), "mmbiz_urls": existing}, ensure_ascii=False))
        return 0

    # Resolve credentials + token
    _p(f"🔑 读取凭据: {args.env_file}")
    appid, appsecret = resolve_credentials(Path(args.env_file))
    token = get_access_token(appid, appsecret)
    _p("✅ access_token OK")

    uploaded = 0
    failed: list[str] = []
    for fname, fpath in to_upload:
        _p(f"  ↑ 上传 {fname} ({fpath.stat().st_size // 1024} KB)...")
        try:
            url = upload_article_image(token, fpath)
        except SystemExit:
            # upload_article_image calls sys.exit on failure; catch and continue
            failed.append(fname)
            _p(f"    ❌ 失败 {fname}")
            continue
        except Exception as e:
            failed.append(fname)
            _p(f"    ❌ 异常 {fname}: {e}")
            continue
        existing[fname] = url
        uploaded += 1
        _p(f"    ✅ {url[:80]}")

    # Persist to meta.json (atomic: write to tmp then rename)
    meta["mmbiz_urls"] = existing
    tmp_path = meta_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(meta_path)
    _p(f"💾 写回 {meta_path}")

    _p(f"\n✅ 完成: 新上传 {uploaded} 张, 失败 {len(failed)}, 已缓存总数 {len(existing)}")

    if args.json:
        _real_print(json.dumps({
            "ok": len(failed) == 0,
            "uploaded": uploaded,
            "skipped": len(images) - len(to_upload),
            "failed": failed,
            "mmbiz_urls": existing,
        }, ensure_ascii=False))

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
