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

注意: 密钥从 /root/.openclaw/secrets/wxmp-yulong.env 读取，不要在命令行传密钥。
"""
import argparse
import json
import mimetypes
import os
import re
import sys
from pathlib import Path

import requests

DEFAULT_ENV_FILE = Path("/root/.openclaw/secrets/wxmp-yulong.env")


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
                    alt=img_info.get("alt", alt),
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
        '我是宇龙，一个用 AI 搞副业的打工人。</p>'
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
    if "meltemi.fun" in html:
        errors.append("② 正文包含内网图片 URL（meltemi.fun），请替换为微信 URL")
    if "<!-- ⚠️" in html:
        count = html.count("<!-- ⚠️")
        errors.append(f"② 有 {count} 张图片未映射（image_map 里找不到），请补充图片映射")

    # ③ 正文长度 > 0
    if len(html.strip()) < 100:
        errors.append("③ 正文内容过短（< 100 字符），可能渲染失败")

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
                    alt=img_info.get("alt", alt),
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
        '我是宇龙，一个用 AI 搞副业的打工人。</p>'
    )
    html_parts.append(
        '<p style="display: none;"><mp-style-type data-value="10000"></mp-style-type></p>'
    )
    html_parts.append('</section>')

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


def make_video_block(media_id: str) -> str:
    """生成视频嵌入 HTML（微信草稿箱支持的 video 标签格式）。"""
    return (
        '<p style="text-align: center; margin: 30px 0;">'
        f'<video mediawidget_nodeid="{media_id}" data-miniprogram-state="false" controls="controls" '
        'src="" preload="metadata" data-pluginname="video" style="max-width: 100%; border-radius: 8px;">'
        '</video>'
        '</p>'
        '<p style="text-align: center; color: #999; font-size: 13px; margin-bottom: 20px;">'
        '👆 视频来源：X (Twitter)</p>'
    )


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
    parser.add_argument("--theme", default="purple", choices=["rainbow", "purple"], help="渲染主题（当前只支持 rainbow）")
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
    if args.theme == "purple":
        html = render_markdown_to_purple_html(markdown_text, image_map)
    else:
        html = render_markdown_to_rainbow_html(markdown_text, image_map)
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
