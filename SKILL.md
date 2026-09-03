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

## 快速命令速查

```bash
python3 /root/.openclaw/workspace/projects/wxmp-studio/scripts/review_helper.py freeze-latest
curl -s http://127.0.0.1:8070/api/themes | jq
cd /root/.openclaw/skills/wxmp-article-pipeline && python3 scripts/archive_articles.py --latest
cd /root/.openclaw/skills/wxmp-article-pipeline && python3 scripts/push_article.py --help
node /root/.openclaw/skills/wxmp-article-pipeline/scripts/wxmp-draft-to-feishu.js /root/wxmp-studio/drafts/claude-design-2026-04-18/article.md --dry-run
python3 /root/.openclaw/skills/wxmp-article-pipeline/scripts/wxmp_article_contract_qc.py --expected-images "a.png,b.jpg" --output /tmp/article.md
curl -s -b /tmp/wxmp_cookie.txt -H 'content-type: application/json' -d '{"mode":"article","action":"one_pass"}' https://wxmp.meltemi.vip/api/drafts/<draft_id>/writing-prompt
/usr/local/bin/wxmp-sync mp-sync --limit 200
python3 /root/.openclaw/skills/wxmp-article-pipeline/scripts/pull_comments.py --appmsgid 2247485899
```

## 短句入口（用户日常只需要这样说）

用户不需要提供长 prompt。遇到下面这种 50-100 字短句时，直接按映射执行，不要反问：

| 用户短句 | 默认解释 | 必跑入口 |
|---|---|---|
| “根据 wxmp 最新草稿写公众号文章推草稿箱” | 最新草稿 + `article` + 一键写稿/推草稿 | `python3 /root/.openclaw/workspace/projects/wxmp-studio/scripts/wxmpctl.py prompt latest --mode article --action one_pass` |
| “根据 wxmp 最新草稿写一篇公众号文章，先给我审” | 最新草稿 + `article` + 只写不推 | `python3 /root/.openclaw/workspace/projects/wxmp-studio/scripts/wxmpctl.py prompt latest --mode article --action write_only` |
| “根据 wxmp 最新草稿发贴图/小绿书” | 最新草稿 + `newspic` + 一键写稿/推草稿 | `python3 /root/.openclaw/workspace/projects/wxmp-studio/scripts/wxmpctl.py prompt latest --mode newspic --action one_pass` |
| “根据 wxmp 最新草稿写贴图，先给我看” | 最新草稿 + `newspic` + 只写不推 | `python3 /root/.openclaw/workspace/projects/wxmp-studio/scripts/wxmpctl.py prompt latest --mode newspic --action write_only` |

执行纪律：

- 先跑上面的 `wxmpctl.py prompt latest ...`，不要直接根据聊天记录写。
- 用返回的结构化 prompt 写稿；它已经包含事实卡、图片块、article/newspic 分流和 QC 命令。
- `推草稿箱/一键/直接发` = `--action one_pass`；`先给我看/先审/写一版` = `--action write_only`。
- 用户说“贴图/小绿书/图片帖”必须用 `--mode newspic`；用户说“文章/公众号文章”默认用 `--mode article`。
- QC 不过不要推送；先自修或只给失败项。

### 传图成稿（photo-to-draft，2026-08-16 定型）

触发词：「图发你了，直接出稿」「按这些图写一篇」「只有图，你先写个大概」，或用户只发一批截图/一个图多字少的飞书 wiki。目标：用户忙不过来时，只传图也能拿到「稍微调一下就能发」的稿子。

流程（顺序固定）：

1. **落地**：图先进 `materials/inbox/`（素材落地规则），再复制进草稿目录。
2. **识图 + 先出原话表**：逐张识图，按五拍排（现场 → 卡住 → 我来 → 意外 → 再试）。**先列出每张图里用户自己打的字**，写进 `manifest.md`，再动笔。表是空的，稿就是空的。详见 `references/story-grammar.md`。
3. **风格三层 + 骨架样本**（读取顺序固定）：
   - **先捞原句**：`python3 scripts/voice_fewshot.py --query "<本篇主题>" --n 8`（朋友圈 830 条 + 社群答疑 + 历史公众号；本机没有语料则 SKIP）
   - `~/Documents/WeChatArchive/corpus/persona_style.md`（口吻档案，摘要不够当 few-shot）
   - `references/personal-voice-rules.md` v6（四套味道 + 口吻按类型对照；自动化验收走自托管 AIGC）
   - `references/story-grammar.md`（先分流长文/短评，长文套五拍，禁止解说腔）
   - `references/golden-samples.md` 挑**同类型**发布版 1 篇当骨架（段数/拍序/引号位置；发布版 > 推送版 > AI 稿）
   - `references/style-benchmarks.md`（可选，最多 1 篇，仅当用户点名或自己样本缺该类型）
4. **用原话填骨架，不要织解说**：每一拍 = 用户原话或截图气泡 + 图 + 一句反应。AI 只写反应短句。禁止「它查了 / 回来说 / 它解释了」。图默认全用，图注描述腔（第七道硬闸），note 来源标「自动图注」。
5. **不编事实**：价格、时间、套餐名、数字拿不准就进「待确认项」，宁可空着让用户扫一眼。缺「卡住」素材也标待确认，不要用顺滑成功学补上。
6. **QC + 口吻 + 自托管 AIGC + 交付**：先套手改操作（段尾句号混合、图注无句号、标题砍第二分句），再跑 QC（含 stylometry + `voice_match`）。口吻 `UNLIKE` 或 `hits` 非空，先改到像他。自动化硬验收用 `scripts/aigc_check.sh`（VPS 本机 ONNX，无验证码；详见 `references/aigc-detector.md`）。`gate=pass`（接近 8/16 v5 / 短评锚点）才能自动交付；`review/fail` 先改稿。朱雀网页有验证码和额度，改抽检，能出分最好，出不了分不要卡死。不要把开源分写成朱雀四档。为刷分硬贴口头禅，口吻和检测一起掉。交付时写清原话来源：口述 / 截图气泡 / 几乎没有。几乎没有的，标注「建议发布前快速手改一遍」。默认 `write_only`，用户明说「直接推」才推草稿箱。
7. **发布后闭环**：用户发布后跑 `compare_publish_edits.py`，手改规律回写 v4 + 新发布版进 golden-samples。每发一篇，下一篇首稿就更像。
8. **想直接过检**：60 秒口述按五拍把故事讲完（语音转写 200 字也行）。这比让 AI 磨十轮都准。

## 触发词路由（先分流，再执行）

| 用户怎么说 | 用哪个 skill / 命令 | 目的 |
|---|---|---|
| “推草稿箱”“发公众号”“渲染文章”“发贴图/小绿书” | `wxmp-article-pipeline` | 写作、排版、上传、推草稿 |
| “抓一下刚发的”“冻结最新发布”“把刚发布的存档一下” | `python3 /root/.openclaw/workspace/projects/wxmp-studio/scripts/review_helper.py freeze-latest` | 抓最新已发布文章 HTML/MD，并加入 review tab |
| “查阅读量/点赞/分享/评论”“同步公众号数据”“做趋势分析” | `wxmp-sync` / `/usr/local/bin/wxmp-sync mp-sync --limit 200` | 同步后台指标到 SQLite/CSV |
| “看看评论”“读者说了啥”“把评论拉下来”“评论区有什么反馈” | `python3 scripts/pull_comments.py --appmsgid <id>` | 拉某篇文章的**评论正文**（昵称/内容/赞数/IP属地/作者回复）|
| “下载某个公众号文章”“搜索公众号”“扫码登录 wxdown” | `wxmp-wxdown` | wxdown 文章下载/关注列表/扫码登录 |
| “wxmp 草稿转飞书文档”“公众号草稿转飞书”“图片图注保留” | `node scripts/wxmp-draft-to-feishu.js <draft-dir-or-md>` | 从草稿 Markdown 创建飞书 Docx，正文在前、图片和图注在后 |
| “从草稿生成 prompt”“一键写稿”“企业服务受众”“直接成飞书” | `/api/drafts/{draft_id}/writing-prompt` | 由 wxmp 草稿生成结构化 Hermes 写作 prompt |

不要把 `freeze-latest` 和 `wxmp-sync sync-all` 混为一个入口：前者管“正文归档 + review tab”，后者管“指标落库 + CSV 导出”。

## 预览口径（不要混）

- wxmp-studio 草稿/待审预览：`http://127.0.0.1:8070/api/rendered/{id}`。
- wxdown 已发布文章静态导出：`http://wxmp.meltemi.vip/uploads/<name>.html`。
- 推草稿前看排版，优先用 wxmp-studio 渲染预览；复盘已发布文章原貌，才用 wxdown 静态导出。

## ⚠️ 最高优先级纪律（读这两条比读别的更重要）

### 🚦 防限流纪律（微信官方限流红线，2026-06 起，违反会限流）

来源：微信公众平台运营中心三类限流案例，宇龙号已被点名（《惊了！GPT…》被列为「导流内容」案例）。每篇发布前必过这一闸。

**① 导流（最高危，宇龙号已踩）——不要明着引导加私域**
- ❌ 不在正文直接插微信二维码、个人微信号、"扫码加我"。
- ❌ 不写"关注+私信『工具』送 XX 合集""备注公众号加我"这类「关注/转发换奖励」。
- ❌ 不做"内容只发一半，关注/加群才给全部"的诱导。
- ✅ 引导要藏暗、克制：结尾最多一句自然的"评论区聊聊/想聊的留言"，把交流留在公众号内（评论、留言），不往站外/私人号导。
- ✅ 真要留联系方式：只在「关于/菜单/自动回复」等非正文位置，正文不碰。

**② 低创作度——必须有信息增量**
- ❌ 同质化：和自己前几篇高度雷同的结构/主题，连发会被判低创作度。换角度、换主题。
- ❌ 纯 AIGC 直出、信息量不足的水文。
- ✅ 每篇必须有「只有你能写」的东西：真实操作、你的判断、独到观察、踩坑、对比结论。AI 只打初稿，观点和现场感是你的。

**③ 不良信息——封面/标题/正文别让人误解**
- ❌ 标题故意隐藏关键信息、信息不完整（标题党留悬念但不能藏掉主语）。
- ❌ 封面人物不完整、有明显水印标记、画质糊。
- ❌ 简单拼凑、重复文字堆砌、P 图拼接误导。
- ✅ 封面清晰完整、标题说清这篇讲什么。

**④ 版权——别让文章本身涉盗版/违法**
- 写到"下书/复制资源/破解"这类，重心放在「AI 拒绝盗版、坚持找正版」的正向结论上，不写成"教你白嫖盗版"的教程。
- 不给可直接照做的侵权步骤、盗版站点、破解方法。

发布前自检（任一条命中先改再发）：正文有没有二维码/微信号/"加我"？有没有"关注送/转发送"？标题是否藏了主语？封面是否清晰完整？这篇相对前几篇有没有新角度？有没有写成盗版/违规教程？

### 🈶 语言纪律：中文为主

- 所有面向用户的中间汇报、结论、`AskUserQuestion` 文案、内部 manifest 注释——**中文为主，技术术语保留英文**。
- **禁止夹带日语 / 法语 / 韩语**等其他外语。一旦发现自己切了别的语言，立刻切回中文重写本条回复。
- 用户上下文 / `CLAUDE.md` 是中文 = 默认中文输出。

### 🔁 重推纪律：先认领正确基底（第 ⑨ 道硬闸）

**任何"再推一次/再渲染一次/换封面/补一句话"之前，必须先 `draft/batchget` 同标题草稿，按 `update_time` 认领"用户最新手改版"——绝对不要拿自己上一次 push 出来的 media_id 当基底。**

正确流程：

```python
# 1. 列同标题草稿
items = draft_batchget(offset=0, count=20, no_content=0)["item"]
same_title = [i for i in items if i["content"]["news_item"][0]["title"].rstrip("！?？!") == base_title.rstrip("！?？!")]
same_title.sort(key=lambda i: i["update_time"], reverse=True)

# 2. 跳过"我自己刚推的"——如果最近一条的 update_time 就在 push 时刻 ±60s，且内容 = 我推上去的，剔除
# 3. 剩下最大 update_time 的那一条 = 用户最新手改版
canonical = same_title[0]
```

历史教训：一次写稿任务里推了 v6-v8 三版，用户其实一直只在 v6（`…P3Ny`）那条手改，我每次拿自己最新推的（`…sU4R` / `…EHY8`）当基底，三轮都拿错。

### 🪡 局部改动纪律：不重渲染（第 ⑩ 道硬闸）

**只换封面、只改标题、只改 digest、只删/补一句话——禁止整篇过 `push_article.py` 重渲染。**

重渲染会冲掉用户在草稿箱里的：emoji、`「」`、空格、表情、`➕`、自定义断行。

正确做法是「复制 content + 局部替换 + draft/add」：

```python
# 1. 取用户最新版的 content HTML 原样
art = draft_get(canonical["media_id"])["news_item"][0]

# 2. 局部替换（如只换封面：仅换 thumb_media_id；如改标题：仅改 art["title"]）
new_thumb = add_material("/path/to/new_cover.png", "image")["media_id"]

# 3. draft/add 新草稿
payload = {"articles": [{
    "title": art["title"],
    "author": art.get("author", "宇龙 AI"),
    "digest": art.get("digest", ""),
    "content": art["content"],          # ← 一字未改
    "thumb_media_id": new_thumb,        # ← 只换这个
    "need_open_comment": 1,
    "only_fans_can_comment": 0,
}]}
draft_add(payload)  # ensure_ascii=False
```

**重推决策表**：

| 改动 | 用什么 |
|---|---|
| 全文重写 | `push_article.py` 全渲染 |
| 只换封面 | `draft/get` + `add_material` + `draft/add`（复制 content）|
| 改一句 / 改标题 / 改 digest | `draft/get` + 改 HTML 局部 + `draft/add` |
| 补一张图（图已在 mmbiz） | 直接在 content HTML 里插 `<img data-src="…">` + `draft/add` |
| 补一张图（仅本地） | uploadimg 拿 mmbiz URL → 同上 |

### 🚧 默认不删旧草稿

- 推新草稿后**不主动调 `draft/delete`**。
- 只有用户**明确说"删旧的 / 去重"**才删。
- 用户多版本对比是常态，不要替用户清理。

### 🎨 封面规则（AI 生图）

- 默认从结果图里挑一张最有场景感的；不强制 AI 生图。
- 真要 AI 生图时，规格固定：**1872×800（≈2.35:1，微信首图比例）**、居中构图（要便于方形裁剪）、**无任何文字**（微信会自动叠标题，封面带字会打架）。
- 调用：`codex` / 本地 `chatgpt-image-2` skill / `gpt-image-2` API 都可以。

### ⏱ 时间数字与"凭空场景"双禁

- **精确时间数字禁**：禁止"半小时 / 15 分钟 / 7 秒 / 3 分钟 / 十秒钟 / 两小时"等带数字的时间副词，**除非用户截图/原话有依据**。AI 模型最容易在这里破防（编出"七八秒就好了""半小时搞定"这种听感很顺、但完全没依据的时间）。
- **范围/模糊词允许**：可以写"几分钟 / 十来分钟 / 一会儿 / 没等多久 / 一杯咖啡的工夫"。读者能感受节奏，不会被打脸。
- **凭空场景禁**：禁止凭空编"我跟朋友说" / "客户问我" / "同事看完" / "评论里有人说" 这种没发生过的对话和角色。
- **brief 工具名优先 SKILL 默认 AI 名**：如果 brief / 用户原素材里点名 GPT / Codex / ChatGPT，不要替换成 Hermes / 爱马仕 / 小龙虾。SKILL 的"默认提到 AI 助手叫 Hermes"是缺省值，brief 给名字时 brief 赢。

### 🛎 评论区互动行 + Hashtag + 签名防重规则

- 评论区互动行（如「你要是也灰度到了，先试一件事：让它查查你微信第一年到底花了多少钱，把数字丢评论区，我赌大部分人第一年都没超过100块😂」）**默认位置 = 正文结尾收尾处**。
- **文末 Hashtag 规则**：互动行之后可自然加入 3-5 个精炼话题标签（如 `#微信 #小微 #AI #Agent #小程序 #宇龙AI`），帮助微信平台算法抓取与话题聚合。
- **严格单签名防重机制**：
  - 签名固定为「**我是宇龙，专注 AI Agent 场景应用落地。**」。
  - `push_article.py` 在渲染前自动执行 `clean_markdown_text`，剥离正文末尾的手写签名与多余分隔线，统一由页脚样式渲染唯一定制的一处签名。
  - `validate_html` 包含强制断言：`assert html.count("我是宇龙") == 1`，出现 0 次或 2 次以上直接报错阻止推送，从底层杜绝双签名 Bug。

### 🎨 排版渲染主题体系（支持 8 大现代风格）

推送时可通过 `--theme` 自由指定排版风格：
1. `green`（默认萌绿）：白底搭配清新草绿 H2 与引用块，现代通透科技感。
2. `purple`（紫色渐变）：浅紫背景搭配深紫高光，优雅精致。
3. `blue`（萌蓝）：清爽冰蓝高亮与柔和边框。
4. `rainbow`（彩虹经典）：顶部彩虹分割线，大号 PART 标头。
5. `dark-gold`（黑金科技，NEW）：深黑夜幕底色（`#18181b`）搭配奢华琥珀金（`#f59e0b`），适合重磅商业阳谋与深度技术洞察。
6. `minimal`（极简纯粹，NEW）：纯白底色、沉稳纯黑左边框标题、冷灰卡片，克制现代。
7. `twilight`（优雅暮蓝，NEW）：暮色蓝紫渐变、靛蓝高光、精致发光阴影。
8. `sunset`（活力暖橙，NEW）：晨曦暖橙背景搭配活力珊瑚橙标题，生动活泼，适合生活化体验与开箱。

### 🤖 多模型弹药库综合评审工作流（NEW）

写稿完成后，可使用 `scripts/cross_model_arena.py`（多模型竞技场）或 `scripts/multi_model_refine.py` 调度 Claude Opus 4.8 / Fable 5 / 5 Opus / Kimi k3 / Gemini 3.7 Flash 等多模型弹药库进行并发提案与匿名交叉盲审打分：
- 爆款标题打分与去科技媒体工牌词
- 视觉识图细节抓取与无句号图注增强
- 宇龙口吻纯度审计与去 AI 腔纠偏
- 商业价值与生态阳谋深度提炼

### 📹 微信视频嵌入与素材上传标准协议（NEW）

- **严禁直接插入 `<video>` 标签**：微信草稿箱编辑器会清洗非白名单标签，导致视频丢失。
- **微信官方原生视频组件**：必须通过 `material/add_material?type=video` 上传，再调 `material/get_material` 获取实际 `vid`（如 `apiv_...`），并生成标准 iframe：
  `<iframe class="video_iframe" data-vidtype="2" data-mpvid="{vid}" src="https://v.qq.com/iframe/preview.html?vid={vid}" frameborder="0" allowfullscreen="" style="width: 100%; height: 375px; border-radius: 8px;"></iframe>`
- **正文精确定位插槽**：正文 Markdown 中写入 `[VIDEO]`，渲染脚本自动将原生视频播放组件原地替换，不破坏行文逻辑。
- **转码与体积防御**：超过 20MB 极易报 -1 system error，上传前统一用 ffmpeg 压制为 720p/H.264 (~2Mbps) 规格。
- **缓存复用与重试**：已上传视频自动记录在 `/tmp/wx_video_cache.json`，遇到网络抖动自动退避重试 3 次。
- 详见：`references/wechat-video-embedding-guide.md`

### 📄 飞书长文档全量导出与图片无损落盘规范（NEW）

- **严禁直接通过 DOM querySelector 粗暴抓取**：飞书带有虚拟滚动，普通 DOM 抓取会丢失 80% 之后的长内容与核心截图。
- **必须使用 `feishu-doc-export/extract.js`**：遍历 `PageMain.blockManager.rootBlockModel` 提取完整 AST 与公开临时图链（asynccode）。
- **图片二进制防损坏自检**：严禁用字符串 buffer 处理二进制图片（会产生 `ef bf bd` 乱码破坏，导致微信报 40137 invalid image format）。必须使用 Python 原生二进制流落地，并用 `file` 命令验证格式。
- 详见：`references/feishu-export-and-media-integrity.md`

对应核心参考：
- `references/wechat-video-embedding-guide.md`（微信视频嵌入与永久素材上传完全指南，NEW）
- `references/feishu-export-and-media-integrity.md`（飞书素材全量导出与媒体完整性校验规范，NEW）
- `references/cross-model-benchmark-arena.md`（多模型交叉盲审天梯榜与黄金样本库，NEW）
- `references/yulong-voice-treasure-vault.md`（宇龙专属高频金句与语感宝库，NEW）
- `references/vision-caption-and-storytelling.md`（看图说话与图注深度指南）
- `references/viral-title-formulas-v2.md`（爆款标题与选题公式库 v2）
- `references/voice-preserving-expansion-guide.md`（原汁原味内容保留与扩充法则）
- `references/data-driven-writing-workflow.md`
- `references/personal-voice-rules.md`
- `references/prompt-result-case-pattern.md`
- `references/image-text-alignment-check.md`

如果用户已经给了截图里的真实请求方式，优先跟着用户素材走，不要硬套“客户/老板/销售”场景。

比如 Codex / AI 工具体验文里，用户截图是：

- 图片拆解
- 参考图转风格
- 文章生成学习图
- Word / PPT 整理

那正文就围绕这些可见案例写，不要改写成销售线索、客户聊天、老板决策分析。

人味儿规则：

- 不要故意塞错别字；故意错字也很假。
- 可以保留短句、口语、轻微重复和一点不那么工整的表达。
- 不要每段都总结大道理，不要每节都拔高。
- 少用：赋能、闭环、重塑、生态、范式、降本增效、生产力革命、全流程自动化、AI 员工、端到端、多模态能力、方法论。

### 🧭 Hermes/MiniMax 写作输出契约

**写公众号时，先提纯再输出。不要把排障日志、工具过程、memory 讨论、模型自我解释混进正文或最终回复。**

每次写作必须按这个顺序做：

1. **提取锁定区**：用户已确认的标题、副标题 digest、封面、必须使用/必须排除的图片、最近一次“不对/重新/应该是”的修正。
2. **提取用户原话区**：语音转写、用户草稿、用户口语句，优先保留；只做顺序调整、错字修复、段落切分。
3. **写正文区**：只输出面向读者的文章 Markdown，不写工具说明，不写“我准备/我正在/我查到”。
4. **交付区固定四块**：`正文`、`副标题（单独发给用户，不进正文）`、`图文对照表`、`待确认项`。
5. **正文第一行必须是最终选用标题**：例如 `# TRAE 的实力如何？`。不要把 `# 标题候选`、`# 正文`、`# 最终交付摘要` 放在第一行；标题候选只能放到正文后面。

MiniMax M2.7 容易把过程说得很散，所以回复用户时强制“一屏协议”：

- 中间进度最多 2 句，只说当前在做什么和下一步。
- 最终回复最多 4 块，不展开工具细节；工具结果只保留结论和路径。
- 不要在同一条回复里同时解释 memory 系统、研究背景、推送流程和正文修改；这些必须拆成不同任务块。
- 任何用户刚修正过的图文关系，必须优先进入图文对照表，而不是继续写新段落。

#### 第二道硬闸：写作测试/纯写稿时禁止冒充执行

如果用户只让“写一版/改一版/测试生成效果”，没有明确要求推草稿、上传图片、创建草稿或调用发布脚本：

- ❌ 不要写“我已读取草稿台”“14 张图都已上传到 mmbiz”“已经推送/已保存”。
- ❌ 不要在最终输出前加“Now I have...”“我现在开始写”等过程句。
- ✅ 最终回复第一行必须直接是最终选用标题，例如 `# TRAE 的实力如何？`。
- ✅ 可以写“以下是写作测试稿”，但不要声称做了任何未实际执行的动作。

#### 第三道硬闸：正文必须真正放图

“图文对照表”不是替代正文配图。只要用户给了图片，正文里必须在对应段落附近插入 Markdown 图片占位：

```md
![图注文字](images/filename.png)
```

规则：

- 本地草稿目录有 `images/` 时，用 `images/<filename>`。
- 只有文件名时，用 `<filename>`，不要编造公网 URL。
- 图片内容不确定但用户要求默认全用时，也要插入，并在图注写 `待确认：...`。
- 图文对照表里的“对应段落”必须和正文真实小节标题一致；正文用 `## 1 小标题`，表格也写这个小节名，不要凭空加英文分段标签或零开头编号。
- 交付前必须核对图片和正文是否一致：请求截图要对应请求说明，结果图要对应结果说明，小字看不清要标出。

发布或交付前必须跑机器 QC。最小流程：

```bash
python3 /root/.openclaw/skills/wxmp-article-pipeline/scripts/wxmp_article_contract_qc.py \
  --expected-images "073737-c55a.png,083126-cb79.png" \
  --output /tmp/article.md
```

如果 `score < 85`、`missing_body_images` 非空、`has_preface_or_process_lead=true`，或 `process_pattern_hits` 非空，不要交付，先修正文。

**交付版 / 推送版必须是两个文件**（2026-07-14 固化，QC 满分实测路径）：

- `article.md`（交付版，跑 QC 用）＝ 正文 + 末尾三区块：`副标题（单独发给用户，不进正文）：…`、`图文对照表：`（表格，含 note 来源列）、`待确认项：`。QC 的 `has_subtitle / has_image_mapping / has_todo` 检查的就是这三块，缺了到不了 85 分。
- `article-push.md`（推送版，喂给 push_article.py）＝ **纯正文**，绝不含上述三区块——它们进了正文就会被渲染进公众号文章。
- 首行 `# 标题` 两个文件都要有：QC 靠它判定非 preface；push_article.py 渲染时会跳过首行 H1，不会双标题。
- 图注写法：`![图注](file.png)` 的下一行再补一行斜体 `*图注。*`——QC 的 `uncaptioned_body_images` 认的是斜体行，光有 alt 不算。

#### 第四道硬闸：不要主动加外链、签名和硬广

- 只有用户提供过的链接、`HISTORICAL-ARTICLES.md` 里的真实相关文章链接，或工具真实返回的链接，才能进入正文。
- 不要凭感觉加 GitHub、官网、个人网站链接。
- 不要在文末加“我是宇龙...”这类签名，除非用户明确要求。
- 不要把 MiniMax 额度、会员、价格写成硬广；只有当用户素材本身要求说，才压成一两句体验信息。

#### 第五道硬闸：企业服务是底色，不是贴脸销售

用户现在的公众号目标不只是“分享 AI 工具”，后续也会承接企业 AI 服务。但写作时不能把正文写成咨询提案或硬广。

默认读者里可以有企业老板、运营/销售负责人、AI 转型负责人；他们不一定懂 Agent / VPS / CLI，但能理解“少折腾、省时间、交付更稳定”。

写法：

- 先讲真实场景，再讲工具；先写“我在干嘛、我让 AI 做什么、它哪里好/哪里不行”。
- 企业服务只影响选材和解释角度，不要在正文里突然写“我可以承接企业 AI 咨询/企业真正需要/AI 员工落地”。
- 每篇只推进一点点：这篇可以从“做游戏”轻轻过渡到“以后 PPT、客户演示、活动页、内部小工具、培训材料也可能类似”，不要列一长串企业应用清单。
- 当前阶段只写“我自己怎么试、哪里不稳、下一步怎么改”，不要提前写成业务承接宣言。
- 真有企业合作案例之后，才升级到“案例复盘/客户问题/交付效果”的写法。
- 不要写空词：赋能、闭环、范式、生态、重塑生产力。

写作前先判断本篇所处阶段：

| 阶段 | 适合怎么写 | 禁止怎么写 |
|---|---|---|
| 自测/工具体验 | 写真实场景、踩坑、结果；结尾轻轻点“以后可迁移” | 写成企业服务广告 |
| 流程稳定/可复用 | 写“我怎么把流程沉淀下来” | 夸大成成熟产品 |
| 真实企业合作 | 写客户问题、方案、交付、反馈 | 暴露客户隐私或编造结果 |

#### 第六道硬闸：一键模式允许自选标题，但必须自检

如果用户明确说“能不能一次完成/直接推草稿/一键成稿”，可以不反问，自己完成：

1. 从草稿生成标题候选，按“场景 + 反差 + 企业价值”自选一个。
2. 自选封面候选，优先选最终结果图或最有场景感的图。
3. 写稿并插入所有图片。
4. 跑 `wxmp_article_contract_qc.py`。
5. QC 通过后再转飞书 Docx 或推微信草稿。

如果 QC 不过，不要推草稿，先返回失败项和 Feishu 审阅稿。

如果事实卡或用户最新反馈给了标题方向，优先用用户方向，不要为了标题党改成更大的说法。TRAE/星巴克这类稿件优先 `TRAE 的实力如何？`，不要写成“AI 帮我干了一个工作室的活儿”，因为这会把“测试 TRAE + 调 Codex”夸大成 TRAE 自己完成全部。

#### 第七道硬闸：图片没 note 时自动补图注

**贴图 `newspic` 跳过本闸**，不配图注。

长文没给图片文字时，不要停住，也不要瞎删图：

- 先用 vision/图片查看能力识别图片内容。
- 自动生成一句“小字居中图注”。
- 图文对照表里标记 `note 来源=自动图注`。
- 待确认项列出这些图片，让用户发布前扫一眼。

更完整的写作提纯规则见 `references/hermes-minimax-output-contract.md`。

#### 🙅 克制「拟人化吹捧 AI 智商」（2026-06-03 用户反馈）

写 AI 体验文最容易踩的坑：**通篇夸 AI「聪明 / 脑回路厉害 / 想得真周到 / 真有条理 / 我服了 / 被它圈粉」，每一节都强行升华成「我被点醒 / 太值得学了」。**

用户原话目的：这种写法 ① 肉麻、像在舔 AI，丢了作者自己的判断；② 通篇重复同一种「AI 真棒」的情绪 = **信息增量低，直接踩微信「低创作度 / 同质化堆砌」红线**；③ 真正的洞察反被密集抒情淹没。

规则：

- **一篇里「我被点醒 / 值得学 / 更有收获 / 真聪明 / 被圈粉」这类主观升华，最多点 1～2 次**（通常只在结尾点一次题）。其余各节只写**事实**：它做了什么、怎么判断的、给的理由是什么。
- 砍掉空洞抒情，**用「信息增量」撑字数**（原理、步骤、它的具体判断依据、相关科普），不要用「我真服了」凑字数。
- 保留作者真实的**口语吐槽**（如「你别说」「好嘛😅」「你厉害你仁义」「方便极了」）——这是个人味，不是吹捧；要砍的是文绉绉的「挺有条理」「值得学习」「令我感慨」这类。
- 标题同理：别用「被它的脑回路圈了粉」这种舔机器的；用「本想让 AI 干下活，结果给我上了一课」这种**有反差、主语是「我」**的。
- 自检：通读全文，把每段结尾那句「……所以我学到 / 真值得 / 更有收获」标出来，超过 2 处就删到只剩点题那一处。

#### 🚧 防限流：导流 / 二维码 / 关注引导要藏暗（2026-06-03，微信新规）

微信明确把这些列入限流：**内容导流、互动导流、诱导关注送奖励、二维码 + 文字强引导**。历史上「惊了！GPT…」那篇就因导流被点名。规则：

- **正文里不要直接插微信二维码图**，不要写「关注后私信『工具』送你 XX 合集」这种「关注+奖励+暗号」三件套（这是诱导关注送奖励，明确违规）。
- 引导要**藏暗**：结尾一句自然的话即可，如「想聊的评论区见」「这套流程我整理了，感兴趣的可以留言」，**不放二维码、不承诺送东西、不留外部联系方式**。
- 商业合作、加微信这类，**别写进正文**；放公众号「菜单 / 自动回复 / 简介」里，那是平台允许的固定位置。
- 评论区互动引导（「评论区聊聊」）是安全的，鼓励用。
- 一句话：**正文只负责把内容讲透（信息增量），引导交给菜单和评论区**，别在正文里又导流又送奖励。

#### 第八道硬闸：AI 味 / GPT 味必须单独过闸

旧 QC 只看“图在不在、有没有假执行”，不够。现在写完还要看 `ai_flavor_hits` 和 `hard_sales_hits`：

```bash
python3 /root/.openclaw/skills/wxmp-article-pipeline/scripts/wxmp_article_contract_qc.py \
  --expected-images "a.png,b.jpg" \
  --output /tmp/article.md
```

如果出现这些命中，不要交付，直接改：

- “真正能打开的结果” -> “我能点开玩”
- “可访问的结果” -> “能点开的东西”
- “把任务往后推” -> “一路做到我能点开”
- “一点点往前磨” -> “一点点改顺”
- “讲得太大” -> “吹过头”
- “单点能力” -> “只回我一段话”
- “工具接力” -> “几个工具轮流干活”
- “这条链路稳定 / 底气就不一样” -> “真跑顺了，再拿去帮别人做，就不是空讲了”
- “我们正在进入一个阶段 / 未来的样子” -> 换成具体感受，不升维
- “比...更重要的是” -> 换成“我在意的是...”
- “这就是现在的效率” -> 删掉，不要替读者下口号式结论
- “电子世界里可以呼风唤雨” -> 删掉，换成具体这次做到了哪一步
- “框架是存在的 / 同样的思路” -> 换成“也许能用类似方法做”，不要像方案总结

同时检查 `unsupported_claim_hits` 和 `part_token_hits`：

- 不要补用户没说过的场景、时间、人群行为和模型能力。
- 没有素材支撑时，不写“半小时、15分钟、十来分钟、翘班、薅羊毛、图纸、怪物听成乖物、游戏公司工作室门口、GPT-image2 做音效”。
- 正文和图文对照表都不要再使用英文分段标签，统一用 `## 1 小标题` 这种自然小节。
- 图片顺序默认照素材清单，不要为了制造反差把开头现实场景图后置。
- `uncaptioned_body_images` 必须为空，`has_image_mapping=true`，`has_todo=true`；否则不是合格交付。
- `meta_first_heading_hits`、`title_overclaim_hits`、`weak_summary_hits` 必须为空；否则说明标题/第一屏/结尾仍有 AI 味。

原则：少写漂亮总结，多写用户现场感；少写抽象名词，多写“我怎么做、它哪里不行、后来怎么改”。

### 🚫 不要 git commit 内容变更

**推草稿 / 改文章内容 / 改 review JSON / 改 draft meta / 换主题 都是数据操作，不是改项目，禁止 commit。**

- ❌ `drafts/*/meta.json` 改 content → 不 commit
- ❌ `review/*.json` 新增 / 修改 → 不 commit
- ❌ `drafts/*/images/` 上传图片 → 不 commit
- ✅ **唯一可以 commit 的情况**：你真的改了 `wxmp-studio/app.py`、`static/index.html`、`scripts/*.py` 这类**代码文件**，并且改动是**对所有文章通用**的改进（例如：加渲染器新特性、修 UI bug、新加 CLI 子命令）

**为什么**：FastAPI 每次请求才读 `review/*.json` 和 `drafts/*/meta.json`，它们是"数据库行"。commit 内容会污染 git log，让后续回顾找不到真正的代码改动。过去 Hermes 给一篇 SBTI 做了 6 次 "终版" commit，就是这个反模式的典型。

### 🚫 不要手写 inline HTML / 硬编码样式

**所有样式都从主题 JSON 里来，单篇文章不允许手写 `<section style="...">...</section>` 塞进 review JSON 的 `html` 字段。**

- ✅ 主题从 **`/api/themes`** 接口查（不是 `ls *.json`，不是凭记忆）— 返回的就是合法 `name` 列表
- ✅ `add-draft` / `add-published` 自动走 `_render_markdown_with_mdnice_theme`（服务器端实时渲染），你只管传 `--theme 紫色渐变` 这种名字
- ❌ 不要给 review JSON 的 `html` 字段手搓 HTML 字符串 — 那是 legacy 路径，只有最老的 SBTI 还在用
- ❌ 不要发明新的 `theme_source`（只允许 `mdnice` 或 `jahseh`）
- ❌ 如果你觉得现有主题都不合适：**停下来问用户要不要加新主题**，不要自己写 inline html 绕开

**想加新主题？**：在 `/root/.openclaw/workspace-restore/docs/wxmp-themes/mdnice/{name}.json` 放一个 JSON 文件（参考 `紫色渐变.json` 的 schema），**不需要配套 .html**，立刻在 `/api/themes` 可见、任何文章都能用 `--theme {name}` 切。加新主题也**不需要 commit**（主题文件不属于 wxmp-studio 仓库，属于 workspace-restore）。

### 🚨 6 条防翻车铁律（来自 5 次真实会话提炼，2026-04-25）

写文章时这 6 条违反任意一条 = 直接翻车，全部固化为硬约束：

#### ① 写完文章后，必须在回复里贴"图文对照表"
不是默默检查，是**实际打印出来给用户看一眼**：

```
图1 (062555-ae86.jpeg) → §1 段落 → 图注："库克在抖音直播间卖小米SU7"
图2 (063012-bc91.jpeg) → §2 段落 → 图注："余承东直播间卖苹果全家桶"
...
```

**为什么硬要求**：4/22 库克稿"美女主播配错段、苹果CEO混在中间"、4/18 Claude Design"ABC 三版风格 C 配错图"、4/13"Claude Code 配置龙虾的图被误读"——这是反复翻车的 #1 错误。模型自己默想"应该没问题"是不够的，必须打印对照表强制 self-check。

#### ② 图片默认全用，要排除哪张必须用户明说
**反向白名单**：用户给的图全部用上，除非用户**明确点名**"这张不用"。

- ❌ 不要自己判断"这张图意义不大、删掉"
- ❌ 不要自己判断"13 张太多、精简到 8 张"
- ✅ 全部插入对应段落，无关的也插上并在图注里标注让用户决定

**为什么**：4/18 Yulong 反复说"除了授权github那张，其他都用！""授权图你怎么又传进去了！？？？""总共只有13张图吗？不对吧？"——模型默认"少而稳"和 Yulong 的偏好"全用"完全相反。

#### ③ 从 inbox 草稿重写（不是从零新写）

**场景**：用户提供 inbox 草稿 URL 或草稿目录，里面已有文字和图片素材。

**流程差异**：
- Step 1（冻结样本）：跳过（没有"刚发布"的新文章）
- Step 2（读历史风格）：**必须做**，读最近2~3篇爆文参考风格
- Step 3（列大纲确认）：**可简化**——用户给了草稿说明方向已定，大纲确认可以简短，聚焦"标题+图片选择"两点
- Step 4（写全文）：**用用户草稿原话**，顺序调整+段落切分+图注，不做书面化重写

**图片使用规则（反向白名单）**：
- 用户提供的图片**默认全用**，不用需要用户明确说"这张不用"
- 图片顺序不是随便排的——**按故事情节线排序**：开头场景→工具介绍→过程→结果→结尾场景
- 开头用场景/氛围图（如咖啡厅照片），不用技术截图
- 结尾用收尾氛围图，不用过程图
- 例：星巴克排队场景图 → Codex IDE截图 → 手机跑游戏截图 → 通关截图 → 咖啡厅收尾图

**相关文章链接（末位加跳转）**：
- 结尾加「相关文章」块，格式：
```html
<p style="text-align:center;margin-top:24px;"><a href="https://mp.weixin.qq.com/s/真实文章ID" style="color:#7c3aed;">相关文章：<strong>上一篇文章标题</strong> →</a></p>
```
- 链接用真实文章 ID（从 HISTORICAL-ARTICLES.md 查），不要留占位符

#### ④ 用户确认过的标题/封面 → 锁定，禁止"再优化"
一旦用户说"这个标题不错"或"用这张封面"，**这条信息进入只读区**。后续任何重写、调整、迭代都不能动它，除非用户主动说"换"。

- 4/13 Yulong：「刚才的标题不是不错嘛，怎么又改了？」
- 4/18 Yulong：「封面图为什么不是用的新网站截图而是旧网站截图？」

**实操**：标题和封面 media_id 确认后立刻在回复里 echo 一遍"已锁定：标题=XXX，封面=img_NN"，作为后续步骤的硬约束。

#### ④ 副标题（digest）必须单独发一条消息，不写进正文
- 文章 `meta.json` 的 `content` 字段：**不含**副标题
- 推送时 `digest` 字段填副标题
- 用户看到回复："副标题：xxxxxxxxx（≤120字，自己粘贴到公众号后台）"——**单独一条消息**

**为什么**：4/13 Yulong 明示"副标题不需要出现在正文，直接发我文字就行（单独发条消息），我自己粘贴。（更新到skill）"——已经在 QC 清单第 7 条但 m2.7 仍反复出错，所以提级到铁律。

#### ⑤ 写作时优先用 Yulong 的原话（语音/口语 > 模型改写）
Yulong 给的素材里，**语音转写、口语句、自己写的草稿原文** = 第一优先级。模型只做：
- 顺序调整（结尾前置等）
- 错字修复（**仅限明显的语音转写错误**，如"重一些的人物"→"任务"、残留的"1."）
- 段落切分

**禁止**：把"我决定换掉龙虾"改成"决定迁移到新平台"这种**书面化重写**。

**用户自创口语词/独特说法不许纠**（2026-07-14 实翻车）：把「一管周额度」"纠正"成「一整个周额度」被用户点名——"一管，就是一管子的意思，不需要非得那么严谨"。判断标准：读得通、有画面的口语表达（一管/嚯个茶/手拿把掐/罚站）一律保留原样；只有确定是转写机器听错的才修，拿不准就保留。

- 4/13：「记得用我语音打字的那些内容啊，我刚才强调也说了的哈！」
- 4/18：「'适合想让访客一眼记住那个拍风光的人这个目标'这是说的啥？不太人话啊！！」「人话这种举一反三啊」

#### ⑥ 上下文 compaction / interrupt 后，第一件事是补读最近的用户修正
看到 `[CONTEXT COMPACTION]` 或 `[System note: previous turn was interrupted]` 时，**不要直接接着干**。先：

1. 读最近 5 条 user 消息（不是 assistant 自己的总结）
2. 找到所有"不对"、"重新"、"改"、"应该是"的修正点
3. 在回复里复述："我了解到你已经确认了 X、修正了 Y、还在等 Z"
4. **得到用户"对，继续"再往前**

**为什么**：4/22 改稿 3 次 interrupt、4/23 多次 interrupt 后模型每次都"忘了之前的约定"重新犯错。opus 4.7 不太会触发 compaction，但写上更安全。

---

### 🧊 用户触发词 → freeze-latest 流程

当用户说以下任何一句，立即跑 `python3 /root/.openclaw/workspace/projects/wxmp-studio/scripts/review_helper.py freeze-latest`：

- "抓一下刚发的"
- "拽一下刚发的那篇"
- "freeze latest"
- "冻结最新发布"
- "把刚发布的存档一下"

这条命令一步到位：
1. 调 `archive_articles.py --latest --json` 从公众号后台拉最新一篇的 HTML + MD 到 `references/archives/published/`
2. 自动把归档路径作为 `source_type: published_archive` 加入 wxmp-studio review tab
3. 返回 review id 和归档路径

**幂等**：已归档过的文章重跑会 skip 下载但仍会刷新 review entry，不会出错。

**失败场景**：wxdown cookie 过期（这时会报错，你看 stderr 里的 "unauthorized" 就是 cookie 要刷新了）。

这一步不是 `wxmp-sync`。如果用户问阅读量、赞、推荐/喜欢、分享、评论，转到 `wxmp-sync`。

---

## 类型判断（先决定 news 还是 newspic）

| 类型 | 场景 | API | 排版 |
|------|------|-----|------|
| **文章 `news`** | 长内容、有多个段落和图片 | `draft/add` | 紫色主题 HTML |
| **贴图 `newspic`** | 短内容、朋友圈/小绿书风格 | `draft/add`（贴图模式） | 纯文本 + 图片，无 HTML |

**⚠️ 关键规则：用户说"贴图"时必须用 newspic 类型！**

用户明确说"贴图"、"小绿书"、"图片帖"时，**必须**设置：
```python
"article_type": "newspic"  # 必须加这个字段
```

不加这个字段 = 文章类型，不是贴图！

贴图任务的写作输出也要先锁死：

- 标题 ≤ 20 个中文字符，且**一遍读懂**：谁 + 干什么 + 结果。短到读者问「啥意思」就重写。细则见 `references/title-formulas.md`。
- 正文是短句，不要英文分段标签式长文结构。宜 **250-400 字**，图上有几块就落到几句，别只甩一个钩子。
- 不写副标题 digest。
- **不配图注。** 贴图就是图 + 短句，不要在图下再跟一行小字。第七道硬闸的自动图注对贴图无效。
- 不走紫色主题 HTML 长文渲染。
- 最终交付为：贴图标题、贴图正文、图片顺序表、待确认项。
- 贴图 QC 必须使用 `--article-type newspic`，且 `newspic_forbidden_hits` 为空。

**贴图限制**：
- `newspic` 的 `image_info` 必填，不支持零图片贴图
- 纯文字贴图只能走公众号 App 前端的"文字海报"入口
- 贴图标题 ≤ 20 个中文字符
- 内容只支持纯文本，不支持 HTML

**⚠️ 标题和正文不能重复！**
- 正文第一句**不能**和标题一样
- 标题是标题，正文是正文，各司其职
- 例：标题"GPT-image-2 也太能打了！"，正文开头应直接说"这是我两句话就和AI对话出来生成出来的，你敢信？"

---

## 发布后数据同步（调用 wxmp-sync）

`wxmp-article-pipeline` 负责发布前流程：写作、图片、渲染、校验、推送草稿箱。发布后的阅读量、点赞、分享、评论、归档备份、趋势分析交给独立的 `wxmp-sync` skill，不要把同步逻辑复制进本 skill。

触发场景：
- 用户说“同步一下公众号数据”“查阅读/点赞/分享/评论”“做内容复盘/趋势分析/归档”
- 文章已经发布，需要把后台发布记录和指标落库
- 需要检查公众号 API 或 mp.weixin 后台登录态是否还有效

常用命令：

```bash
/usr/local/bin/wxmp-sync sync-all
/usr/local/bin/wxmp-sync doctor
/usr/local/bin/wxmp-sync auth-status
```

指标查询优先读取 `/root/.wxmp-sync/wxmp.sqlite` 的 `mp_publish_articles` 表，或使用 `/root/.wxmp-sync/mp_publish_metrics.csv`。如果 `auth-status` 失败，不要在 Hermes 里绕登录态；从 Mac/Win 浏览器宿主刷新后再同步。

## 📣 拉评论正文（2026-07-26 打通，此前一直以为拉不到）

**结论：能拉，而且是后台正规接口。**之前失败是因为**路径猜错了**——评论接口在 `/misc/appmsgcomment`，不在 `/cgi-bin/` 下面。

```bash
python3 /root/.openclaw/skills/wxmp-article-pipeline/scripts/pull_comments.py --appmsgid 2247485899
python3 .../pull_comments.py --comment-id 4440681168547561475        # 已知 comment_id 时更快
python3 .../pull_comments.py --appmsgid 2247485899 --json out.json   # 落盘
python3 .../pull_comments.py --appmsgid 2247485899 --type 4          # 被屏蔽的评论
```

### 接口真相（找了很久，记下来别再走弯路）

| 用途 | 接口 |
|---|---|
| 文章列表 → 拿 `comment_id` | `GET /misc/appmsgcomment?action=list_latest_comment&begin=0&count=20&sort_type=0&sendtype=MASSSEND` |
| 某文章的评论 | `GET /misc/appmsgcomment?action=list_comment&comment_id=<64位id>&begin=0&count=20&filtertype=0&day=0&type=0&max_id=0` |

公共参数：`token`、`lang=zh_CN`、`f=json`、`ajax=1`。请求头必须带：`Cookie`、浏览器 `User-Agent`、`X-Requested-With: XMLHttpRequest`、`Referer: https://mp.weixin.qq.com/misc/appmsgcomment?action=list_latest_comment&...&token=<token>`。

### 五个坑（每个都真踩过）

1. **路径**是 `/misc/appmsgcomment`，**不是** `/cgi-bin/appmsgcomment`。猜错路径时微信返回**空 body（0 字节）**、不报错，极难 debug。
2. **`comment_id` ≠ `appmsgid`**。`comment_id` 是一篇文章的 64 位评论区 id（如 `4440681168547561475`），必须先用 `list_latest_comment` 查出来（脚本已自动做）。
3. 参数是 **`filtertype`**（没有下划线），写成 `filter_type` 拿不到。
4. **响应里套响应**：`comment_list` 和 `app_msg_list` 是**嵌在 JSON 里的 JSON 字符串**，要 double-parse。
5. **登录态**用的是 wechat-article-exporter 存的那份（`/root/.openclaw/data/wxdown/kv/cookie/` 取最新 mtime）。它和 `wxmp-sync` 自己的 `mp-session.json` 原本是**两份独立凭证**（扫一次码只救活一份），现已用下面的桥接脚本打通。

### 🔗 登录态桥接（2026-07-26 打通，扫一次码两边都活）

```bash
python3 /root/.openclaw/skills/wxmp-article-pipeline/scripts/sync_mp_session.py          # 同步
python3 /root/.openclaw/skills/wxmp-article-pipeline/scripts/sync_mp_session.py --check  # 只看两份状态
```

- 做的事：取 exporter 最新那份 → **GET 一次 appmsgpublish 验真的活着** → 转成 mp-sync 的 `{token, cookie, cookie_names}` 格式写入（原文件自动备份 `.bak-<时间戳>`）。
- **保守设计**：exporter 那份若也是死的，**不覆盖**现有文件（避免把好凭证冲掉），退出码 2。
- **已挂 cron 自动续接**：`35 1 * * *`（在 1:40 的 `mp-sync` 前 5 分钟跑），日志 `/root/.wxmp-sync/session-bridge.log`。
- 所以日常流程：**只需去 `wxdown.meltemi.vip` 扫一次码**，读数/评论/夜间同步全部自动恢复；两边都过期时才需再扫。
- 排查口诀：`--check` 一把看清谁死谁活；`wxmp-sync` 报 `200003` 先跑桥接再重试同步。

### 每条评论能拿到的字段

`nick_name`、`content`、`like_num`、`post_time`、`is_elected`（是否精选）、`shield_status`、`ip_wording`（IP 属地）、`reply.reply_list`（作者回复）。
另外 `total_count` 含被屏蔽的，`total_shield_count` 是屏蔽数，可见数 = 两者相减。

### 为什么值得常拉（选题金矿）

2026-07-26 实拉「拉群」那篇 22 条评论，直接长出三个诉求：**求教程**（最高赞之一"有什么教程吗，指导一下"）、**怕烧钱**（3 条问 token 成本）、**担心违规**（2 条提 telegram 合规）。这批诉求和阅读数据完全吻合（工具教程 258 读还在涨 vs 观点文 11 读），**写选题前先拉一遍评论，比拍脑袋准**。

⚠️ 纪律：脚本**只读**（只发 GET），绝不用它发表/删除/回复评论。

## 流程总览

### 文章流程（news）
```
输入（素材/图片）
  ↓
Step 0（必读）：
  │  ★ 先冻结上一篇已发布的文章为 golden 样本（on-demand 归档）：
  │     python3 /root/.openclaw/workspace/projects/wxmp-studio/scripts/review_helper.py freeze-latest
  │     → 自动调 archive_articles.py --latest --json 拉最新一篇
  │     → 自动加入 wxmp-studio review tab 作为 published_archive
  │     → 没有新文章要归档时会报错退出, 忽略继续即可
  │  读写作风格指南：references/writing-style.md（总则 + 文件索引）
  │  读术语表：references/GLOSSARY.md
  │  读最近3篇历史文章：references/HISTORICAL-ARTICLES.md
  ↓
Step 1：逐张看图，确认内容与段落对应关系
  ↓
Step 2：存档图片识别结果为 MD（如 ClawBot 已有识别结果，保存到 archives/）
  ↓
Step 3：列大纲给用户确认（标题 + 小节结构 + 图片选择）
  ↓
Step 4：用户确认后写全文
  │  → 开篇查 references/opening-patterns.md 对照开头模式
  │  → 标题套 references/title-formulas.md 公式
  │  → 金句/结尾查 references/callout-patterns.md
  │  → 图注查 references/image-caption-rules.md
  │  → 写完自检 references/banlist-words.md
  │  → 大纲/小节结构查 references/structure-patterns.md
  ↓
Step 5：上传图片到微信
  │  正文图片 → uploadimg → mmbiz.qpic.cn URL
  │  封面图   → add_material → thumb_media_id
  │  封面来源：默认从正文结果图里挑一张最有场景感的；
  │           用户要求或没有合适结果图时，才用 AI 生图（如 codex cli 调 gpt-image-2）单独出一张。
  │           不要默认每篇都生成封面，一般是「选」，不是「生」。
  ↓
Step 6：渲染紫色主题 HTML（含小节标题、blockquote 金句、图注）
  ⚠️ **禁止跳过**：永远调用 `render_markdown_to_purple_html(md_text, image_map)`，不要裸推 HTML、不要手写 inline HTML、不要直接调 `push_draft()` 而绕过渲染。
  ↓
Step 7：逐项 QC 清单（见"推送前 QC 清单"章节，全部 □ 通过再推）
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

> ⚠️ **6 篇里有 4 篇是贴图**，比例 67%。这是**主流路径**，不是边角料。

```
输入（短文本 + 1~N 张图片）
  ↓
Step 1：判断要不要 hashtag
  │  ★ 引流话题贴 → 末尾加 #Hermes #AI #具体话题（参考 4/15 抖音视频帖）
  │  ★ 纯感想/产品发布 → 不加（参考 4/24 DeepSeekV4、4/16 Opus 4.7）
  ↓
Step 2：写正文
  │  → 1-3 行场景钩子（"今天刷到X"、"DeepSeek大家都期待了好久了"）
  │  → 几句关键说明（用了什么、效果如何）
  │  → 一句感受 / 反问（"真方便啊～"）
  │  → 互动结尾可选：「评论区聊聊，你最想让 AI 学什么技能？」
  ↓
Step 3：上传图片到微信素材库（add_material）
  ↓
Step 4：组装 newspic payload（关键：必须加 article_type: "newspic"）
  ↓
Step 5：推送草稿箱
  ↓
输出：草稿 media_id
```

#### 贴图 API payload 关键字段（2026-04-30 实测）

**必须加 `article_type: "newspic"`，否则会被当成文章（news）而不是贴图！**

```python
payload = {
    "articles": [{
        "title": title,           # ≤ 20 字
        "content": content,       # 纯文本，不含 HTML
        "thumb_media_id": image_media_ids[0],  # 第一张图作为封面
        "need_open_comment": 1,
        "only_fans_can_comment": 0,
        "article_type": "newspic",  # ← 关键！不加这个会变成文章
        "image_info": {
            "image_list": [{"image_media_id": mid} for mid in image_media_ids]
        },
    }]
}
```

#### 贴图写作要点（基于 6 篇真实贴图提炼）

| 要点 | 怎么做 | 反例 |
|---|---|---|
| 标题 | ≤ 20 中文字，一遍读懂，有反差 | "让AI学我说话，回微信才8个字" ✅ / "AI写得太长，我自己才8个字" ❌ |
| 开头 | 1-3 行画面钩子，不重复标题 | "DeepSeek大家都期待了好久了" ✅ |
| 长度 | 250-400 字 | 只甩三句钩子、图对不上 ❌ |
| 图注 | **不配** | 图下再跟一行小字 ❌ |
| 签名 | **禁止加**"我是宇龙..." | newspic 不需要 |
| AI 助手 | 直接叫 Hermes / 爱马仕 | 别叫 OpenClaw |
| 紫色主题 | **不渲染** | newspic 是纯文本，加 inline style 会被 API 拒 |
| hashtag | 引流话题贴可加 | `#Hermes #AI #进化 #skill #宇龙`（参考 4/15 抖音视频帖） |

#### 何时加 hashtag（4/15 那篇是新模式）

加：
- 想引流到具体话题（#抖音、#skill、#Hermes）
- 内容是"我学会了某个新技能"类
- 想被关注同主题的人发现

不加：
- 模型/产品发布快讯（DeepSeekV4、Opus 4.7）
- 个人感想/吐槽
- 太正式的内容

---

## 🌩 图片走云端，别跟本地链路死磕（tailscale/scp 不稳时尤其有用）

图片一旦上传到微信，就有 `mmbiz.qpic.cn` 公网链接，本机/任何地方都能直接 `curl` 读到（HTTP 200、完整）。所以：

- **看图写图注**：图已在某篇草稿/已发布文里（有 mmbiz 链接）→ 直接 `curl` 云端读，别走 tailscale/scp。只有「用户刚上传、还没推过」的本地图才必须从源头拿。
- **重推/换封面**：markdown 里图片已经是 `https://mmbiz.qpic.cn/...` → 应该直接透传，不重新上传。
- **本地稿件自包含**：一篇推送成功后，把本地 `article.md` 的图片引用换成 push-report 里的 mmbiz 链接，以后重推这篇就不依赖 VPS 本地图。
- ⚠️ 现状：`push_article.py` 还没做「mmbiz 链接透传」，仍会把 `--images` 全部重传。要彻底省掉重传，需给它加一个 pass-through：markdown 图是 mmbiz 域名就跳过上传、直接用。改完记得在 VPS 上测。
- 复用的 mmbiz 链接必须是**本号自己**传过的；别号的 mmbiz 图在本号文章里可能不显示。

## 历史文章下载（维护已发布存档）

### 存档结构（每篇文章一个文件夹）
```
archives/published/YYYY-MM-DD-标题slug/
  published.html   ← 微信发布版原文（真实渲染HTML，含样式+图片）
  content.md      ← 净化版Markdown（原写作稿，对比用）
```

### 查看文章列表
```bash
cd /root/.openclaw/skills/wxmp-wxdown && python3 scripts/wxdown-manage.py articles findyi --size 10
```

### 下载已发布文章（html + md 双版本）
```bash
cd /root/.openclaw/skills/wxmp-article-pipeline
python3 scripts/archive_articles.py                  # 拉全部（跳过已存档）
python3 scripts/archive_articles.py --since 2026-03-01  # 只拉指定日期之后的
python3 scripts/archive_articles.py --force           # 强制覆盖
python3 scripts/archive_articles.py --dry-run          # 只看计划不下载
python3 scripts/archive_articles.py --latest          # 只拉最新一篇
```

### 存档命名规范
```
YYYY-MM-DD-slug/              ← 文章文件夹（date + 标题前12字）
  published.html              ← 发布版原文（微信真实HTML）
  content.md                  ← 原写作稿（对比用）
```

### 更新索引
下载后自动更新 `references/HISTORICAL-ARTICLES.md`，在已发布文章表格添加一行。

### 首次初始化（把所有历史文章全部拉回来）
```bash
cd /root/.openclaw/skills/wxmp-article-pipeline
python3 scripts/archive_articles.py --force
```

---

## 图片处理规则（最容易出错）

### 必须逐张看图确认

**绝对不能凭文件名猜图片内容。**

每张图都要用视觉工具实际查看，确认：
1. 图片实际内容是什么
2. 对应文章哪个段落
3. 图注应该怎么写

#### 强制工具：image-recognize（Gemini 3 Flash）

写文前**第一步**就跑批量识别，不要边写边猜：

```bash
node /root/.openclaw/skills/image-recognize/scripts/recognize_images_with_gemini.mjs <图片目录或文件>
```

会落盘三种结果（每张图一份）：
- `<name>.gemini.ocr.txt` — 纯文字 OCR
- `<name>.recognize.md` — 文字 + 图片说明 + 关键信息（人话总结）
- `<name>.recognize.json` — 结构化数据

把每张图的 `.recognize.md` 内联到工作上下文后再开始写正文，按"图说什么 → 段落讲什么"匹配。

**为什么用 Gemini 而不是其他模型？**（实测 2026-04-25，三家盲测）

| 维度 | Gemini 3 Flash | MiniMax | Claude Sonnet 4.6 |
|---|---|---|---|
| OCR 准确度 | ✅ | ✅ | ✅ |
| 字段-内容对应（防张冠李戴） | ✅ | 偶尔模糊 | ✅✅ 最强 |
| 单图速度 | ~10s | ~20s | ~6s |
| 现成批量脚本 + 三种落盘 | ✅ | ❌ | ❌ |
| 综合 | **默认主力** | 备选 | 高难度兜底 |

公众号配图场景默认 Gemini，足够用。如果某张图三家结果对不上、疑似关键事实有歧义（产品名/版本号/数字），再用 Claude Sonnet 4.6 走 ccvps 二次校验（参考 claude-api-proxy skill）。

**图注禁止出现文件名**：写图注时要像跟朋友描述这张图在展示什么，禁止出现 `img_xx.jpg` 这类文件名。

**图片排除规则**：用户说哪张不用才排除，不要自己推断。遇到无关内容（如截图里有完全不相关的小贴士），在图注里说明，让用户决定。

### 上传接口区分

| 用途 | 接口 | 返回 | 作用 |
|------|------|------|------|
| 正文图片 | `POST /cgi-bin/media/uploadimg` | `url`（mmbiz.qpic.cn） | 嵌入 HTML `<img src>` |
| 封面图 | `POST /cgi-bin/material/add_material?type=image` | `media_id` + `url` | draft/add 的 `thumb_media_id` |

**只有 `mmbiz.qpic.cn` 域名的图片才能在公众号正常显示。**

### 封面图选择

- 封面图必须单独上传 `add_material`，获得 `media_id`
- 封面一般选第一张有代表性的图，或专门设计的封面图
- 上传后记录 `media_id`，推送时传给 `thumb_media_id` 字段

---

## 写作决策启发式

> 当 AI 不知道某个场景怎么处理时，直接查这张表，不要凭训练数据发挥。

| 场景 | 规则 |
|------|------|
| 开头不知道怎么写 | 用画面开头（"X给我发了Y"），再引反差；查 `references/opening-patterns.md` |
| 标题太平淡 | 加数字/反差词/问号；查 `references/title-formulas.md` |
| 不知道结论怎么写 | 先给结论，再给数据/经历支撑 |
| 段落太长 | 拆短句，单句≤25字 |
| 主观评论混在正文里 | 抽出成 Blockquote，不要加粗 |
| 不知道怎么过渡 | 用"向前桥接"：预告下一段内容 |
| 图注不知道写什么 | 写图片里"发生了什么"，不写"这是X截图" |
| 配图和文字不对应 | 停下来重新匹配，再继续写 |
| 语气太正式 | 改成"我/你"，删掉"的""了" |
| 不知道怎么结尾 | 亮点总结 + Hermes（爱马仕）点名 + 表情 |
| 不知道怎么软化负面评价 | 只说行为（"被推脱了"），不说感受（"态度差"） |
| 有政治/争议性内容 | 删，只保留行为描述 |
| 不确定某个词对不对 | 不肯定的不写，不确定事实的删掉 |
| 互动引导不知道写什么 | 拆行 + 加"AI"等通俗词 |
| 不知道该不该提某产品 | 提真实存在的，假的/不确定的删掉 |
| 表格不知道放什么 | 必须有"结论/判断"列，不只是描述 |

---

## 主题与渲染（极简速查）

> ⚠️ 你不需要写任何 inline HTML。渲染交给脚本。下面只列**必须知道**的边界条件。

### 主题怎么选（⚠️ 两套主题系统，名字互不通用）

| 流程 | 主题参数 | 合法值 | 权威源 |
|---|---|---|---|
| `push_article.py --theme`（推公众号草稿，脚本内硬编码渲染器） | 英文名 | `rainbow` / `purple` / `blue` / `green` | 脚本 argparse choices |
| wxmp-studio 预览 / `review_helper.py --theme`（mdnice 服务端渲染） | 中文名 | `紫色渐变`、`姹紫` 等 ~44 个 | `curl -s http://127.0.0.1:8070/api/themes \| jq '.[].name'` |

- 两套名字**互不通用**：`--theme green` 只对 push_article.py 有效；`--theme 紫色渐变` 只对 mdnice 流程有效。别把中文名传给 push_article.py。
- **news（长文）当前默认**：`green`（萌绿，2026-06-23 起宇龙主用；白底 + 居中绿标题，完整样式规范见 `references/green-theme/spec.md`）。`紫色渐变`/`purple` 是旧默认，用户点名才用。
- **newspic（贴图）**：不渲染主题，纯文本+图片。
- 用户没指定就用当前默认，不要自己换主题。

#### 🌿 green（萌绿）两个必踩的坑（2026-07-13 实翻车固化）

1. **正文必须有 `## 小标题`**：萌绿的招牌样式（居中绿标题 `#48b378` + 上下装饰线）只渲染在 `##` 上。纯段落平铺的文章渲出来**通篇无绿**、和白底普通文没区别（实录：推完用户问"不是说用绿色主题吗？那个排版！"）。写稿时至少给 3~4 个短小标题；推前先 `--dry-run`，`grep -c '#48b378' dry.html` ≥ 2 才算绿主题真生效。
2. **重排旧文防紫色残留**：旧文 content 里的 inline `#7c3aed` 等紫色会原样透传进萌绿版，先改成 `#48b378` 或删掉（详见 spec.md）。

### 唯一允许的手写 HTML：独立链接居中

独立一行的链接（旧版回顾、外站跳转）必须用：

```html
<center><a href="https://example.com" style="color:#7c3aed">旧版网站回顾 →</a></center>
```

push_article.py 把以 `<` 开头 + `</x>` 结尾的行当 raw HTML 透传，不包 `<p>`，居中才不会失效。

### 文章末尾固定块（每篇 news 必加）

```html
<p style="display:none;"><mp-style-type data-value="10000"></mp-style-type></p>
```

微信编辑器识别用。push_article.py 会自动加，**但你写 markdown 时不要漏**。

### 签名规则（按类型分）

| 类型 | 签名 |
|---|---|
| **news**（长文章） | 不主动加签名，除非用户明确要求 |
| **newspic**（贴图/短帖） | ❌ 禁止加签名 |

提到 AI 助手时叫 **Hermes / 爱马仕**（两个名字都行，看上下文），**不再用** OpenClaw / 小龙虾（4/13 已发文公开切换）。

### 关注引导块规范（用户要求时才加）

news 默认不加签名/引导。但用户明确要求"加二维码、关注引导、商业合作"时，按这个规范放在正文最后，标题用 `## 写在最后`（不带编号）：

- 三段短话：① 一句承接正文的邀请；② 私信暗号 + 送什么；③ 商业合作 + 扫码备注。
- 暗号和赠品名（如 `「工具」`、`《AI 提效工具 · 普通人即装即用合集》`、`商业合作`）用行内 `<span style="color:#7c3aed;font-weight:700;">…</span>` 上色强调；`inline_format` 不转义 HTML，会原样进主题 `<p>`，所以正常 Markdown 段落里直接写 span 即可，不用整行 raw HTML。
- 赠品要写真实存在、能交付的东西（合集文档/清单），不要写空头承诺。
- 二维码用正常 Markdown 图片 `![扫码加我，备注「公众号」](images/qr-wechat.jpg)` + 斜体图注，跟着 `--images` 一起上传。
- 当前模板（2026-05-19 起作为规范之一）：

  ```md
  ## 写在最后

  如果你也想让 AI 先替你把第一版做出来，欢迎来找我聊聊。

  关注我之后，私信 <span style="color:#7c3aed;font-weight:700;">「工具」</span> 两个字，我把自己一直在用的那份 <span style="color:#7c3aed;font-weight:700;">《AI 提效工具 · 普通人即装即用合集》</span> 发你。

  如果你想把 AI 用到公司里，或者有 <span style="color:#7c3aed;font-weight:700;">商业合作</span> 的想法，也可以直接扫码加我。

  ![扫码加我，备注「公众号」](images/qr-wechat.jpg)
  *扫码加我，备注「公众号」。*
  ```

### 副标题（digest）走 API，本流程自动产出

副标题不是写进正文的，它是微信 `draft/add` 的 `digest` 字段，推送时单独带上。本 pipeline 已支持：

- `push_article.py --digest "..."` 直接把副标题写进 `digest` 字段。
- 副标题可由本流程根据正文自动拟一版（≤120 字），不用用户自己写。
- 但**必须单独发一条消息给用户**让其知晓，正文里不出现（见上面铁律④）。
- 落地到 `manifest.md` 的 `subtitle:` 字段存档。

### 用户中途补图的标准处理（让用户更省心）

用户经常在写稿过程中补发图片。收到补图后**不要等用户排序**，按这套自动跑：

1. **识别**：用 image-recognize（Gemini）跑一遍，搞清每张图是请求截图还是结果图、属于哪个岗位/小节。
2. **排序**：按故事线和逻辑关系排——同一件事的「请求截图 → 结果图」相邻成对；识别类的「原图 → 拆解截图」相邻；不要按用户发图的先后顺序硬排。
3. **去重 / 合并**：用户说"这两张没区分好"时，判断是不是同一个工作的不同步骤，能合并小节就合并（如"识别图片→拆解→反推生成"算一个工作）。
4. **落地**：存进 `materials/inbox/.../images/` 和 `drafts/.../images/`，按内容重命名（如 `2-dog-decompose.jpg`），不沿用 `微信图片_xxx` 这种名。
5. **上传 + 更新链接表**：推送时一并上传，推完用 `push-report.json` 刷新 `cloud-links.md` 的图片链接表。
6. **合规筛查**：补图里若含公众号 skill/后台、GitHub、VPS、维护脚本等内容，**不进正文**，在待确认项里说明原因（踩"不写公众号自动化"红线）。

### 写作中的负面表述软化

| 原稿写法 | 发布版 |
|---|---|
| "速度有点慢" | 删掉或改中性 |
| "推脱，不肯动" | "需要再催一句" |
| 政治性描述 | 删，只保留行为 |

### 紫色渐变主题长啥样（参考，不是让你抄）

JSON 文件：`/root/.openclaw/workspace-restore/docs/wxmp-themes/mdnice/紫色渐变.json`
渲染效果：渐变紫底色 + 紫色 H2 标题（`#7c3aed`）+ 卡片式 blockquote + 彩色渐变 hr。
新增主题：在 mdnice/ 加 JSON，**不需要改 SKILL，不需要 commit**。

---

## 推送前 QC 清单（全部 □ 通过再推）

### □ 标题检查
- [ ] 标题 ≤ 64 字（文章）/ ≤ 20 字（贴图）
- [ ] HTML 里 `<h1>` 已移除（避免和 API title 字段双标题）
- [ ] 标题经过 `references/title-formulas.md` 公式验证

### □ 图片检查
- [ ] **推前必数：markdown 中 `![]()` 引用数量 = mmbiz image_map 数量**（缺一不可）
- [ ] 所有 `<img src="...">` 是 `mmbiz.qpic.cn` 域名
- [ ] 无本地路径（`/root/.openclaw/...`）
- [ ] 无 `src="https://meltemi.vip` / `src="http://meltemi.vip`（href 里的外部链接如游戏链接是允许的，只要不是 img src 就行）
- [ ] 无第三方图片 URL / http 协议图片
- [ ] 封面图已单独上传 `add_material`，有正确的 `thumb_media_id`
- [ ] 每张正文章有对应 mmbiz URL

> **为什么这条排第一**：少漏一张图意味着要么重渲重推，要么草稿里缺图。2026-05-09 漏写 3 张图的教训。

### □ 正文内容检查
- [ ] 正文 > 100 字
- [ ] 无 `<!-- 配图 -->` 等 HTML 注释残留
- [ ] 正文和图文对照表都没有英文分段标签和零开头编号
- [ ] news 类型：没有手写签名，除非用户明确要求
- [ ] newspic 类型：结尾**没有**手写签名
- [ ] 负面评价已软化（"有点慢"→删掉或改中性）
- [ ] 无幻觉 Skill 名（只写真实存在的 Skill）
- [ ] 语气符合 references/writing-style.md 总则

### □ 金句 & 图注检查
- [ ] 主观评论/金句已抽出为 Blockquote
- [ ] 每张图有图注（不是文件名，不是"图片描述"）
- [ ] 图注和段落内容对应，不张冠李戴
- [ ] 图注里没有出现 `img_xx.jpg` 这样的文件名

图注示例：
- ❌ `img_04.jpg`
- ❌ `配图`
- ❌ `这是API调用流程图`
- ✅ `Claude Code 跑通后，终端输出 “Build successful”`
- ✅ `Hermes 在群里自动调起机票查询，把价格和航班时间列成表`

图注长度与句式（2026-07-14 用户反馈固化）：
- **要短**：一句话、20 字上下，只说画面重点，不求把图讲全。
- **禁止「XX：」冒号前缀式**：❌ `codexradar 上我的用量：累计 27 亿 token，7 月 13 号一天就跑了 3.3 个亿，连着用了 20 天` → ✅ `累计 27 亿 token，7 月 13 号一天就跑了 3.3 个亿`。
- 同理 ❌ `降智雷达：今天 Sol 的…` → ✅ 直接 `Sol 的 High 和 Medium 都是 135 分`。平台名/面板名正文里说过就行，图注不用再报幕。
- **图注句尾不带「。」**（2026-08-15 发布手改固化）：❌ `…有套餐就能直接登。` → ✅ `…有套餐就能直接登`。QC 的 `caption_trailing_period_hits` 非空不交付。
- **正文段尾句号混合**（2026-08-16 修正）：默认不带，约 1/5 自然收口句带；QC 的 `stylometry.hits` 非空不交付（段首模式/冒号/问号/逗号/句号率五项统计约束，阈值见 `references/anti-ai-stylometry.md`）。交付前跑 `scripts/voice_match.py --target article.md`，`verdict=UNLIKE` 或 `hits` 非空不交付；再跑 `scripts/aigc_check.sh`，`gate=pass` 才能自动交付。朱雀网页抽检，详见 `references/aigc-detector.md`。

### □ 推送就绪检查
- [ ] `digest`（摘要）单独发给用户，不写在文章正文里
- [ ] `digest`（摘要）≤ 120 字
- [ ] 独立一行的链接已用居中+颜色格式（`<center><a href="..." style="color:#7c3aed">文字 →</a></center>`）
- [ ] `draft/batchget` 确认草稿箱无同标题草稿（如有 → 告知用户等确认）
- [ ] 结尾点名 Hermes（爱马仕），不写 OpenClaw / 小龙虾
- [ ] 互动引导已拆行 + 加通俗词（末尾问句）
- [ ] 无政治性描述（只保留行为描述）

---

## 推送 API（编码坑 — ensure_ascii=False）

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

## 常见踩坑速查

| 坑 | 现象 | 解决 |
|----|------|------|
| 标题重复 | 草稿箱标题出现两次 | 去掉 HTML 里第一行 `# 标题` |
| 图片不显示 | 草稿里图片是叉叉 | ① 确认用的是 `data-src="mmbiz_url"` 格式（含完整 `mmbiz.qpic.cn` URL，不是 `src=""` 空值）② 重新上传图片到微信，用 uploadimg 返回的 URL 替换 ③ 微信草稿箱支持 `data-src` 懒加载格式，只要 URL 是 mmbiz 域名就没问题 |
| 中文乱码 | 内容全是 `\u4e2d\u6587` | 改用 `ensure_ascii=False` |
| 封面图错误 | 缩略图不对 | 重新上传封面图获取正确 `media_id` |
| 重复推送 | 同一篇草稿箱出现多次 | **推前 batchget 去重检查** |
| 贴图用了文章 API | 格式错误 | 贴图用 `newspic`，文章用 `news` |
| `lark-cli docs +media-download` 报 unsafe output path | 下载飞书图片失败 | `--output` 必须是文件名（如 `image1.png`），不能是目录。先 `cd` 到目标目录再用相对路径 |
| 贴图手写 Python 推送脚本 | 重复造轮子 | 复用 `push_article.py` 的 `upload_cover_image()` 上传素材，或用 `add_material` API 直接获取 media_id 后调 `draft/add` |
| 标题太长 | API 报 `45003` | 文章 ≤ 64 字，贴图 ≤ 20 字 |
| `<!-- 配图 -->` 残留 | HTML 出现注释文字 | 渲染前删掉所有 HTML 注释 |
| 残留英文分段标签 | 正文或图文对照表出现英文分段标签 | 改成 `## 1 小标题`，不要保留英文分段标签 |
| 擅自改标题 | 标题被加词/改词 | 用户确认什么标题就用什么，不自己改 |
| 封面图自己想当然 | 封面图和用户意图不符 | 用户说用哪张就用哪张，不自己换 |
| 编造 Skill 名 | 文章里写了不存在的 Skill | 只写实际存在的 Skill，没有的不准编 |
| 改了内容不推送 | 本地改了但没推 | 直接推，让用户看草稿箱效果再反馈 |
| 正文残留杂字（如"小红书"） | 渲染后HTML里多了乱文字 | 推送前 grep HTML 查残留文字，手动删掉 |
| 图注出现 img_xx 文件名 | 图注里出现了图片文件名 | 写图注时要像跟朋友描述图里有什么，禁止出现 img_xx.jpg |
| 图片 alt 被文件名覆盖 | 渲染后 HTML 里 img alt 是 `img_xx.jpg` 而不是 Markdown 写的文案 | push_article.py 第 614 行：`alt=alt if alt else img_info.get("alt", "")` — 优先级是 Markdown alt > image_map alt，不要反过来 |
| 链接没有居中+颜色 | 独立一行链接文字没有居中上色 | 用 `<center><a href="..." style="color:#7c3aed">文字 →</a></center>`，push_article.py 会做 raw HTML 处理不包 `<p>` |
| 副标题写在文章正文里 | digest 混在文章内容里 | digest 单独发给用户，不写进文章正文 |
| 贴图没加 article_type | 贴图被当成文章（news）处理 | payload 里必须加 `"article_type": "newspic"`，否则 draft/add 默认创建文章 |
| 正文外链 `<a>` 整段消失 | draft/add 后链接连字带 URL 全没了 | 微信服务端会剥掉非白名单域名的 `<a>`（含内文）。外部链接用**纯文本彩色 span**：`<center><span style="color:...;word-break:break-all;">https://…</span></center>`，读者复制访问；`mp.weixin.qq.com` 域名的 `<a>` 可保留 |

---

## 凭据位置

`push_article.py` 按这个顺序找第一个存在的文件：

```
$WXMP_ENV_FILE
~/.openclaw/secrets/wxmp-yulong.env          # Mac / Win 本机
/root/.openclaw/secrets/wxmp-yulong.env      # VPS
```

包含 `WXMP_APPID` 和 `WXMP_APPSECRET`。不要把这份文件放进 GitHub、weixin-write 仓库或可同步网盘。

家宽 / Win 本机直连 `api.weixin.qq.com` 通常会 `40164`（IP 不在白名单）。写稿仍在本机，推送改走：

```bash
python3 scripts/push_via_vps.py --markdown article-push.md --images images/a.png --title "标题" --cover images/a.png --theme green --author 宇龙 --digest "摘要"
```

---

## 写作风格速查

详见 `references/writing-style.md`（必须读）和 `references/GLOSSARY.md`（术语表）。

快速 QC 可直接读 `references/anti-regression-checklist.md`，按 6 条铁律逐项输出检查结论。

**核心要点：**
- 说人话，不说技术黑话
- 口语化短句，像跟朋友发微信
- 用 `## 1 小标题` 分段，不用英文分段标签和零开头编号
- 金句用 Blockquote 引用块
- 每图必须有图注
- 不主动加“我是宇龙...”这类签名；用户明确要求时再加
- 提到 AI 助手时点名 Hermes（爱马仕），不再用 OpenClaw / 小龙虾
- 负面评价软化处理

---

## 存档管理（发布后触发）

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

### 对比功能（对比原稿和发布版差异）

触发条件：用户说"对比一下"、"改了什么"、"diff"。

```bash
cd /root/.openclaw/skills/wxmp-article-pipeline
python3 scripts/diff_articles.py --list                # 列出所有可对比的文章
python3 scripts/diff_articles.py "2026-04-09"         # 模糊匹配（日期开头）
python3 scripts/diff_articles.py "2026-04-09-完整文件夹名"  # 精确匹配
```

输出内容：
- 发布版新增了哪些句子（发布时加的内容）
- 原稿有但发布版没有的句子（发布时删改的内容）
- 两版前100字预览

用于：检查发布后实际改了什么，评估改稿效果。

### 手改规律提炼（compare_publish_edits.py，2026-08-15 起）

发布后想总结「用户到底改了啥」，用这个（比 diff_articles.py 细，按类型归类）：

```bash
# 单篇：存档目录里要有 content.md（推送前稿）+ published.html（发布版）
python3 scripts/compare_publish_edits.py --archive-dir references/archives/published/<目录> --max-print 60

# 批量 + 汇总统计
python3 scripts/compare_publish_edits.py --all --json /tmp/publish-edits.json

# 三层对比（口述稿 → 推送版 → 发布版）
python3 scripts/compare_publish_edits.py --archive-dir <目录> --user-draft <口述稿.md>
```

改动分类：`punct_only`（纯标点）/ `split`（拆段）/ `tweak`（用词微调）/ `rewrite` / `added` / `removed`，外加图注句号统计和标题变更。

纪律：
- **每次发布后跑一遍**，把新规律补进 `references/personal-voice-rules.md`（v4 起是手改账本）。
- 发布版抓取：`archive_articles.py --latest` 正常时自动有；wxdown 失败时可 curl 公开链接存成 `published.html`（脚本能解微信的 `\x3c` JS 转义）。
- 2026-06 之前的老存档 content.md 是 pandoc 净化产物，格式噪音大（`------`/`\"`/加粗符号），批量统计只采信 2026-06-23 之后的对子。

---

## 已渲染草稿 review tab — 数据操作（不是改项目）

> ⚠️ **核心认知**：往「已渲染草稿」tab 加文章 **是数据操作，不是改项目**。
> `review/*.json` 是 FastAPI 每次请求才读的纯数据文件 — **不需要 commit、不需要重启服务、不需要 push 任何代码**。
> 把它当作"往一张表里 INSERT 一行"。

### 🔑 唯一规则：二选一，没有中间地带

**根据图片来源决定**：

| 图片来源 | 用什么命令 | 图片引用方式 |
|---|---|---|
| 🟢 文章已发布到公众号 → wxdown 已抓存档 | `add-published` | 真实 `https://mmbiz.qpic.cn/...` URL（存档里就有） |
| 🟡 本地草稿（未发布） | `add-draft` | 本地文件名 `![](062555-ae86.jpeg)`（draft images/ 目录里的文件） |

**就这两条。没有第三条。** 不存在"我手写一个 mmbiz URL"或"我用 LLM 生成的 HTML"这种路径。

### 🚫 严禁

- ❌ **永远不要手写 `mmbiz.qpic.cn` URL** — 它们只能来自两个地方：wxdown 抓的 published.html，或者 wxmp 上传 API 的真实返回值。**永远不要从你脑子里生成这种 URL，LLM 100% 会幻觉**
- ❌ 用 `cat > review/xxx.json` / `echo > ...` / Write 工具直接创建 review JSON — 用 `review_helper.py`
- ❌ 修改 `wxmp-studio/app.py`、重启服务、cp 图到 static 目录
- ❌ 用 `theme_source: "purple_html"` 或其他不存在的目录（合法值只有 `mdnice` 和 `jahseh`）
- ❌ 没有用户要求时主动加"我是宇龙..."这类签名

### ✅ 决策树

```
要把文章加进 review？
│
├─ 文章已经发布到公众号了？
│   ├─ 是 → archives/published/ 里有这篇？
│   │      ├─ 有 → 用 add-published（路径 A，下面）
│   │      └─ 没有 → 先跑 archive_articles.py 拉一份，再 add-published
│   └─ 没发布 → 走下面
│
└─ 没发布 → 文章写在 wxmp-studio/drafts/ 里了？
    ├─ 是 → 草稿 content 里图片是 ![](filename) 本地文件名？
    │      ├─ 是 → 用 add-draft（路径 B）
    │      └─ 不是 → 把图片标记改成本地文件名（drafts/{id}/images/ 里的真实文件名），再 add-draft
    └─ 不是 → 先在 drafts/ 里建草稿、把本地图放到 images/、写 ![](filename)，再走上面
```

### 路径 A：已发布文章 → `add-published`

```bash
HELPER=/root/.openclaw/workspace/projects/wxmp-studio/scripts/review_helper.py

python3 $HELPER add-published \
  --article-dir /root/.openclaw/skills/wxmp-article-pipeline/references/archives/published/2026-04-09-我给AI装上了外挂它能自 \
  --title "我给AI装上了外挂 (已发布)"
```

**渲染来源**：直接用 `published.html`，里面的 mmbiz URL 是 wxdown 抓时的真实 URL。和你手机上看到的一模一样。

### 路径 B：本地草稿 → `add-draft`

**前提**：草稿 `meta.json` 的 `content` 字段里图片必须是 **本地文件名**（不是 URL，不是绝对路径）：

```markdown
正文段落...

![](062555-ae86.jpeg)

正文段落...
```

文件名要和 `meta.json["images"][n]["filename"]` 完全一致。`app.py` 会自动改写成 `/api/drafts/{id}/images/062555-ae86.jpeg/file`。

```bash
python3 $HELPER add-draft \
  --draft-id 20260410-062506-c31247 \
  --title "SBTI 人格测试" \
  --theme 姹紫 \
  --auto-insert-images        # 草稿没图片标记？让脚本按段落均匀插
```

`--auto-insert-images` 会**直接修改 `drafts/{id}/meta.json`**（持久化、幂等），把 `images/` 里所有未引用的图按段落均匀插入。alt 用 image 的 `note` 字段。

### 主题预设（重要：永远从这里挑，不要发明新的）

所有主题都在 `/root/.openclaw/workspace-restore/docs/wxmp-themes/mdnice/*.json`。常用：

| theme 参数值 | 风格 | 适用场景 |
|---|---|---|
| `紫色渐变` | 渐变紫底色 + 彩色 hr + 卡片式 blockquote | **宇龙个人号默认** — 视觉冲击足、有辨识度 |
| `姹紫` | 纯白底 + 紫色标题 + 边框 blockquote | mdnice 经典紫色，正式一点 |
| `柠檬黄` | 黄绿色调 | 轻快、生活类内容 |
| `橙心` | 橙色调 | 活泼、热情 |
| `兰青` | 蓝青色 | 偏理性 / 技术 |
| `极简黑` | 黑白极简 | 严肃、专业 |
| `Pornhub黄` | 黄黑高对比 | 科技节奏感 / 段子 |
| `WeFormat` | 中性 | 通用 |

`--theme-source` 永远是 `mdnice`（默认值，不用写）。

完整主题列表（权威源）：`curl -s http://127.0.0.1:8070/api/themes` 返回的 JSON 数组里 `name` 字段就是合法 `--theme` 参数值。

🚫 **永远不要传不存在的主题名**（比如 `purple_html`、`紫色`、`hermes-purple`）。先调 `/api/themes` 确认存在再用，不要凭记忆或 ls 文件（文件枚举可能漏掉 json-only 主题）。

#### 加新主题（需要时）

如果用户说"我想要一个 XXX 风格的主题"：
1. 在 `/root/.openclaw/workspace-restore/docs/wxmp-themes/mdnice/` 加一个 `{name}.json`，schema 参考 `紫色渐变.json`
2. 不需要改任何代码或重启服务
3. 立即可以用 `--theme {name}`

### 列表 / 删除

```bash
python3 $HELPER list --confirmed-only
python3 $HELPER remove --id <review_id>
```

### 完整文档

`/root/.openclaw/workspace/projects/wxmp-studio/REVIEW.md`

### 触发场景

用户说："加到 review" / "加到已渲染草稿" / "做对比预览" / "在 wxmp 预览这篇文章"

→ 立即按上面决策树走 A 或 B。**永远不要绕过 review_helper.py，永远不要手写 mmbiz URL**。
