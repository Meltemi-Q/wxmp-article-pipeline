#!/usr/bin/env python3
"""
微信公众号文章一键推送脚本

用法:
  python3 push_article.py \
    --markdown article.md \
    --images file_183.jpg file_184.jpg file_185.jpg \
    --title "文章标题" \
    --cover file_185.jpg \
    --theme rainbow \
    --author "宇龙"

功能:
  1. 读取 Markdown
  2. 逐图上传到微信（获取 mmbiz URL）
  3. 封面图单独上传（获取 thumb_media_id）
  4. 渲染主题 HTML
  5. 去重复标题
  6. 三项验证
  7. 推送草稿箱
  8. batchget 验证草稿到账
  9. 输出 report.json

注意: 密钥从本机 env 文件读取，不要在命令行传密钥。
查找顺序：
  1. 环境变量 WXMP_ENV_FILE
  2. ~/.openclaw/secrets/wxmp-yulong.env   # Mac / Win 本机
  3. /root/.openclaw/secrets/wxmp-yulong.env  # VPS
"""
import shutil
import argparse
import json
import mimetypes
import os
import re
import sys
from pathlib import Path

import requests

VPS_ENV_FILE = Path("/root/.openclaw/secrets/wxmp-yulong.env")
HOME_ENV_FILE = Path.home() / ".openclaw" / "secrets" / "wxmp-yulong.env"


def resolve_default_env_file() -> Path:
    """挑第一个实际存在的凭据文件；都不存在时返回本机 home 路径，方便报错提示。"""
    override = os.environ.get("WXMP_ENV_FILE", "").strip()
    candidates = []
    if override:
        candidates.append(Path(override).expanduser())
    candidates.extend([HOME_ENV_FILE, VPS_ENV_FILE])
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


DEFAULT_ENV_FILE = resolve_default_env_file()


# ---------------------------------------------------------------------------
# 凭据 & Token
# ---------------------------------------------------------------------------

def load_env(path: Path) -> dict[str, str]:
    """读取 key=value 格式的 env 文件，自动去掉注释和空行。"""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def resolve_credentials(env_file: Path) -> tuple[str, str]:
    """从 env 文件或环境变量获取 WXMP_APPID / WXMP_APPSECRET。"""
    env = load_env(env_file)
    appid = os.environ.get("WXMP_APPID") or env.get("WXMP_APPID")
    appsecret = os.environ.get("WXMP_APPSECRET") or env.get("WXMP_APPSECRET")
    if not appid or not appsecret:
        print(f"❌ 缺少 WXMP_APPID / WXMP_APPSECRET，请检查: {env_file}")
        sys.exit(1)
    return appid, appsecret


def get_access_token(appid: str, appsecret: str) -> str:
    resp = requests.get(
        "https://api.weixin.qq.com/cgi-bin/token",
        params={"grant_type": "client_credential", "appid": appid, "secret": appsecret},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token")
    if not token:
        print(f"❌ 获取 access_token 失败: {data}")
        sys.exit(1)
    return token


# ---------------------------------------------------------------------------
# 图片上传
# ---------------------------------------------------------------------------

def upload_article_image(token: str, image_path: Path) -> str:
    """上传正文图片，返回 mmbiz.qpic.cn URL。"""
    mime = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    with image_path.open("rb") as fh:
        resp = requests.post(
            f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={token}",
            files={"media": (image_path.name, fh, mime)},
            timeout=180,
        )
    resp.raise_for_status()
    data = resp.json()
    url = data.get("url")
    if not url:
        print(f"❌ 上传正文图片失败 {image_path}: {data}")
        sys.exit(1)
    return url


def upload_cover_image(token: str, image_path: Path) -> dict:
    """上传封面图（永久素材），返回 {media_id, url}。"""
    mime = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    with image_path.open("rb") as fh:
        resp = requests.post(
            f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image",
            files={"media": (image_path.name, fh, mime)},
            timeout=180,
        )
    resp.raise_for_status()
    data = resp.json()
    if "media_id" not in data:
        print(f"❌ 上传封面图失败 {image_path}: {data}")
        sys.exit(1)
    # add_material 有时不返回 url，fallback 到 uploadimg
    url = data.get("url") or upload_article_image(token, image_path)
    return {"media_id": data["media_id"], "url": url}


# ---------------------------------------------------------------------------
# HTML 渲染（彩虹主题）
# ---------------------------------------------------------------------------

def rainbow_separator() -> str:
    return '<p style="text-align: center; margin: 30px 0; color: #ccc; letter-spacing: 10px;">* * *</p>'


def rainbow_blockquote(text: str) -> str:
    return (
        '<blockquote style="margin: 0 0 24px; padding: 16px 18px; '
        'border-left: 4px solid #F56A5F; border-radius: 0 16px 16px 0; '
        'background: linear-gradient(90deg, rgba(245,106,95,0.08) 0%, rgba(255,227,107,0.10) 42%, rgba(7,193,96,0.08) 100%); '
        'color: #1a1a1a;">'
        f'<p style="margin: 0; font-size: 16px; font-weight: 700; line-height: 1.8; text-align: justify;">{text}</p>'
        '</blockquote>'
    )


def rainbow_image_block(url: str, alt: str, caption: str) -> str:
    return (
        '<p style="margin: 20px 0 8px; text-align: center;">'
        f'<img src="{url}" alt="{alt}" '
        'style="display: block; width: 100%; max-width: 100%; border-radius: 12px; margin: 0 auto;">'
        '</p>'
        f'<p style="margin: 0 0 24px; font-size: 13px; color: #888888; text-align: center; line-height: 1.6;">{caption}</p>'
    )


def rainbow_part_header(number: str, title: str, bar_width: int = 160) -> str:
    return (
        '<section style="margin: 36px 0 20px;">'
        '<div style="display: flex; align-items: flex-end; line-height: 1;">'
        f'<span style="font-size: 42px; font-weight: 900; color: #F56A5F; margin-right: 14px; '
        f'font-family: \'Arial Black\', Helvetica, sans-serif;">{number}</span>'
        '<div>'
        '<div style="display: inline-block; padding: 2px 8px; border-radius: 999px; '
        'background: #F56A5F; color: #ffffff; font-size: 11px; font-weight: 700; letter-spacing: 1px;">PART</div>'
        f'<div style="margin-top: 10px; font-size: 22px; font-weight: 700; color: #1a1a1a;">{title}</div>'
        '</div>'
        '</div>'
        f'<div style="height: 4px; width: {bar_width}px; margin: 14px 0 0 55px; border-radius: 999px; '
        'background: linear-gradient(90deg, #F56A5F 0%, #ffb86b 20%, #ffe36b 40%, #07C160 60%, #4dabf7 80%, #9b6bff 100%);"></div>'
        '</section>'
    )


def render_markdown_to_rainbow_html(
    markdown_text: str,
    image_map: dict[str, dict],  # {placeholder_or_filename: {url, alt, caption}}
) -> str:
    """
    将 Markdown 转换为彩虹主题 HTML。

    支持的 Markdown 元素:
    - # / ## / ### 标题 → PART 结构 / H2 / H3
    - > 引用块 → Blockquote 彩虹样式
    - --- → 分隔符
    - **粗体** → <strong>
    - *斜体* → <em>
    - 普通段落 → <p>
    - ![alt](path) → 图片（自动替换为微信 URL）

    image_map 格式:
    {
        "file_183.jpg": {"url": "https://mmbiz.qpic.cn/...", "alt": "图片描述", "caption": "图注"},
        # 或者用文件 basename 作为 key
    }
    """
    lines = markdown_text.splitlines()
    html_parts = [
        '<section style="max-width: 677px; margin: 0 auto; padding: 28px 24px 32px; '
        'box-sizing: border-box; '
        'background: linear-gradient(180deg, #fffafa 0%, #fffdf9 24%, #f8fff9 52%, #f8fbff 78%, #fcf9ff 100%); '
        'font-family: -apple-system, BlinkMacSystemFont, \'Helvetica Neue\', \'PingFang SC\', \'Microsoft YaHei\', sans-serif; '
        'color: #333333; line-height: 1.9; overflow: hidden;">',
        # 顶部彩虹线
        '<div style="height: 5px; border-radius: 999px; margin: 0 0 32px; '
        'background: linear-gradient(90deg, #F56A5F 0%, #ffb86b 18%, #ffe36b 36%, #07C160 54%, #4dabf7 74%, #9b6bff 100%);"></div>',
    ]

    part_counter = 0
    i = 0
    pending_blockquote_lines: list[str] = []

    def flush_blockquote():
        nonlocal pending_blockquote_lines
        if pending_blockquote_lines:
            text = " ".join(pending_blockquote_lines).strip()
            html_parts.append(rainbow_blockquote(text))
            pending_blockquote_lines = []

    def inline_format(text: str) -> str:
        """处理行内格式：**粗体**、*斜体*、`代码`"""
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        return text

    # 跳过第一行 `# 标题`（如果存在，避免重复标题）
    start_idx = 0
    if lines and lines[0].startswith("# "):
        start_idx = 1

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 跳过 HTML 注释（如 <!-- 配图 -->）
        if re.match(r'^\s*<!--.*-->\s*$', line):
            i += 1
            continue

        # 分隔符 ---
        if stripped in ("---", "***", "* * *"):
            flush_blockquote()
            html_parts.append(rainbow_separator())
            i += 1
            continue

        # 引用块（可能跨多行）
        if stripped.startswith("> "):
            pending_blockquote_lines.append(inline_format(stripped[2:]))
            i += 1
            continue
        else:
            flush_blockquote()

        # H1 → 跳过（避免重复标题）
        if stripped.startswith("# ") and i == start_idx:
            i += 1
            start_idx = -1  # 只跳过一次
            continue

        # H2 → PART 结构
        if stripped.startswith("## "):
            part_counter += 1
            title = stripped[3:].strip()
            html_parts.append(rainbow_part_header(f"{part_counter:02d}", title))
            i += 1
            continue

        # H3 → 小标题
        if stripped.startswith("### "):
            title = inline_format(stripped[4:].strip())
            html_parts.append(
                f'<h3 style="margin: 24px 0 12px; font-size: 18px; font-weight: 700; color: #1a1a1a;">{title}</h3>'
            )
            i += 1
            continue

        # 图片 ![alt](path)
        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
        if img_match:
            alt = img_match.group(1)
            path = img_match.group(2)
            basename = Path(path).name
            # 尝试从 image_map 里找
            img_info = image_map.get(path) or image_map.get(basename)
            # 自动提取图注：图片后紧跟的空行+*斜体行* 作为 caption
            caption = ""
            if img_info:
                caption = img_info.get("caption", "")
            # 向前看：跳过空行，找 *caption* 行
            peek = i + 1
            while peek < len(lines) and lines[peek].strip() == "":
                peek += 1
            if not caption and peek < len(lines):
                cap_match = re.match(r'^\*([^*]+)\*$', lines[peek].strip())
                if cap_match:
                    caption = cap_match.group(1)
                    i = peek  # 跳过 caption 行
            if img_info:
                html_parts.append(rainbow_image_block(
                    url=img_info["url"],
                    alt=alt if alt else img_info.get("alt", ""),
                    caption=caption,
                ))
            else:
                # 找不到图片映射，输出警告注释
                html_parts.append(f'<!-- ⚠️ 图片未映射: {path} -->')
                print(f"⚠️  图片未映射: {path}（basename: {basename}）")
            i += 1
            continue

        # 无序列表
        if stripped.startswith("- ") or stripped.startswith("* "):
            # 收集连续的列表项
            list_items = []
            while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")):
                item = lines[i].strip()[2:]
                list_items.append(f'<li style="margin: 0 0 8px;">{inline_format(item)}</li>')
                i += 1
            html_parts.append(
                '<ul style="margin: 0 0 20px; padding-left: 22px; font-size: 15px; color: #555; line-height: 1.8;">'
                + "".join(list_items)
                + "</ul>"
            )
            continue

        # 有序列表
        if re.match(r'^\d+\. ', stripped):
            list_items = []
            while i < len(lines) and re.match(r'^\d+\. ', lines[i].strip()):
                item = re.sub(r'^\d+\. ', '', lines[i].strip())
                list_items.append(f'<li style="margin: 0 0 8px;">{inline_format(item)}</li>')
                i += 1
            html_parts.append(
                '<ol style="margin: 0 0 20px; padding-left: 22px; font-size: 15px; color: #555; line-height: 1.8;">'
                + "".join(list_items)
                + "</ol>"
            )
            continue

        # 空行
        if not stripped:
            i += 1
            continue

        # 普通段落
        html_parts.append(
            f'<p style="margin: 0 0 16px; font-size: 16px; text-align: justify;">{inline_format(stripped)}</p>'
        )
        i += 1

    flush_blockquote()

    # 结尾
    html_parts.append(
        '<p style="margin: 32px 0 0; font-size: 14px; color: #999999; text-align: center; '
        'line-height: 1.8; border-top: 1px solid #eee; padding-top: 24px;">'
        '我是宇龙，专注 AI Agent 场景应用落地</p>'
    )
    html_parts.append('</section>')

    return "\n".join(html_parts)


# ---------------------------------------------------------------------------
# 验证
# ---------------------------------------------------------------------------

def validate_html(html: str, title: str) -> list[str]:
    """三项验证。返回错误列表（空列表=验证通过）。"""
    errors = []

    # ① 正文无重复标题
    # 检查 HTML 里是否存在和 title 完全一样的文字（去掉 HTML 标签后）
    plain_text_start = re.sub(r'<[^>]+>', '', html[:500])
    if title in plain_text_start:
        errors.append(f"① 检测到重复标题：正文开头包含 '{title}'，请去掉 Markdown 第一行 # 标题")

    # ② 所有图片已替换为微信 URL
    if "/root/" in html:
        errors.append("② 正文包含本地路径（/root/...），图片未上传到微信")
    if "meltemi.fun" in html or "meltemi.vip" in html:
        errors.append("② 正文包含内网图片 URL（meltemi.fun/meltemi.vip），请替换为微信 URL")
    if "<!-- ⚠️" in html:
        count = html.count("<!-- ⚠️")
        errors.append(f"② 有 {count} 张图片未映射（image_map 里找不到），请补充图片映射")

    # ③ 正文长度 > 0
    if len(html.strip()) < 100:
        errors.append("③ 正文内容过短（< 100 字符），可能渲染失败")

    # ④ 图片禁止使用 src="" + data-src="" 懒加载格式（微信编辑器不支持）
    if re.search(r'<img src=""', html):
        errors.append("④ 图片使用了 src=\"\" + data-src 懒加载格式，微信编辑器不支持。请用 src=\"url\" 直接引用。")

    # ⑤ 签名严格单次校验（必须严格等于 1）
    sig_count = html.count("我是宇龙")
    if sig_count > 1:
        errors.append(f"⑤ 签名重复错误：检测到 '我是宇龙' 出现了 {sig_count} 次，必须严格只有 1 次！")
    elif sig_count == 0:
        errors.append("⑤ 签名缺失错误：未检测到 '我是宇龙' 页脚签名！")

    return errors


# ---------------------------------------------------------------------------
# 推送草稿
# ---------------------------------------------------------------------------

def push_draft(
    token: str,
    title: str,
    html: str,
    thumb_media_id: str,
    author: str = "",
    digest: str = "",
) -> dict:
    article: dict = {
        "title": title,
        "content": html,
        "thumb_media_id": thumb_media_id,
        "need_open_comment": 1,
        "only_fans_can_comment": 0,
    }
    if author:
        article["author"] = author
    if digest:
        article["digest"] = digest

    payload = {"articles": [article]}
    # 关键：必须用 ensure_ascii=False，不能用 json= 参数
    json_str = json.dumps(payload, ensure_ascii=False)
    resp = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}",
        data=json_str.encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("media_id"):
        print(f"❌ 推送草稿失败: {data}")
        sys.exit(1)
    return data


def verify_draft(token: str, media_id: str) -> dict:
    """batchget 验证草稿已到账。"""
    payload = {"offset": 0, "count": 20, "no_content": 0}
    json_str = json.dumps(payload, ensure_ascii=False)
    resp = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/draft/batchget?access_token={token}",
        data=json_str.encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=60,
    )
    resp.raise_for_status()
    resp.encoding = "utf-8"  # 微信响应不带 charset，不设会按 latin-1 解码导致中文乱码
    result = resp.json()
    items = result.get("item", [])
    target = next((item for item in items if item.get("media_id") == media_id), None)
    if not target:
        return {"error": f"batchget 未找到草稿 {media_id}"}
    news_items = target.get("content", {}).get("news_item", [])
    if not news_items:
        return {"error": "batchget 返回 news_item 为空"}
    return news_items[0]


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


# 紫色主题（Purple Theme）- 基于 SKILL.md 文档
# ---------------------------------------------------------------------------

def purple_blockquote(text: str) -> str:
    return (
        '<blockquote style="border-left: 4px solid #c084fc; padding: 15px 20px; '
        'margin: 20px 0; background: rgba(192, 132, 252, 0.1); color: #6b21a8; '
        'border-radius: 0 8px 8px 0;">'
        f'<p style="margin: 0; text-align: justify;">{text}</p>'
        '</blockquote>'
    )


def purple_image_block(url: str, alt: str, caption: str) -> str:
    return (
        '<p style="text-align: center; margin: 20px 0;">'
        f'<img src="{url}" alt="{alt}" '
        'style="max-width: 100%; border-radius: 8px; box-shadow: rgba(0,0,0,0.1) 0px 2px 8px; '
        'height: auto !important;">'
        '</p>'
        f'<p style="text-align: center; color: #999; font-size: 13px; margin-bottom: 20px;">{caption}</p>'
    )


def purple_separator() -> str:
    return (
        '<hr style="border: none; height: 2px; '
        'background: linear-gradient(90deg, #ec4899, #8b5cf6, #3b82f6); '
        'margin: 30px 0; border-radius: 1px;" />'
    )


def purple_h2(title: str) -> str:
    return (
        f'<h2 style="font-size: 22px; font-weight: bold; color: #7c3aed; '
        f'border-bottom: 2px solid #c4b5fd; padding-bottom: 8px; '
        f'margin: 25px 0 15px 0;">{title}</h2>'
    )


def purple_h3(title: str) -> str:
    return (
        f'<h3 style="margin: 24px 0 12px; font-size: 18px; font-weight: 700; color: #7c3aed;">{title}</h3>'
    )


def render_markdown_to_purple_html(
    markdown_text: str,
    image_map: dict,
) -> str:
    """将 Markdown 转换为紫色主题 HTML。"""
    lines = markdown_text.splitlines()
    html_parts = [
        '<section style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, '
        '\'Helvetica Neue\', Arial, sans-serif; font-size: 16px; color: #333; line-height: 1.8; '
        'padding: 20px; '
        'background: linear-gradient(180deg, #fdf4ff 0%, #faf5ff 50%, #f5f3ff 100%);">',
    ]

    part_counter = 0
    pending_blockquote_lines: list[str] = []

    def flush_blockquote():
        nonlocal pending_blockquote_lines
        if pending_blockquote_lines:
            text = " ".join(pending_blockquote_lines).strip()
            html_parts.append(purple_blockquote(text))
            pending_blockquote_lines = []

    def inline_format(text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="font-weight: bold; color: #6d28d9;">\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        return text

    # 跳过第一行 # 标题（避免重复标题）
    skip_first_h1 = False
    if lines and lines[0].startswith("# ") and not lines[0].startswith("## "):
        skip_first_h1 = True

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 跳过 HTML 注释
        if re.match(r'^\s*<!--.*-->\s*$', line):
            i += 1
            continue

        # 跳过第一行 H1
        if skip_first_h1 and i == 0 and stripped.startswith("# ") and not stripped.startswith("## "):
            skip_first_h1 = False
            i += 1
            continue

        # 分隔符
        if stripped in ("---", "***", "* * *"):
            flush_blockquote()
            html_parts.append(purple_separator())
            i += 1
            continue

        # 引用块
        if stripped.startswith("> "):
            pending_blockquote_lines.append(inline_format(stripped[2:]))
            i += 1
            continue
        else:
            flush_blockquote()

        # H2 → 紫色标题
        if stripped.startswith("## "):
            part_counter += 1
            title = inline_format(stripped[3:].strip())
            html_parts.append(purple_h2(title))
            i += 1
            continue

        # H3
        if stripped.startswith("### "):
            title = inline_format(stripped[4:].strip())
            html_parts.append(purple_h3(title))
            i += 1
            continue

        # 图片
        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
        if img_match:
            alt = img_match.group(1)
            path = img_match.group(2)
            basename = Path(path).name
            img_info = image_map.get(path) or image_map.get(basename)
            # 自动提取图注：图片后紧跟的空行+*斜体行* 作为 caption
            caption = ""
            if img_info:
                caption = img_info.get("caption", "")
            peek = i + 1
            while peek < len(lines) and lines[peek].strip() == "":
                peek += 1
            if not caption and peek < len(lines):
                cap_match = re.match(r'^\*([^*]+)\*$', lines[peek].strip())
                if cap_match:
                    caption = cap_match.group(1)
                    i = peek
            if img_info:
                html_parts.append(purple_image_block(
                    url=img_info["url"],
                    alt=alt if alt else img_info.get("alt", ""),
                    caption=caption,
                ))
            else:
                html_parts.append(f'<!-- ⚠️ 图片未映射: {path} -->')
                print(f"⚠️  图片未映射: {path}")
            i += 1
            continue

        # 无序列表
        if stripped.startswith("- ") or stripped.startswith("* "):
            list_items = []
            while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")):
                item = lines[i].strip()[2:]
                list_items.append(f'<li style="margin: 0 0 8px;">{inline_format(item)}</li>')
                i += 1
            html_parts.append(
                '<ul style="margin: 15px 0; padding-left: 25px;">'
                + "".join(list_items)
                + "</ul>"
            )
            continue

        # 有序列表
        if re.match(r'^\d+\. ', stripped):
            list_items = []
            while i < len(lines) and re.match(r'^\d+\. ', lines[i].strip()):
                item = re.sub(r'^\d+\. ', '', lines[i].strip())
                list_items.append(f'<li style="margin: 0 0 8px;">{inline_format(item)}</li>')
                i += 1
            html_parts.append(
                '<ol style="margin: 15px 0; padding-left: 25px;">'
                + "".join(list_items)
                + "</ol>"
            )
            continue

        # 空行
        if not stripped:
            i += 1
            continue

        # 独立一行的大块 HTML（如居中链接等），不做段落包装
        if stripped.startswith('<') and re.search(r'</[a-z]+>$', stripped):
            html_parts.append(stripped)
            i += 1
            continue

        # 普通段落
        html_parts.append(
            f'<p style="margin: 15px 0; text-align: justify;">{inline_format(stripped)}</p>'
        )
        i += 1

    flush_blockquote()

    # 结尾签名
    html_parts.append(
        '<p style="margin: 30px 0 0; font-size: 14px; color: #999; text-align: center; '
        'line-height: 1.8; border-top: 1px solid #eee; padding-top: 20px;">'
        '我是宇龙，专注 AI Agent 场景应用落地</p>'
    )
    html_parts.append(
        '<p style="display: none;"><mp-style-type data-value="10000"></mp-style-type></p>'
    )
    html_parts.append('</section>')

    return "\n".join(html_parts)





def blue_blockquote(text: str) -> str:
    return (f'<section style="margin: 20px 0; padding: 16px 18px; background: #eff6ff; '
            f'border-left: 4px solid #2563eb; border-radius: 8px; color: #1e3a8a; '
            f'font-size: 15px; line-height: 1.8;">{text}</section>')


def blue_image_block(url: str, alt: str, caption: str) -> str:
    cap = (f'<p style="margin: 8px 0 0; font-size: 13px; color: #94a3b8; text-align: center; '
           f'line-height: 1.6;">{caption}</p>') if caption else ''
    return (f'<section style="margin: 22px 0; text-align: center;">'
            f'<img src="{url}" alt="{alt}" style="max-width: 100%; border-radius: 10px;"/>{cap}</section>')


def blue_separator() -> str:
    return ('<section style="margin: 28px 0; height: 2px; '
            'background: linear-gradient(90deg, transparent, #93c5fd, transparent);"></section>')


def blue_h2(title: str) -> str:
    return (f'<h2 style="margin: 30px 0 16px; font-size: 20px; font-weight: bold; color: #1d4ed8; '
            f'border-left: 5px solid #2563eb; padding-left: 12px; line-height: 1.5;">{title}</h2>')


def blue_h3(title: str) -> str:
    return (f'<h3 style="margin: 24px 0 12px; font-size: 17px; font-weight: bold; '
            f'color: #2563eb;">{title}</h3>')


def mac_code_block(code_lines: list) -> str:
    import html as _h
    body = _h.escape("\n".join(code_lines))
    return (
        '<section style="margin: 20px 0; border-radius: 6px; overflow: hidden; '
        'box-shadow: rgba(0,0,0,0.55) 0px 2px 10px;">'
        '<section style="background: #282c34; padding: 9px 14px; line-height: 1;">'
        '<span style="font-size:22px; letter-spacing:8px; line-height:1; font-family: Arial,sans-serif;">'
        '<span style="color:#ff5f56;">●</span>'
        '<span style="color:#ffbd2e;">●</span>'
        '<span style="color:#27c93f;">●</span></span>'
        '</section>'
        '<section style="background: #282c34; padding: 14px 16px; overflow-x: auto;">'
        f'<pre style="margin:0; color:#abb2bf; font-family: Operator Mono,Consolas,Menlo,monospace; '
        f'font-size:14px; line-height:1.7; white-space: pre;">{body}</pre>'
        '</section></section>'
    )
def render_markdown_to_blue_html(
    markdown_text: str,
    image_map: dict,
) -> str:
    """将 Markdown 转换为萌蓝主题 HTML（含 Mac 窗口代码块）。"""
    lines = markdown_text.splitlines()
    html_parts = [
        '<section style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, '
        '\'Helvetica Neue\', Arial, sans-serif; font-size: 16px; color: #333; line-height: 1.8; '
        'padding: 20px; '
        'background: linear-gradient(180deg, #eff6ff 0%, #f0f9ff 50%, #eff6ff 100%);">',
    ]

    part_counter = 0
    pending_blockquote_lines: list[str] = []

    def flush_blockquote():
        nonlocal pending_blockquote_lines
        if pending_blockquote_lines:
            text = " ".join(pending_blockquote_lines).strip()
            html_parts.append(blue_blockquote(text))
            pending_blockquote_lines = []

    def inline_format(text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="font-weight: bold; color: #1d4ed8;">\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        return text

    # 跳过第一行 # 标题（避免重复标题）
    skip_first_h1 = False
    if lines and lines[0].startswith("# ") and not lines[0].startswith("## "):
        skip_first_h1 = True

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 跳过 HTML 注释
        if re.match(r'^\s*<!--.*-->\s*$', line):
            i += 1
            continue

        # 跳过第一行 H1
        if skip_first_h1 and i == 0 and stripped.startswith("# ") and not stripped.startswith("## "):
            skip_first_h1 = False
            i += 1
            continue

        # 分隔符
        if stripped in ("---", "***", "* * *"):
            flush_blockquote()
            html_parts.append(blue_separator())
            i += 1
            continue

        # 引用块
        if stripped.startswith("> "):
            pending_blockquote_lines.append(inline_format(stripped[2:]))
            i += 1
            continue
        else:
            flush_blockquote()

        # H2 → 紫色标题
        if stripped.startswith("## "):
            part_counter += 1
            title = inline_format(stripped[3:].strip())
            html_parts.append(blue_h2(title))
            i += 1
            continue

        # H3
        if stripped.startswith("### "):
            title = inline_format(stripped[4:].strip())
            html_parts.append(blue_h3(title))
            i += 1
            continue

        # 围栏代码块 ``` → Mac 窗口样式
        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 跳过结束围栏
            html_parts.append(mac_code_block(code_lines))
            continue

        # 图片
        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
        if img_match:
            alt = img_match.group(1)
            path = img_match.group(2)
            basename = Path(path).name
            img_info = image_map.get(path) or image_map.get(basename)
            # 自动提取图注：图片后紧跟的空行+*斜体行* 作为 caption
            caption = ""
            if img_info:
                caption = img_info.get("caption", "")
            peek = i + 1
            while peek < len(lines) and lines[peek].strip() == "":
                peek += 1
            if not caption and peek < len(lines):
                cap_match = re.match(r'^\*([^*]+)\*$', lines[peek].strip())
                if cap_match:
                    caption = cap_match.group(1)
                    i = peek
            if img_info:
                html_parts.append(blue_image_block(
                    url=img_info["url"],
                    alt=alt if alt else img_info.get("alt", ""),
                    caption=caption,
                ))
            else:
                html_parts.append(f'<!-- ⚠️ 图片未映射: {path} -->')
                print(f"⚠️  图片未映射: {path}")
            i += 1
            continue

        # 无序列表
        if stripped.startswith("- ") or stripped.startswith("* "):
            list_items = []
            while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")):
                item = lines[i].strip()[2:]
                list_items.append(f'<li style="margin: 0 0 8px;">{inline_format(item)}</li>')
                i += 1
            html_parts.append(
                '<ul style="margin: 15px 0; padding-left: 25px;">'
                + "".join(list_items)
                + "</ul>"
            )
            continue

        # 有序列表
        if re.match(r'^\d+\. ', stripped):
            list_items = []
            while i < len(lines) and re.match(r'^\d+\. ', lines[i].strip()):
                item = re.sub(r'^\d+\. ', '', lines[i].strip())
                list_items.append(f'<li style="margin: 0 0 8px;">{inline_format(item)}</li>')
                i += 1
            html_parts.append(
                '<ol style="margin: 15px 0; padding-left: 25px;">'
                + "".join(list_items)
                + "</ol>"
            )
            continue

        # 空行
        if not stripped:
            i += 1
            continue

        # 独立一行的大块 HTML（如居中链接等），不做段落包装
        if stripped.startswith('<') and re.search(r'</[a-z]+>$', stripped):
            html_parts.append(stripped)
            i += 1
            continue

        # 普通段落
        html_parts.append(
            f'<p style="margin: 15px 0; text-align: justify;">{inline_format(stripped)}</p>'
        )
        i += 1

    flush_blockquote()

    # 结尾签名
    html_parts.append(
        '<p style="margin: 30px 0 0; font-size: 14px; color: #999; text-align: center; '
        'line-height: 1.8; border-top: 1px solid #eee; padding-top: 20px;">'
        '我是宇龙，专注 AI Agent 场景应用落地</p>'
    )
    html_parts.append(
        '<p style="display: none;"><mp-style-type data-value="10000"></mp-style-type></p>'
    )
    html_parts.append('</section>')

    return "\n".join(html_parts)






def green_blockquote(text: str) -> str:
    return (f'<section style="margin: 20px 0; padding: 16px 18px; background: #f0f9f4; '
            f'border-left: 4px solid #48b378; border-radius: 8px; color: #3f3f3f; '
            f'font-size: 15px; line-height: 1.8;">{text}</section>')


def green_image_block(url: str, alt: str, caption: str) -> str:
    cap = (f'<p style="margin: 8px 0 0; font-size: 13px; color: #999; text-align: center; '
           f'line-height: 1.6;">{caption}</p>') if caption else ''
    return (f'<section style="margin: 22px 0; text-align: center;">'
            f'<img src="{url}" alt="{alt}" style="max-width: 100%; border-radius: 10px;"/>{cap}</section>')


def green_separator() -> str:
    return ('<section style="margin: 28px 0; height: 2px; '
            'background: linear-gradient(90deg, transparent, #a7e0c0, transparent);"></section>')


def green_h2(title: str) -> str:
    return (f'<h2 style="margin: 34px 0 18px; font-size: 19px; font-weight: bold; color: #48b378; '
            f'text-align: center; line-height: 1.6;">'
            f'<span style="display:block; width:34px; height:3px; margin:0 auto 10px; '
            f'background:#a7e0c0; border-radius:2px;"></span>'
            f'{title}'
            f'<span style="display:block; width:48px; height:3px; margin:10px auto 0; '
            f'background:#48b378; border-radius:2px;"></span></h2>')


def green_h3(title: str) -> str:
    return (f'<h3 style="margin: 24px 0 12px; font-size: 17px; font-weight: bold; '
            f'color: #48b378;">{title}</h3>')


def render_markdown_to_green_html(
    markdown_text: str,
    image_map: dict,
) -> str:
    """将 Markdown 转换为萌绿主题 HTML（含 Mac 窗口代码块）。"""
    lines = markdown_text.splitlines()
    html_parts = [
        '<section style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, '
        '\'Helvetica Neue\', Arial, sans-serif; font-size: 16px; color: #333; line-height: 1.8; '
        'padding: 20px; '
        'background: #ffffff;">',
    ]

    part_counter = 0
    pending_blockquote_lines: list[str] = []

    def flush_blockquote():
        nonlocal pending_blockquote_lines
        if pending_blockquote_lines:
            text = " ".join(pending_blockquote_lines).strip()
            html_parts.append(green_blockquote(text))
            pending_blockquote_lines = []

    def inline_format(text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="font-weight: bold; color: #4a4a4a;">\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`(.+?)`', r'<code style="color:#28ca71;background:rgba(27,31,35,.06);padding:2px 5px;border-radius:4px;font-family:Consolas,Menlo,monospace;font-size:14px;">\1</code>', text)
        return text

    # 跳过第一行 # 标题（避免重复标题）
    skip_first_h1 = False
    if lines and lines[0].startswith("# ") and not lines[0].startswith("## "):
        skip_first_h1 = True

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 跳过 HTML 注释
        if re.match(r'^\s*<!--.*-->\s*$', line):
            i += 1
            continue

        # 跳过第一行 H1
        if skip_first_h1 and i == 0 and stripped.startswith("# ") and not stripped.startswith("## "):
            skip_first_h1 = False
            i += 1
            continue

        # 分隔符
        if stripped in ("---", "***", "* * *"):
            flush_blockquote()
            html_parts.append(green_separator())
            i += 1
            continue

        # 引用块
        if stripped.startswith("> "):
            pending_blockquote_lines.append(inline_format(stripped[2:]))
            i += 1
            continue
        else:
            flush_blockquote()

        # H2 → 紫色标题
        if stripped.startswith("## "):
            part_counter += 1
            title = inline_format(stripped[3:].strip())
            html_parts.append(green_h2(title))
            i += 1
            continue

        # H3
        if stripped.startswith("### "):
            title = inline_format(stripped[4:].strip())
            html_parts.append(green_h3(title))
            i += 1
            continue

        # 围栏代码块 ``` → Mac 窗口样式
        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 跳过结束围栏
            html_parts.append(mac_code_block(code_lines))
            continue

        # 图片
        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
        if img_match:
            alt = img_match.group(1)
            path = img_match.group(2)
            basename = Path(path).name
            img_info = image_map.get(path) or image_map.get(basename)
            # 自动提取图注：图片后紧跟的空行+*斜体行* 作为 caption
            caption = ""
            if img_info:
                caption = img_info.get("caption", "")
            peek = i + 1
            while peek < len(lines) and lines[peek].strip() == "":
                peek += 1
            if not caption and peek < len(lines):
                cap_match = re.match(r'^\*([^*]+)\*$', lines[peek].strip())
                if cap_match:
                    caption = cap_match.group(1)
                    i = peek
            if img_info:
                html_parts.append(green_image_block(
                    url=img_info["url"],
                    alt=alt if alt else img_info.get("alt", ""),
                    caption=caption,
                ))
            else:
                html_parts.append(f'<!-- ⚠️ 图片未映射: {path} -->')
                print(f"⚠️  图片未映射: {path}")
            i += 1
            continue

        # 无序列表
        if stripped.startswith("- ") or stripped.startswith("* "):
            list_items = []
            while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")):
                item = lines[i].strip()[2:]
                list_items.append(f'<li style="margin: 0 0 8px;">{inline_format(item)}</li>')
                i += 1
            html_parts.append(
                '<ul style="margin: 15px 0; padding-left: 25px;">'
                + "".join(list_items)
                + "</ul>"
            )
            continue

        # 有序列表
        if re.match(r'^\d+\. ', stripped):
            list_items = []
            while i < len(lines) and re.match(r'^\d+\. ', lines[i].strip()):
                item = re.sub(r'^\d+\. ', '', lines[i].strip())
                list_items.append(f'<li style="margin: 0 0 8px;">{inline_format(item)}</li>')
                i += 1
            html_parts.append(
                '<ol style="margin: 15px 0; padding-left: 25px;">'
                + "".join(list_items)
                + "</ol>"
            )
            continue

        # 空行
        if not stripped:
            i += 1
            continue

        # 独立一行的大块 HTML（如居中链接等），不做段落包装
        if stripped.startswith('<') and re.search(r'</[a-z]+>$', stripped):
            html_parts.append(stripped)
            i += 1
            continue

        # 普通段落
        html_parts.append(
            f'<p style="margin: 15px 0; text-align: justify;">{inline_format(stripped)}</p>'
        )
        i += 1

    flush_blockquote()

    # 结尾签名
    html_parts.append(
        '<p style="margin: 30px 0 0; font-size: 14px; color: #999; text-align: center; '
        'line-height: 1.8; border-top: 1px solid #eee; padding-top: 20px;">'
        '我是宇龙，专注 AI Agent 场景应用落地</p>'
    )
    html_parts.append(
        '<p style="display: none;"><mp-style-type data-value="10000"></mp-style-type></p>'
    )
    html_parts.append('</section>')

    return "\n".join(html_parts)








# ---------------------------------------------------------------------------
# 文本清洗与防重复签名预处理
# ---------------------------------------------------------------------------

def clean_markdown_text(markdown_text: str) -> tuple[str, str]:
    """清洗 Markdown 文本：
    1. 剥离尾部签名（如 '我是宇龙...'），避免与主题页脚重复出现两次
    2. 提取文末 hashtag（如 '#微信 #小微 #AI #Agent'）
    返回 (clean_text, hashtags_str)
    """
    lines = markdown_text.strip().splitlines()
    hashtags = ""
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        if "我是宇龙" in last:
            lines.pop()
            continue
        if last in ("---", "***", "* * *", "___"):
            lines.pop()
            continue
        if re.match(r'^(?:#\S+\s*)+$', last):
            hashtags = last
            lines.pop()
            continue
        break
    return "\n".join(lines), hashtags


# ---------------------------------------------------------------------------
# 主题 5: 黑金科技 (dark-gold)
# ---------------------------------------------------------------------------

def dark_gold_image_block(url: str, alt: str, caption: str) -> str:
    return (
        '<p style="text-align: center; margin: 24px 0 8px;">'
        f'<img src="{url}" alt="{alt}" '
        'style="max-width: 100%; border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); '
        'border: 1px solid #292524; height: auto !important;">'
        '</p>'
        f'<p style="text-align: center; color: #a8a29e; font-size: 13px; margin: 0 0 24px;">{caption}</p>'
    )

def render_markdown_to_dark_gold_html(markdown_text: str, image_map: dict) -> str:
    clean_text, hashtags = clean_markdown_text(markdown_text)
    lines = clean_text.splitlines()
    html_parts = [
        '<section style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, '
        '\'Helvetica Neue\', Arial, sans-serif; font-size: 16px; color: #e7e5e4; line-height: 1.85; '
        'padding: 24px 20px; background: linear-gradient(180deg, #18181b 0%, #1c1917 50%, #0c0a09 100%); '
        'border-radius: 12px; box-sizing: border-box;">',
    ]

    def inline_format(text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="font-weight: bold; color: #fbbf24;">\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em style="color: #fde68a;">\1</em>', text)
        text = re.sub(r'`(.+?)`', r'<code style="background: #27272a; color: #fde047; padding: 2px 6px; border-radius: 4px;">\1</code>', text)
        return text

    skip_h1 = bool(lines and lines[0].startswith("# ") and not lines[0].startswith("## "))
    i = 0
    pending_quotes = []

    def flush_quotes():
        nonlocal pending_quotes
        if pending_quotes:
            q_text = " ".join(pending_quotes).strip()
            html_parts.append(
                f'<blockquote style="margin: 20px 0; padding: 14px 18px; border-left: 4px solid #f59e0b; '
                f'background: rgba(245, 158, 11, 0.08); color: #fde68a; border-radius: 0 12px 12px 0;">'
                f'<p style="margin: 0; font-size: 15px; line-height: 1.7;">{q_text}</p></blockquote>'
            )
            pending_quotes = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if re.match(r'^\s*<!--.*-->\s*$', line):
            i += 1; continue
        if skip_h1 and i == 0 and stripped.startswith("# ") and not stripped.startswith("## "):
            skip_h1 = False; i += 1; continue
        if stripped in ("---", "***", "* * *"):
            flush_quotes()
            html_parts.append('<hr style="border: none; height: 1px; background: linear-gradient(90deg, #78350f, #f59e0b, #78350f); margin: 30px 0;" />')
            i += 1; continue
        if stripped.startswith("> "):
            pending_quotes.append(inline_format(stripped[2:]))
            i += 1; continue
        else:
            flush_quotes()

        if stripped.startswith("## "):
            title = inline_format(stripped[3:].strip())
            html_parts.append(f'<h2 style="font-size: 21px; font-weight: 800; color: #fbbf24; border-bottom: 2px solid #b45309; padding-bottom: 8px; margin: 32px 0 16px;">{title}</h2>')
            i += 1; continue
        if stripped.startswith("### "):
            title = inline_format(stripped[4:].strip())
            html_parts.append(f'<h3 style="margin: 24px 0 12px; font-size: 17px; font-weight: 700; color: #f59e0b;">{title}</h3>')
            i += 1; continue

        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
        if img_match:
            alt, path = img_match.group(1), img_match.group(2)
            img_info = image_map.get(path) or image_map.get(Path(path).name)
            caption = img_info.get("caption", "") if img_info else ""
            peek = i + 1
            while peek < len(lines) and lines[peek].strip() == "": peek += 1
            if not caption and peek < len(lines):
                cap_match = re.match(r'^\*([^*]+)\*$', lines[peek].strip())
                if cap_match: caption = cap_match.group(1); i = peek
            if img_info:
                html_parts.append(dark_gold_image_block(img_info["url"], alt or img_info.get("alt", ""), caption))
            else:
                html_parts.append(f'<!-- ⚠️ 图片未映射: {path} -->')
            i += 1; continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            items = []
            while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")):
                items.append(f'<li style="margin: 0 0 8px;">{inline_format(lines[i].strip()[2:])}</li>')
                i += 1
            html_parts.append('<ul style="margin: 15px 0; padding-left: 24px; color: #d6d3d1;">' + "".join(items) + '</ul>')
            continue

        if not stripped:
            i += 1; continue
        if stripped.startswith('<') and re.search(r'</[a-z]+>$', stripped):
            html_parts.append(stripped); i += 1; continue
        html_parts.append(f'<p style="margin: 0 0 16px; font-size: 16px; text-align: justify; color: #e7e5e4;">{inline_format(stripped)}</p>')
        i += 1

    flush_quotes()
    if hashtags:
        html_parts.append(f'<div style="text-align: center; margin: 28px 0 14px; font-size: 13px; color: #f59e0b; letter-spacing: 0.5px;">{hashtags}</div>')
    html_parts.append(
        '<p style="margin: 30px 0 0; font-size: 14px; color: #a8a29e; text-align: center; line-height: 1.8; border-top: 1px solid #292524; padding-top: 20px;">'
        '我是宇龙，专注 AI Agent 场景应用落地</p>'
    )
    html_parts.append('<p style="display: none;"><mp-style-type data-value="10000"></mp-style-type></p></section>')
    return "\n".join(html_parts)


# ---------------------------------------------------------------------------
# 主题 6: 极简纯粹 (minimal)
# ---------------------------------------------------------------------------

def minimal_image_block(url: str, alt: str, caption: str) -> str:
    return (
        '<p style="text-align: center; margin: 24px 0 8px;">'
        f'<img src="{url}" alt="{alt}" '
        'style="max-width: 100%; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.06); height: auto !important;">'
        '</p>'
        f'<p style="text-align: center; color: #6b7280; font-size: 13px; margin: 0 0 24px;">{caption}</p>'
    )

def render_markdown_to_minimal_html(markdown_text: str, image_map: dict) -> str:
    clean_text, hashtags = clean_markdown_text(markdown_text)
    lines = clean_text.splitlines()
    html_parts = [
        '<section style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, '
        '\'Helvetica Neue\', Arial, sans-serif; font-size: 16px; color: #1f2937; line-height: 1.85; '
        'padding: 24px 16px; background: #ffffff; box-sizing: border-box;">',
    ]

    def inline_format(text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="font-weight: 700; color: #111827;">\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em style="color: #4b5563;">\1</em>', text)
        text = re.sub(r'`(.+?)`', r'<code style="background: #f3f4f6; color: #111827; padding: 2px 5px; border-radius: 3px;">\1</code>', text)
        return text

    skip_h1 = bool(lines and lines[0].startswith("# ") and not lines[0].startswith("## "))
    i = 0
    pending_quotes = []

    def flush_quotes():
        nonlocal pending_quotes
        if pending_quotes:
            q_text = " ".join(pending_quotes).strip()
            html_parts.append(
                f'<blockquote style="margin: 20px 0; padding: 12px 16px; border-left: 3px solid #111827; '
                f'background: #f9fafb; color: #374151; border-radius: 0 6px 6px 0;">'
                f'<p style="margin: 0; font-size: 15px; line-height: 1.7;">{q_text}</p></blockquote>'
            )
            pending_quotes = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if re.match(r'^\s*<!--.*-->\s*$', line):
            i += 1; continue
        if skip_h1 and i == 0 and stripped.startswith("# ") and not stripped.startswith("## "):
            skip_h1 = False; i += 1; continue
        if stripped in ("---", "***", "* * *"):
            flush_quotes()
            html_parts.append('<hr style="border: none; border-top: 1px dashed #e5e7eb; margin: 30px 0;" />')
            i += 1; continue
        if stripped.startswith("> "):
            pending_quotes.append(inline_format(stripped[2:]))
            i += 1; continue
        else:
            flush_quotes()

        if stripped.startswith("## "):
            title = inline_format(stripped[3:].strip())
            html_parts.append(f'<h2 style="font-size: 20px; font-weight: 800; color: #111827; border-left: 4px solid #111827; padding-left: 10px; margin: 32px 0 16px;">{title}</h2>')
            i += 1; continue
        if stripped.startswith("### "):
            title = inline_format(stripped[4:].strip())
            html_parts.append(f'<h3 style="margin: 22px 0 10px; font-size: 17px; font-weight: 700; color: #374151;">{title}</h3>')
            i += 1; continue

        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
        if img_match:
            alt, path = img_match.group(1), img_match.group(2)
            img_info = image_map.get(path) or image_map.get(Path(path).name)
            caption = img_info.get("caption", "") if img_info else ""
            peek = i + 1
            while peek < len(lines) and lines[peek].strip() == "": peek += 1
            if not caption and peek < len(lines):
                cap_match = re.match(r'^\*([^*]+)\*$', lines[peek].strip())
                if cap_match: caption = cap_match.group(1); i = peek
            if img_info:
                html_parts.append(minimal_image_block(img_info["url"], alt or img_info.get("alt", ""), caption))
            else:
                html_parts.append(f'<!-- ⚠️ 图片未映射: {path} -->')
            i += 1; continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            items = []
            while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")):
                items.append(f'<li style="margin: 0 0 8px;">{inline_format(lines[i].strip()[2:])}</li>')
                i += 1
            html_parts.append('<ul style="margin: 15px 0; padding-left: 24px; color: #4b5563;">' + "".join(items) + '</ul>')
            continue

        if not stripped:
            i += 1; continue
        if stripped.startswith('<') and re.search(r'</[a-z]+>$', stripped):
            html_parts.append(stripped); i += 1; continue
        html_parts.append(f'<p style="margin: 0 0 16px; font-size: 16px; text-align: justify; color: #1f2937;">{inline_format(stripped)}</p>')
        i += 1

    flush_quotes()
    if hashtags:
        html_parts.append(f'<div style="text-align: center; margin: 28px 0 14px; font-size: 13px; color: #6b7280; letter-spacing: 0.5px;">{hashtags}</div>')
    html_parts.append(
        '<p style="margin: 30px 0 0; font-size: 14px; color: #9ca3af; text-align: center; line-height: 1.8; border-top: 1px solid #f3f4f6; padding-top: 20px;">'
        '我是宇龙，专注 AI Agent 场景应用落地</p>'
    )
    html_parts.append('<p style="display: none;"><mp-style-type data-value="10000"></mp-style-type></p></section>')
    return "\n".join(html_parts)


# ---------------------------------------------------------------------------
# 主题 7: 优雅暮蓝 (twilight)
# ---------------------------------------------------------------------------

def twilight_image_block(url: str, alt: str, caption: str) -> str:
    return (
        '<p style="text-align: center; margin: 24px 0 8px;">'
        f'<img src="{url}" alt="{alt}" '
        'style="max-width: 100%; border-radius: 8px; box-shadow: 0 4px 14px rgba(59,130,246,0.12); height: auto !important;">'
        '</p>'
        f'<p style="text-align: center; color: #64748b; font-size: 13px; margin: 0 0 24px;">{caption}</p>'
    )

def render_markdown_to_twilight_html(markdown_text: str, image_map: dict) -> str:
    clean_text, hashtags = clean_markdown_text(markdown_text)
    lines = clean_text.splitlines()
    html_parts = [
        '<section style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, '
        '\'Helvetica Neue\', Arial, sans-serif; font-size: 16px; color: #0f172a; line-height: 1.85; '
        'padding: 24px 20px; background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 50%, #e2e8f0 100%); '
        'box-sizing: border-box;">',
    ]

    def inline_format(text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="font-weight: bold; color: #1d4ed8;">\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em style="color: #2563eb;">\1</em>', text)
        text = re.sub(r'`(.+?)`', r'<code style="background: #e2e8f0; color: #1e3a8a; padding: 2px 6px; border-radius: 4px;">\1</code>', text)
        return text

    skip_h1 = bool(lines and lines[0].startswith("# ") and not lines[0].startswith("## "))
    i = 0
    pending_quotes = []

    def flush_quotes():
        nonlocal pending_quotes
        if pending_quotes:
            q_text = " ".join(pending_quotes).strip()
            html_parts.append(
                f'<blockquote style="margin: 20px 0; padding: 14px 18px; border-left: 4px solid #3b82f6; '
                f'background: rgba(59, 130, 246, 0.08); color: #1e3a8a; border-radius: 0 10px 10px 0;">'
                f'<p style="margin: 0; font-size: 15px; line-height: 1.7;">{q_text}</p></blockquote>'
            )
            pending_quotes = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if re.match(r'^\s*<!--.*-->\s*$', line):
            i += 1; continue
        if skip_h1 and i == 0 and stripped.startswith("# ") and not stripped.startswith("## "):
            skip_h1 = False; i += 1; continue
        if stripped in ("---", "***", "* * *"):
            flush_quotes()
            html_parts.append('<hr style="border: none; height: 2px; background: linear-gradient(90deg, #60a5fa, #3b82f6, #1d4ed8); margin: 30px 0;" />')
            i += 1; continue
        if stripped.startswith("> "):
            pending_quotes.append(inline_format(stripped[2:]))
            i += 1; continue
        else:
            flush_quotes()

        if stripped.startswith("## "):
            title = inline_format(stripped[3:].strip())
            html_parts.append(f'<h2 style="font-size: 21px; font-weight: 800; color: #2563eb; border-bottom: 2px solid #bfdbfe; padding-bottom: 8px; margin: 32px 0 16px;">{title}</h2>')
            i += 1; continue
        if stripped.startswith("### "):
            title = inline_format(stripped[4:].strip())
            html_parts.append(f'<h3 style="margin: 24px 0 12px; font-size: 17px; font-weight: 700; color: #1d4ed8;">{title}</h3>')
            i += 1; continue

        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
        if img_match:
            alt, path = img_match.group(1), img_match.group(2)
            img_info = image_map.get(path) or image_map.get(Path(path).name)
            caption = img_info.get("caption", "") if img_info else ""
            peek = i + 1
            while peek < len(lines) and lines[peek].strip() == "": peek += 1
            if not caption and peek < len(lines):
                cap_match = re.match(r'^\*([^*]+)\*$', lines[peek].strip())
                if cap_match: caption = cap_match.group(1); i = peek
            if img_info:
                html_parts.append(twilight_image_block(img_info["url"], alt or img_info.get("alt", ""), caption))
            else:
                html_parts.append(f'<!-- ⚠️ 图片未映射: {path} -->')
            i += 1; continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            items = []
            while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")):
                items.append(f'<li style="margin: 0 0 8px;">{inline_format(lines[i].strip()[2:])}</li>')
                i += 1
            html_parts.append('<ul style="margin: 15px 0; padding-left: 24px; color: #334155;">' + "".join(items) + '</ul>')
            continue

        if not stripped:
            i += 1; continue
        if stripped.startswith('<') and re.search(r'</[a-z]+>$', stripped):
            html_parts.append(stripped); i += 1; continue
        html_parts.append(f'<p style="margin: 0 0 16px; font-size: 16px; text-align: justify; color: #0f172a;">{inline_format(stripped)}</p>')
        i += 1

    flush_quotes()
    if hashtags:
        html_parts.append(f'<div style="text-align: center; margin: 28px 0 14px; font-size: 13px; color: #2563eb; letter-spacing: 0.5px;">{hashtags}</div>')
    html_parts.append(
        '<p style="margin: 30px 0 0; font-size: 14px; color: #64748b; text-align: center; line-height: 1.8; border-top: 1px solid #cbd5e1; padding-top: 20px;">'
        '我是宇龙，专注 AI Agent 场景应用落地</p>'
    )
    html_parts.append('<p style="display: none;"><mp-style-type data-value="10000"></mp-style-type></p></section>')
    return "\n".join(html_parts)


# ---------------------------------------------------------------------------
# 主题 8: 活力暖橙 (sunset)
# ---------------------------------------------------------------------------

def sunset_image_block(url: str, alt: str, caption: str) -> str:
    return (
        '<p style="text-align: center; margin: 24px 0 8px;">'
        f'<img src="{url}" alt="{alt}" '
        'style="max-width: 100%; border-radius: 10px; box-shadow: 0 4px 14px rgba(234,88,12,0.10); height: auto !important;">'
        '</p>'
        f'<p style="text-align: center; color: #9a3412; font-size: 13px; margin: 0 0 24px;">{caption}</p>'
    )

def render_markdown_to_sunset_html(markdown_text: str, image_map: dict) -> str:
    clean_text, hashtags = clean_markdown_text(markdown_text)
    lines = clean_text.splitlines()
    html_parts = [
        '<section style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, '
        '\'Helvetica Neue\', Arial, sans-serif; font-size: 16px; color: #292524; line-height: 1.85; '
        'padding: 24px 20px; background: linear-gradient(180deg, #fffbf7 0%, #fff7ed 50%, #ffedd5 100%); '
        'box-sizing: border-box;">',
    ]

    def inline_format(text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="font-weight: bold; color: #c2410c;">\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em style="color: #ea580c;">\1</em>', text)
        text = re.sub(r'`(.+?)`', r'<code style="background: #fed7aa; color: #7c2d12; padding: 2px 6px; border-radius: 4px;">\1</code>', text)
        return text

    skip_h1 = bool(lines and lines[0].startswith("# ") and not lines[0].startswith("## "))
    i = 0
    pending_quotes = []

    def flush_quotes():
        nonlocal pending_quotes
        if pending_quotes:
            q_text = " ".join(pending_quotes).strip()
            html_parts.append(
                f'<blockquote style="margin: 20px 0; padding: 14px 18px; border-left: 4px solid #ea580c; '
                f'background: rgba(234, 88, 12, 0.08); color: #7c2d12; border-radius: 0 10px 10px 0;">'
                f'<p style="margin: 0; font-size: 15px; line-height: 1.7;">{q_text}</p></blockquote>'
            )
            pending_quotes = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if re.match(r'^\s*<!--.*-->\s*$', line):
            i += 1; continue
        if skip_h1 and i == 0 and stripped.startswith("# ") and not stripped.startswith("## "):
            skip_h1 = False; i += 1; continue
        if stripped in ("---", "***", "* * *"):
            flush_quotes()
            html_parts.append('<hr style="border: none; height: 2px; background: linear-gradient(90deg, #fb923c, #ea580c, #c2410c); margin: 30px 0;" />')
            i += 1; continue
        if stripped.startswith("> "):
            pending_quotes.append(inline_format(stripped[2:]))
            i += 1; continue
        else:
            flush_quotes()

        if stripped.startswith("## "):
            title = inline_format(stripped[3:].strip())
            html_parts.append(f'<h2 style="font-size: 21px; font-weight: 800; color: #ea580c; border-bottom: 2px solid #fdba74; padding-bottom: 8px; margin: 32px 0 16px;">{title}</h2>')
            i += 1; continue
        if stripped.startswith("### "):
            title = inline_format(stripped[4:].strip())
            html_parts.append(f'<h3 style="margin: 24px 0 12px; font-size: 17px; font-weight: 700; color: #c2410c;">{title}</h3>')
            i += 1; continue

        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
        if img_match:
            alt, path = img_match.group(1), img_match.group(2)
            img_info = image_map.get(path) or image_map.get(Path(path).name)
            caption = img_info.get("caption", "") if img_info else ""
            peek = i + 1
            while peek < len(lines) and lines[peek].strip() == "": peek += 1
            if not caption and peek < len(lines):
                cap_match = re.match(r'^\*([^*]+)\*$', lines[peek].strip())
                if cap_match: caption = cap_match.group(1); i = peek
            if img_info:
                html_parts.append(sunset_image_block(img_info["url"], alt or img_info.get("alt", ""), caption))
            else:
                html_parts.append(f'<!-- ⚠️ 图片未映射: {path} -->')
            i += 1; continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            items = []
            while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")):
                items.append(f'<li style="margin: 0 0 8px;">{inline_format(lines[i].strip()[2:])}</li>')
                i += 1
            html_parts.append('<ul style="margin: 15px 0; padding-left: 24px; color: #44403c;">' + "".join(items) + '</ul>')
            continue

        if not stripped:
            i += 1; continue
        if stripped.startswith('<') and re.search(r'</[a-z]+>$', stripped):
            html_parts.append(stripped); i += 1; continue
        html_parts.append(f'<p style="margin: 0 0 16px; font-size: 16px; text-align: justify; color: #292524;">{inline_format(stripped)}</p>')
        i += 1

    flush_quotes()
    if hashtags:
        html_parts.append(f'<div style="text-align: center; margin: 28px 0 14px; font-size: 13px; color: #ea580c; letter-spacing: 0.5px;">{hashtags}</div>')
    html_parts.append(
        '<p style="margin: 30px 0 0; font-size: 14px; color: #9a3412; text-align: center; line-height: 1.8; border-top: 1px solid #fed7aa; padding-top: 20px;">'
        '我是宇龙，专注 AI Agent 场景应用落地</p>'
    )
    html_parts.append('<p style="display: none;"><mp-style-type data-value="10000"></mp-style-type></p></section>')
    return "\n".join(html_parts)

def upload_video(token: str, video_path: Path, title: str = "") -> str:
    """上传视频到微信永久素材库，返回 media_id。"""
    import subprocess
    import json as _json
    video_title = video_path.stem[:64]
    description = {
        "title": video_title, 
        "introduction": video_title[:120]
    }
    
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=video"
    cmd = [
        "curl", "-s",
        "-F", f"media=@{video_path}",
        "-F", "description=" + _json.dumps(description, ensure_ascii=False),
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    data = _json.loads(result.stdout) if result.stdout else {}
    if "media_id" not in data:
        print(f"❌ 上传视频失败 {video_path}: {data}")
        sys.exit(1)
    return data["media_id"]


def make_video_block(media_id: str, caption: str = "👆 视频：实测豆包工作生成「乌鸦坐飞机」") -> str:
    """生成视频嵌入 HTML（微信草稿箱支持的 video 标签格式）。"""
    return (
        '<p style="text-align: center; margin: 30px 0 10px;">'
        f'<video mediawidget_nodeid="{media_id}" data-miniprogram-state="false" controls="controls" '
        'src="" preload="metadata" data-pluginname="video" style="max-width: 100%; border-radius: 8px;">'
        '</video>'
        '</p>'
        '<p style="text-align: center; color: #999; font-size: 13px; margin: 0 0 24px;">'
        f'{caption}</p>'
    )


def verify_article_str(text: str) -> int:
    """文章自检：PART字样、图片alt等，返回0表示通过"""
    errors = []
    # PART 字样检查
    for i, line in enumerate(text.splitlines(), 1):
        import re
        if re.search(r'\bPART\b', line, re.IGNORECASE):
            errors.append(f"  行 {i}: {line.strip()[:60]}")
    if errors:
        print(f"❌ 发现 PART 字样:\n" + "\n".join(errors))
        return 1
    # 图片alt检查（不能是空）
    images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', text)
    print(f"📷 Markdown 图片引用: {len(images)} 张")
    for alt, path in images:
        if not alt.strip():
            print(f"⚠️  {path} 的 alt 为空")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="微信公众号文章一键推送",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--markdown", required=True, help="Markdown 文件路径")
    parser.add_argument("--images", nargs="+", required=True, help="图片文件路径列表（按文章顺序）")
    parser.add_argument("--title", required=True, help="文章标题")
    parser.add_argument("--cover", required=True, help="封面图路径（从 --images 列表里选一个）")
    parser.add_argument("--author", default="宇龙", help="作者（默认：宇龙）")
    parser.add_argument("--digest", default="", help="文章摘要")
    parser.add_argument("--theme", default="purple", choices=["rainbow", "purple", "blue", "green", "dark-gold", "minimal", "twilight", "sunset"], help="渲染主题：rainbow/purple(紫色渐变)/blue(萌蓝)/green(萌绿,白底居中绿标题,需正文有##小标题)")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="凭据文件路径")
    parser.add_argument("--video", type=str, default=None, help="视频文件路径（可选）")
    parser.add_argument("--report-file", default="push-report.json", help="报告输出路径（默认：push-report.json）")
    parser.add_argument("--dry-run", action="store_true", help="只渲染 HTML，不推送")
    args = parser.parse_args()

    md_path = Path(args.markdown)
    cover_path = Path(args.cover)
    image_paths = [Path(p) for p in args.images]
    report_path = Path(args.report_file)
    env_file = Path(args.env_file)

    # 文件存在性检查
    for path in [md_path, cover_path] + image_paths:
        if not path.exists():
            print(f"❌ 文件不存在: {path}")
            sys.exit(1)
    if cover_path not in image_paths:
        print(f"⚠️  封面图 {cover_path} 不在 --images 列表里，将单独上传")

    print(f"📄 读取 Markdown: {md_path}")
    markdown_text = md_path.read_text(encoding="utf-8")

    # 文章自检（图片顺序 + PART 字样）
    print(f"\n🔍 文章自检...")
    verify_rc = verify_article_str(markdown_text)
    if verify_rc != 0:
        print(f"⚠️  自检发现问题（人工核对后确认可继续请忽略）")

    # 获取凭据
    if not args.dry_run:
        appid, appsecret = resolve_credentials(env_file)
        print("🔑 获取 access_token...")
        token = get_access_token(appid, appsecret)
        print("✅ access_token 获取成功")
    else:
        token = "DRY_RUN"
        print("🔧 dry-run 模式，跳过 API 调用")

    # 上传图片
    image_map: dict[str, dict] = {}
    uploads_log: list[dict] = []
    cover_media_id = ""
    cover_url = ""

    print(f"\n📤 上传图片（共 {len(image_paths)} 张）...")
    for idx, img_path in enumerate(image_paths, 1):
        print(f"  [{idx}/{len(image_paths)}] {img_path.name}...", end="", flush=True)
        if args.dry_run:
            url = f"https://mmbiz.qpic.cn/dry_run/{img_path.name}"
            print(f" [dry-run]")
        else:
            url = upload_article_image(token, img_path)
            print(f" ✅ {url[:60]}...")

        entry = {
            "path": str(img_path),
            "basename": img_path.name,
            "url": url,
            "alt": img_path.stem,
            "caption": "",  # 用户可在 Markdown 里通过图片语法自定义
        }
        image_map[str(img_path)] = entry
        image_map[img_path.name] = entry
        uploads_log.append(entry)

    # 上传封面图（add_material）
    print(f"\n🖼️  上传封面图: {cover_path.name}...")
    if args.dry_run:
        cover_media_id = "DRY_RUN_MEDIA_ID"
        cover_url = image_map.get(cover_path.name, {}).get("url", "")
        print("  [dry-run]")
    else:
        cover_upload = upload_cover_image(token, cover_path)
        cover_media_id = cover_upload["media_id"]
        cover_url = cover_upload["url"]
        # 更新 image_map 里封面图的 url（add_material 返回的 url 可能更稳定）
        if cover_path.name in image_map:
            image_map[cover_path.name]["url"] = cover_url
            image_map[str(cover_path)]["url"] = cover_url
        print(f"  ✅ thumb_media_id: {cover_media_id}")

    # 渲染 HTML
    print(f"\n🎨 渲染主题 HTML...")
    # 预处理：清洗尾部签名与提取 hashtag，杜绝重复签名
    cleaned_md, _ = clean_markdown_text(markdown_text)
    
    if args.theme == "purple":
        html = render_markdown_to_purple_html(cleaned_md, image_map)
    elif args.theme == "blue":
        html = render_markdown_to_blue_html(cleaned_md, image_map)
    elif args.theme == "green":
        html = render_markdown_to_green_html(cleaned_md, image_map)
    elif args.theme == "dark-gold":
        html = render_markdown_to_dark_gold_html(markdown_text, image_map)
    elif args.theme == "minimal":
        html = render_markdown_to_minimal_html(markdown_text, image_map)
    elif args.theme == "twilight":
        html = render_markdown_to_twilight_html(markdown_text, image_map)
    elif args.theme == "sunset":
        html = render_markdown_to_sunset_html(markdown_text, image_map)
    else:
        html = render_markdown_to_rainbow_html(cleaned_md, image_map)
    print(f"  ✅ HTML 长度: {len(html)} 字符，图片引用: {html.count('mmbiz.qpic.cn')} 张")

    # 如果有视频，嵌入到文章末尾（结尾签名前）
    if hasattr(args, 'video') and args.video:
        video_path = Path(args.video)
        if video_path.exists():
            print(f"\n🎬 上传视频: {video_path.name}...")
            video_url = upload_video(token, video_path, title=args.title)
            video_html = make_video_block(video_url)
            # 插入到结尾签名前（匹配两种主题的签名段）
            insert_marker = 'border-top: 1px solid #eee; padding'
            if insert_marker in html:
                html = html.replace(insert_marker, video_html + '\n' + insert_marker)
            else:
                # fallback: 插入到 </section> 前
                html = html.replace('</section>', video_html + '\n</section>')
            print(f"  ✅ 视频已嵌入: {video_url}")
        else:
            print(f"  ⚠️ 视频文件不存在: {args.video}")

    # 三项验证
    print("\n🔍 三项验证...")
    errors = validate_html(html, args.title)
    if errors:
        print("❌ 验证未通过：")
        for e in errors:
            print(f"   {e}")
        if not args.dry_run:
            sys.exit(1)
        else:
            print("  [dry-run] 忽略验证错误，继续...")
    else:
        print("  ✅ 全部通过")

    if args.dry_run:
        # 保存 HTML 到本地
        html_path = report_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")
        print(f"\n🔧 dry-run 完成，HTML 已保存: {html_path}")
        return

    # 推送草稿
    print(f"\n🚀 推送草稿: {args.title[:30]}...")
    push_result = push_draft(
        token=token,
        title=args.title,
        html=html,
        thumb_media_id=cover_media_id,
        author=args.author,
        digest=args.digest,
    )
    media_id = push_result["media_id"]
    print(f"  ✅ 草稿 media_id: {media_id}")

    # 验证草稿
    print("\n✔️  验证草稿已到账...")
    article = verify_draft(token, media_id)
    if "error" in article:
        print(f"  ⚠️  验证警告: {article['error']}")
    else:
        print(f"  ✅ 草稿验证通过: title='{article.get('title')}', content_length={len(article.get('content', ''))}")

    # 留存对比用存档（覆盖上次推送的内容）
    last_push_dir = Path(__file__).parent.parent / "archives" / "last-push"
    last_push_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(md_path, last_push_dir / "original.md")
    (last_push_dir / "pre-publish.html").write_text(html, encoding="utf-8")
    print(f"  ✅ 对比存档已留存: {last_push_dir}/original.md + pre-publish.html")

    # 输出报告
    report = {
        "title": args.title,
        "author": args.author,
        "markdown_file": str(md_path),
        "cover_image": str(cover_path),
        "cover_media_id": cover_media_id,
        "draft_media_id": media_id,
        "image_count": len(image_paths),
        "content_length": len(html),
        "mmbiz_image_count": html.count("mmbiz.qpic.cn"),
        "verified_title": article.get("title"),
        "verified_content_length": len(article.get("content", "")) if "error" not in article else 0,
        "uploads": uploads_log,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n📋 推送完成！报告: {report_path}")
    print(json.dumps({k: v for k, v in report.items() if k != "uploads"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
