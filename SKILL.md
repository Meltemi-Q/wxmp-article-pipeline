---
name: wxmp-article-pipeline
description: >
  微信公众号文章全流程发布工具。从 Markdown 文件到微信草稿箱的一键流水线，
  支持两种类型：文章（news，紫色主题排版）和贴图（newspic，纯文本+图片）。
  覆盖图片上传、主题渲染、封面选择、格式校验、推送验证、去重检查。
  当用户要求"推草稿箱""发公众号""渲染文章""发贴图/小绿书"时使用。
---

# wxmp-article-pipeline

微信公众号发布全流程 Skill。支持两种内容类型，踩过的坑都固化在这里。

---

## 零、先判断类型

| 类型 | 场景 | API | 排版 |
|------|------|-----|------|
| **文章 `news`** | 长内容、有多个段落和图片 | `draft/add` | 紫色主题 HTML |
| **贴图 `newspic`** | 短内容、朋友圈/小绿书风格 | `draft/add`（贴图模式） | 纯文本 + 图片，无 HTML |

**贴图限制**：
- `newspic` 的 `image_info` 必填，不支持零图片贴图
- 纯文字贴图只能走公众号 App 前端的"文字海报"入口
- 贴图标题 ≤ 20 个中文字符
- 内容只支持纯文本，不支持 HTML

---

## 一、流程总览

### 文章流程（news）
```
输入（Markdown + 图片）
  ↓
Step 1：逐张看图，确认内容与段落对应关系
  ↓
Step 2：上传图片到微信
  │  正文图片 → uploadimg → mmbiz.qpic.cn URL
  │  封面图   → add_material → thumb_media_id
  ↓
Step 3：渲染紫色主题 HTML（含 h2 标题、blockquote 金句、图注）
  ↓
Step 4：三项验证（标题/图片/正文长度）
  ↓
Step 5：去重检查（batchget 草稿箱，确认同标题不存在）
  ↓
Step 6：推送草稿箱（draft/add，ensure_ascii=False）
  ↓
Step 7：batchget 验证草稿已到账
  ↓
输出：report.json + 草稿 media_id
```

### 贴图流程（newspic）
```
输入（短文本 + 1~N 张图片）
  ↓
Step 1：上传图片到微信素材库（add_material）
  ↓
Step 2：组装 newspic payload
  ↓
Step 3：推送草稿箱
  ↓
输出：草稿 media_id
```

---

## 二、图片处理规则（最容易出错）

### 2.1 必须逐张看图确认

**绝对不能凭文件名猜图片内容。**

每张图都要用视觉工具实际查看，确认：
1. 图片实际内容是什么
2. 对应文章哪个段落
3. 图注应该怎么写

### 2.2 上传接口区分

| 用途 | 接口 | 返回 | 作用 |
|------|------|------|------|
| 正文图片 | `POST /cgi-bin/media/uploadimg` | `url`（mmbiz.qpic.cn） | 嵌入 HTML `<img src>` |
| 封面图 | `POST /cgi-bin/material/add_material?type=image` | `media_id` + `url` | draft/add 的 `thumb_media_id` |

**只有 `mmbiz.qpic.cn` 域名的图片才能在公众号正常显示。**

### 2.3 封面图选择

- 封面图必须单独上传 `add_material`，获得 `media_id`
- 封面一般选第一张有代表性的图，或专门设计的封面图
- 上传后记录 `media_id`，推送时传给 `thumb_media_id` 字段

---

## 三、渲染规则（紫色主题）

紫色主题是当前默认主题，基于已发布文章的真实样式提取。

### 3.1 整体容器

```html
<section style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  font-size: 16px; color: #333; line-height: 1.8; padding: 20px;
  background: linear-gradient(180deg, #fdf4ff 0%, #faf5ff 50%, #f5f3ff 100%);">
```

### 3.2 段落

```html
<p style="margin: 15px 0; text-align: justify;">正文内容</p>
```

### 3.3 H2 标题（代替 PART 编号）

```html
<h2 style="font-size: 22px; font-weight: bold; color: #7c3aed;
  border-bottom: 2px solid #c4b5fd; padding-bottom: 8px;
  margin: 25px 0 15px 0;">标题文字</h2>
```

### 3.4 金句 / 引用 → Blockquote

```html
<blockquote style="border-left: 4px solid #c084fc; padding: 15px 20px;
  margin: 20px 0; background: rgba(192, 132, 252, 0.1); color: #6b21a8;
  border-radius: 0 8px 8px 0;">
  <p style="margin: 15px 0; text-align: justify;">金句内容</p>
</blockquote>
```

### 3.5 加粗/强调

```html
<strong style="font-weight: bold; color: #6d28d9;">重点文字</strong>
```

### 3.6 分隔线

```html
<hr style="border: none; height: 2px;
  background: linear-gradient(90deg, #ec4899, #8b5cf6, #3b82f6);
  margin: 30px 0; border-radius: 1px;" />
```

### 3.7 图片 + 居中图注

```html
<p style="text-align: center; margin: 20px 0;">
  <img style="max-width: 100%; border-radius: 8px;
    box-shadow: rgba(0, 0, 0, 0.1) 0px 2px 8px;
    height: auto !important;"
    data-src="https://mmbiz.qpic.cn/..." alt="图片描述" />
</p>
<p style="text-align: center; color: #999; font-size: 13px; margin-bottom: 20px;">
  图注文字
</p>
```

### 3.8 列表

```html
<ul style="margin: 15px 0; padding-left: 25px;">
  <li style="margin: 8px 0;">列表项</li>
</ul>
```

### 3.9 结尾（不加手写签名）

公众号已有固定底部模板（关注引导、往期推荐），正文末尾**不加手写签名**。

- ❌ 不要加"我是宇龙，一个用 AI 搞副业的打工人。"
- ✅ 正文自然结束即可，结尾提到 AI 助手时点名 **OpenClaw**

> 来源：2026-03-20 Yulong 审稿确认，手写签名显得套路化和重复

### 3.10 负面评价软化

| 原稿写法 | 发布时处理 |
|---------|----------|
| "速度有点慢" | 删掉或改中性描述 |
| "推脱，不肯动" | "需要再催一句" |
| 提及具体政治性描述 | 删掉，只保留行为描述 |

### 3.11 mp-style-type 标记

文章末尾加上（微信编辑器识别用）：

```html
<p style="display: none;"><mp-style-type data-value="10000"></mp-style-type></p>
```

---

## 四、推送前验证（必须全过才能推）

### ① 去重检查（新增！）

推送前先调用 `draft/batchget` 查看草稿箱，确认**同标题的草稿不存在**。
如果已存在同标题草稿，**必须告知用户并等确认**，不要重复推送。

### ② 正文无重复标题

Markdown 第一行 `# 标题` 会和 API `title` 字段重复。

**修复：** 渲染 HTML 时去掉第一个 `<h1>`，避免草稿箱显示双标题。

### ③ 所有图片已替换为微信 URL

HTML 里不能有：
- 本地路径（`/root/.openclaw/...`）
- `meltemi.fun` 的 URL
- 第三方图片 URL / http 协议图片

### ④ 正文长度 > 0

```python
assert len(html.strip()) > 100
```

---

## 五、推送草稿（关键：编码）

**必须用 `ensure_ascii=False` + 手动编码：**

```python
payload = {
    "articles": [{
        "title": title,
        "content": html,
        "thumb_media_id": thumb_media_id,
        "author": author,
        "digest": digest,
        "need_open_comment": 1,
        "only_fans_can_comment": 0,
    }]
}
json_str = json.dumps(payload, ensure_ascii=False)
response = requests.post(
    f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}",
    data=json_str.encode("utf-8"),
    headers={"Content-Type": "application/json; charset=utf-8"},
    timeout=180,
)
```

❌ **不能用 `requests.post(url, json=payload)`** — 中文会变 `\uXXXX`，草稿箱乱码。

---

## 六、常见踩坑速查

| 坑 | 现象 | 解决 |
|----|------|------|
| 标题重复 | 草稿箱标题出现两次 | 去掉 HTML 里第一行 `# 标题` |
| 图片不显示 | 草稿里图片是叉叉 | 重新上传到微信，替换为 mmbiz URL |
| 中文乱码 | 内容全是 `\u4e2d\u6587` | 改用 `ensure_ascii=False` |
| 封面图错误 | 缩略图不对 | 重新上传封面图获取正确 `media_id` |
| 重复推送 | 同一篇草稿箱出现多次 | **推前 batchget 去重检查** |
| 贴图用了文章 API | 格式错误 | 贴图用 `newspic`，文章用 `news` |
| 标题太长 | API 报 `45003` | 文章 ≤ 64 字，贴图 ≤ 20 字 |
| `<!-- 配图 -->` 残留 | HTML 出现注释文字 | 渲染前删掉所有 HTML 注释 |

---

## 七、凭据位置

```
/root/.openclaw/secrets/wxmp-yulong.env
```

包含 `WXMP_APPID` 和 `WXMP_APPSECRET`。

---

## 八、写作风格速查

详见 WRITING-GUIDE.md 和 YULONG-VOICE.md。

**核心要点：**
- 说人话，不说技术黑话
- 口语化短句，像跟朋友发微信
- H2 标题分段，不用 PART 编号
- 金句用 Blockquote 引用块
- 每图必须有图注
- 结尾不加手写签名，提到 AI 助手时点名 OpenClaw
- 负面评价软化处理

---

## 九、主题扩展

当前默认主题为**紫色主题**。后续如需新增主题，在本文件"三、渲染规则"中新增对应章节即可，通过参数 `--theme` 切换。
