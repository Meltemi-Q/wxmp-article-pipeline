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
输入（素材/图片）
  ↓
Step 0（必读）：
  │  读写作风格指南：references/writing-style.md
  │  读术语表：references/GLOSSARY.md
  │  读最近3篇历史文章：references/HISTORICAL-ARTICLES.md
  ↓
Step 1：逐张看图，确认内容与段落对应关系
  ↓
Step 2：存档图片识别结果为 MD（如 ClawBot 已有识别结果，保存到 archives/）
  ↓
Step 3：列大纲给用户确认（标题 + PART结构 + 图片选择）
  ↓
Step 4：用户确认后写全文
  ↓
Step 5：上传图片到微信
  │  正文图片 → uploadimg → mmbiz.qpic.cn URL
  │  封面图   → add_material → thumb_media_id
  ↓
Step 6：渲染紫色主题 HTML（含 PART 标题、blockquote 金句、图注）
  ↓
Step 7：三项验证（标题/图片/正文长度）
  ↓
Step 8：去重检查（batchget 草稿箱，确认同标题不存在）
  ↓
Step 9：推送草稿箱（draft/add，ensure_ascii=False）
  ↓
Step 10：batchget 验证草稿已到账
  ↓
Step 11：更新 HISTORICAL-ARTICLES.md（记录新草稿）
  ↓
Step 12：更新 REVISION-TRACKING.md（记录推送记录）
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

## 二、历史文章下载（维护已发布存档）

### 2.1 存档结构（每篇文章一个文件夹）
```
archives/published/YYYY-MM-DD-标题slug/
  published.html   ← 微信发布版原文（真实渲染HTML，含样式+图片）
  content.md      ← 净化版Markdown（原写作稿，对比用）
```

### 2.2 查看文章列表
```bash
cd /root/.openclaw/skills/wxmp-wxdown && python3 scripts/wxdown-manage.py articles findyi --size 10
```

### 2.3 下载已发布文章（html + md 双版本）
```bash
cd /root/.openclaw/skills/wxmp-article-pipeline
python3 scripts/archive_articles.py                  # 拉全部（跳过已存档）
python3 scripts/archive_articles.py --since 2026-03-01  # 只拉指定日期之后的
python3 scripts/archive_articles.py --force           # 强制覆盖
python3 scripts/archive_articles.py --dry-run          # 只看计划不下载
python3 scripts/archive_articles.py --latest          # 只拉最新一篇
```

### 2.4 存档命名规范
```
YYYY-MM-DD-slug/              ← 文章文件夹（date + 标题前12字）
  published.html              ← 发布版原文（微信真实HTML）
  content.md                  ← 原写作稿（对比用）
```

### 2.5 更新索引
下载后自动更新 `references/HISTORICAL-ARTICLES.md`，在已发布文章表格添加一行。

### 2.6 首次初始化（把所有历史文章全部拉回来）
```bash
cd /root/.openclaw/skills/wxmp-article-pipeline
python3 scripts/archive_articles.py --force
```

---

## 三、图片处理规则（最容易出错）

### 3.1 必须逐张看图确认

**绝对不能凭文件名猜图片内容。**

每张图都要用视觉工具实际查看，确认：
1. 图片实际内容是什么
2. 对应文章哪个段落
3. 图注应该怎么写

### 3.2 上传接口区分

| 用途 | 接口 | 返回 | 作用 |
|------|------|------|------|
| 正文图片 | `POST /cgi-bin/media/uploadimg` | `url`（mmbiz.qpic.cn） | 嵌入 HTML `<img src>` |
| 封面图 | `POST /cgi-bin/material/add_material?type=image` | `media_id` + `url` | draft/add 的 `thumb_media_id` |

**只有 `mmbiz.qpic.cn` 域名的图片才能在公众号正常显示。**

### 3.3 封面图选择

- 封面图必须单独上传 `add_material`，获得 `media_id`
- 封面一般选第一张有代表性的图，或专门设计的封面图
- 上传后记录 `media_id`，推送时传给 `thumb_media_id` 字段

---

## 四、渲染规则（紫色主题）

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

## 五、推送前验证（必须全过才能推）

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

## 六、推送草稿（关键：编码）

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

## 七、常见踩坑速查

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
| PART 编号后面空着 | 只有"PART 1"没有描述 | PART 编号后必须加描述（如"PART 1 Skill是什么"） |
| 擅自改标题 | 标题被加词/改词 | 用户确认什么标题就用什么，不自己改 |
| 封面图自己想当然 | 封面图和用户意图不符 | 用户说用哪张就用哪张，不自己换 |
| 编造 Skill 名 | 文章里写了不存在的 Skill | 只写实际存在的 Skill，没有的不准编 |
| 改了内容不推送 | 本地改了但没推 | 直接推，让用户看草稿箱效果再反馈 |
| 正文残留杂字（如"小红书"） | 渲染后HTML里多了乱文字 | 推送前 grep HTML 查残留文字，手动删掉 |

---

## 八、凭据位置

```
/root/.openclaw/secrets/wxmp-yulong.env
```

包含 `WXMP_APPID` 和 `WXMP_APPSECRET`。

---

## 九、写作风格速查

详见 `references/writing-style.md`（必须读）和 `references/GLOSSARY.md`（术语表）。

**核心要点：**
- 说人话，不说技术黑话
- 口语化短句，像跟朋友发微信
- PART 编号分段（如"PART 1 Skill是什么"），编号后必须带描述，不能空着
- 金句用 Blockquote 引用块
- 每图必须有图注
- 结尾不加手写签名，提到 AI 助手时点名 OpenClaw
- 负面评价软化处理

---

## 十、主题扩展

当前默认主题为**紫色主题**。后续如需新增主题，在本文件"三、渲染规则"中新增对应章节即可，通过参数 `--theme` 切换。

---

## 十一、存档管理（发布后触发）

存档目的：保留原稿（content.md）和发布版（published.html），方便后续对比修改。

### 触发点一：发布好了（刚发布完）

**触发条件**：用户说"发布好了"、"发完了"、"发布了"。

**操作**：用 `archive_articles.py --latest` 拉取最新一篇文章，存档 html + md。

**判断逻辑**：
1. 调用 `wxdown articles findyi --size 1` 获取最新文章标题+链接
2. 与 HISTORICAL-ARTICLES.md 最新行对比
3. 如果链接不同 → 是新发布的 → 下载存档
4. 如果链接相同 → 已是最新存档 → 告知"已存档，无需重复拉取"

### 触发点二：写新文章前（检查漏拉）

**触发条件**：用户说"写"、"开始写"、"写文章"。

**操作**：检查 HISTORICAL-ARTICLES.md 里所有文章，找出还没有 `published.html` 的文章，先批量拉取，再开始写。

**操作步骤**：
1. 读取 HISTORICAL-ARTICLES.md，遍历所有文章链接
2. 对每篇检查 `archives/published/YYYY-MM-DD-slug/published.html` 是否存在
3. 缺失的批量下载（用 `archive_articles.py --force` 或逐篇下载）
4. 完成后汇报"已补拉 X 篇历史文章，现在开始写"
5. 然后按正常流程（一～十）走

### 两种触发对比

| 触发点 | 场景 | 操作 |
|--------|------|------|
| 发布好了 | 用户刚点发布 | 立刻拉最新一篇 `--latest` |
| 写文章前 | 用户要写新文章 | 先检查+补拉漏掉的历史文章，再开始写 |
