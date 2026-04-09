# 微信公众号推送踩坑指南

> 来源：memory/wxmp-draft-guide.md + 实际操作经验沉淀

---

## 快速查表

| 现象 | 根因 | 解决 |
|------|------|------|
| 草稿正文中文全是 `\u4e2d\u6587` 乱码 | 用了 `requests.post(json=payload)` | 改为 `ensure_ascii=False` + 手动 encode |
| 草稿标题出现两次 | Markdown 第一行是 `# 标题` | 渲染前删掉第一行 `# 标题` |
| 图片在草稿里是叉叉 | 用了本地路径或外部 URL | 重新上传到微信，换成 mmbiz.qpic.cn URL |
| 封面图显示错误 | `thumb_media_id` 传错了 | 单独用 `add_material` 上传封面，获取正确 media_id |
| API 报 `45003` | 标题超长 | 压缩到 20 个汉字以内 |
| `<!-- 配图 -->` 注释出现在正文 | HTML 注释没清除 | 渲染前/渲染后过滤掉 HTML 注释 |
| 小绿书推送失败 | 用了 `news` 接口 | 贴图用 `newspic`，长文章用 `news` |
| 图片内容和段落对不上 | 凭文件名猜图片内容 | 逐张用视觉工具看图，不猜 |
| 待审区 API 返回 401 | 用了 Authorization header | 待审区用 cookie 认证，不是 Bearer token |

---

## 详细说明

### 1. 中文乱码（最常见）

**现象：** 草稿箱里的中文变成 `\u8fd9\u662f\u6e2c\u8bd5`

**根因：**
```python
# ❌ 错误写法：requests 默认用 ensure_ascii=True 序列化 JSON
requests.post(url, json=payload)
```

**解决：**
```python
# ✅ 正确写法：手动序列化，禁止 ASCII 转义
json_str = json.dumps(payload, ensure_ascii=False)
requests.post(
    url,
    data=json_str.encode("utf-8"),
    headers={"Content-Type": "application/json; charset=utf-8"},
)
```

---

### 2. 标题重复出现两次

**现象：** 草稿箱文章标题区域显示两遍标题

**根因：** Markdown 文件第一行是 `# 文章标题`，渲染后变成 HTML 里的一个 `<h1>` 或 `<h2>`。推送时 API `title` 字段又传了一遍，公众号同时显示两个标题。

**解决：**
1. 渲染前删掉 Markdown 第一行的 `# 标题`（只删第一行，不影响 PART 结构里的 `## 小节标题`）
2. 或渲染后检查 HTML，确保第一个可见文字不和 `title` 字段相同

```python
# 简单去重：删掉 HTML 里第一个 <h1> 或以标题为内容的 <p>
import re
html = re.sub(r'<h1[^>]*>.*?</h1>', '', html, count=1, flags=re.DOTALL)
```

---

### 3. 图片不显示（叉叉）

**现象：** 推送成功，但草稿里图片全是叉

**根因：** 图片 URL 不在微信白名单内。以下情况都会出现叉：
- 本地文件路径（`/root/.openclaw/...`）
- 内网图片（`wxmp.meltemi.fun`）
- http 协议的外部图片
- 临时图片 URL

**解决：** 每张图必须先上传到微信，使用返回的 `mmbiz.qpic.cn` URL。

**接口：**
```
POST https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={token}
form-data: media=<文件>
返回: {"url": "https://mmbiz.qpic.cn/..."}
```

**验证：**
```python
# 推送前检查所有图片都是微信域名
assert html.count("mmbiz.qpic.cn") >= len(images)
assert "/root/" not in html
assert "meltemi.fun" not in html
```

---

### 4. 封面图不对

**现象：** 草稿缩略图显示了错误的图片，或者是白色占位图

**根因：**
- `thumb_media_id` 传错了
- 使用了正文图片的 `media_id`（虽然格式相同，但语义不同）
- 封面图没有单独用 `add_material` 上传

**解决：**
1. 封面图必须用 `add_material?type=image` 上传，获取 `media_id`
2. 正文图片用 `uploadimg` 上传，获取 `url`
3. 两个接口不能混用

```python
# 封面图上传
def upload_cover(token, image_path):
    with open(image_path, "rb") as f:
        r = requests.post(
            f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image",
            files={"media": (Path(image_path).name, f, "image/jpeg")},
        )
    return r.json()["media_id"]  # ← 这个才是 thumb_media_id
```

---

### 5. 标题超长（45003 错误）

**现象：** API 返回 `{"errcode": 45003, "errmsg": "title size out of limit"}`

**规则：** 标题长度限制约 64 字节（约 20 个汉字，或 40 个英文字符）

**特别注意：** 特殊字符（`×`、`·`、`—`）在某些编码下占多个字节，可能意外触发超长。

**解决：**
```python
title = title[:20]  # 汉字安全截断
# 或更精确：
while len(title.encode("utf-8")) > 60:
    title = title[:-1]
```

---

### 6. `<!-- 配图 -->` 注释出现在正文

**现象：** 草稿里出现文字 `<!-- 配图：file_185 -->`

**根因：** Markdown 里用 HTML 注释标记图片位置，渲染时没过滤掉

**解决：**
```python
import re
# 渲染前或渲染后，清除所有 HTML 注释
html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
```

---

### 7. 小绿书（贴图）vs 长文章 接口混淆

**现象：** 推送成功但格式完全不对，或 API 报错

**区别：**

| 类型 | API 接口 | article_type | 正文格式 |
|------|---------|-------------|---------|
| 长文章 | `draft/add` | `news` | 完整 HTML |
| 贴图（小绿书） | `draft/add` | `newspic` | 纯文本（≤1000字）+ 图片 list |

**小绿书限制：**
- 标题 ≤ 32 字
- 正文 ≤ 1000 字（纯文本，不支持 HTML）
- 图片最多 20 张
- 正文字段用 `content`，图片用 `image_info.image_list`

---

### 8. 待审区 API 认证方式

**现象：** 调用 `wxmp.meltemi.fun` API 返回 401

**根因：** 待审区是本地工作台，用的是 cookie 认证，不是 Bearer token / Authorization header

**解决：**
```python
# ✅ 待审区请求，用 token 作为查询参数或 cookie
headers = {"Cookie": f"token={LOCAL_TOKEN}"}
# 或者 URL 里带 token
# http://127.0.0.1:8070/api/drafts?token={LOCAL_TOKEN}
```

**注意：** 微信公众号 API 才用 `access_token` 查询参数，不要混淆。

---

## 凭据文件位置

```
/root/.openclaw/secrets/wxmp-yulong.env
```

包含：
- `WXMP_APPID`
- `WXMP_APPSECRET`

读取方法：
```python
from pathlib import Path

def load_env(path=Path("/root/.openclaw/secrets/wxmp-yulong.env")):
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env
```
