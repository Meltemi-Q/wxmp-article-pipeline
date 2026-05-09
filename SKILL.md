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
curl -s -b /tmp/wxmp_cookie.txt -H 'content-type: application/json' -d '{"mode":"article","action":"one_pass"}' https://wxmp.meltemi.fun/api/drafts/<draft_id>/writing-prompt
/usr/local/bin/wxmp-sync mp-sync --limit 200
```

## 触发词路由（先分流，再执行）

| 用户怎么说 | 用哪个 skill / 命令 | 目的 |
|---|---|---|
| “推草稿箱”“发公众号”“渲染文章”“发贴图/小绿书” | `wxmp-article-pipeline` | 写作、排版、上传、推草稿 |
| “抓一下刚发的”“冻结最新发布”“把刚发布的存档一下” | `python3 /root/.openclaw/workspace/projects/wxmp-studio/scripts/review_helper.py freeze-latest` | 抓最新已发布文章 HTML/MD，并加入 review tab |
| “查阅读量/点赞/分享/评论”“同步公众号数据”“做趋势分析” | `wxmp-sync` / `/usr/local/bin/wxmp-sync mp-sync --limit 200` | 同步后台指标到 SQLite/CSV |
| “下载某个公众号文章”“搜索公众号”“扫码登录 wxdown” | `wxmp-wxdown` | wxdown 文章下载/关注列表/扫码登录 |
| “wxmp 草稿转飞书文档”“公众号草稿转飞书”“图片图注保留” | `node scripts/wxmp-draft-to-feishu.js <draft-dir-or-md>` | 从草稿 Markdown 创建飞书 Docx，正文在前、图片和图注在后 |
| “从草稿生成 prompt”“一键写稿”“企业服务受众”“直接成飞书” | `/api/drafts/{draft_id}/writing-prompt` | 由 wxmp 草稿生成结构化 Hermes 写作 prompt |

不要把 `freeze-latest` 和 `wxmp-sync sync-all` 混为一个入口：前者管“正文归档 + review tab”，后者管“指标落库 + CSV 导出”。

## 预览口径（不要混）

- wxmp-studio 草稿/待审预览：`http://127.0.0.1:8070/api/rendered/{id}`。
- wxdown 已发布文章静态导出：`http://wxmp.meltemi.fun/uploads/<name>.html`。
- 推草稿前看排版，优先用 wxmp-studio 渲染预览；复盘已发布文章原貌，才用 wxdown 静态导出。

## ⚠️ 最高优先级纪律（读这两条比读别的更重要）

### 🧭 Hermes/MiniMax 写作输出契约

**写公众号时，先提纯再输出。不要把排障日志、工具过程、memory 讨论、模型自我解释混进正文或最终回复。**

每次写作必须按这个顺序做：

1. **提取锁定区**：用户已确认的标题、副标题 digest、封面、必须使用/必须排除的图片、最近一次“不对/重新/应该是”的修正。
2. **提取用户原话区**：语音转写、用户草稿、用户口语句，优先保留；只做顺序调整、错字修复、段落切分。
3. **写正文区**：只输出面向读者的文章 Markdown，不写工具说明，不写“我准备/我正在/我查到”。
4. **交付区固定四块**：`正文`、`副标题（单独发给用户，不进正文）`、`图文对照表`、`待确认项`。

MiniMax M2.7 容易把过程说得很散，所以回复用户时强制“一屏协议”：

- 中间进度最多 2 句，只说当前在做什么和下一步。
- 最终回复最多 4 块，不展开工具细节；工具结果只保留结论和路径。
- 不要在同一条回复里同时解释 memory 系统、研究背景、推送流程和正文修改；这些必须拆成不同任务块。
- 任何用户刚修正过的图文关系，必须优先进入图文对照表，而不是继续写新段落。

#### 第二道硬闸：写作测试/纯写稿时禁止冒充执行

如果用户只让“写一版/改一版/测试生成效果”，没有明确要求推草稿、上传图片、创建草稿或调用发布脚本：

- ❌ 不要写“我已读取草稿台”“14 张图都已上传到 mmbiz”“已经推送/已保存”。
- ❌ 不要在最终输出前加“Now I have...”“我现在开始写”等过程句。
- ✅ 最终回复第一行必须直接是 `正文` 或 `## 正文`。
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
- 图文对照表里的“对应段落”必须和正文真实小节标题一致；正文用 `## 01 小标题`，表格也写这个小节名，不要凭空加 `PART`。

发布或交付前必须跑机器 QC。最小流程：

```bash
python3 /root/.openclaw/skills/wxmp-article-pipeline/scripts/wxmp_article_contract_qc.py \
  --expected-images "073737-c55a.png,083126-cb79.png" \
  --output /tmp/article.md
```

如果 `score < 85`、`missing_body_images` 非空、`has_preface_or_process_lead=true`，或 `process_pattern_hits` 非空，不要交付，先修正文。

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

#### 第七道硬闸：图片没 note 时自动补图注

用户没给图片文字时，不要停住，也不要瞎删图：

- 先用 vision/图片查看能力识别图片内容。
- 自动生成一句“小字居中图注”。
- 图文对照表里标记 `note 来源=自动图注`。
- 待确认项列出这些图片，让用户发布前扫一眼。

更完整的写作提纯规则见 `references/hermes-minimax-output-contract.md`。

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
- 正文和图文对照表都不要再使用 `PART`，用 `## 01 小标题` 这种自然小节。
- 图片顺序默认照素材清单，不要为了制造反差把开头现实场景图后置。
- `uncaptioned_body_images` 必须为空，`has_image_mapping=true`，`has_todo=true`；否则不是合格交付。

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
- 错字修复
- 段落切分

**禁止**：把"我决定换掉龙虾"改成"决定迁移到新平台"这种**书面化重写**。

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

- 标题 ≤ 20 个中文字符。
- 正文是短句，不要 `PART` 长文结构。
- 不写副标题 digest。
- 不走紫色主题 HTML 长文渲染。
- 最终交付为：贴图标题、贴图正文、图片顺序表、待确认项。

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
| 标题 | ≤ 20 中文字 + 反差/惊喜 | "DeepSeekV4出了！我接进Hermes生成了视频" ✅ |
| 开头 | 1-3 行画面钩子 | "DeepSeek大家都期待了好久了" ✅ |
| 长度 | 150-400 字 | 03 那篇 150 字也可以发，不强求长 |
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

> ⚠️ 你不需要写任何 inline HTML。push_article.py 会按 theme JSON 服务端渲染。
> 你只管：写 markdown + 传 `--theme 紫色渐变`。下面只列**必须知道**的边界条件。

### 主题怎么选

- 唯一权威源：`curl -s http://127.0.0.1:8070/api/themes | jq '.[].name'`
- **news（长文）默认**：`紫色渐变`（宇龙个人号视觉冲击+辨识度）
- **newspic（贴图）**：不渲染主题，纯文本+图片
- 用户没指定就用默认，不要自己换主题

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
- [ ] 无 `src="https://meltemi.fun` / `src="http://meltemi.fun`（href 里的外部链接如游戏链接是允许的，只要不是 img src 就行）
- [ ] 无第三方图片 URL / http 协议图片
- [ ] 封面图已单独上传 `add_material`，有正确的 `thumb_media_id`
- [ ] 每张正文章有对应 mmbiz URL

> **为什么这条排第一**：少漏一张图意味着要么重渲重推，要么草稿里缺图。2026-05-09 漏写 3 张图的教训。

### □ 正文内容检查
- [ ] 正文 > 100 字
- [ ] 无 `<!-- 配图 -->` 等 HTML 注释残留
- [ ] 正文和图文对照表都没有 `PART`
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
| 残留 PART | 正文或图文对照表出现 `PART` | 改成 `## 01 小标题`，不要保留英文分段标签 |
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

---

## 凭据位置

```
/root/.openclaw/secrets/wxmp-yulong.env
```

包含 `WXMP_APPID` 和 `WXMP_APPSECRET`。

---

## 写作风格速查

详见 `references/writing-style.md`（必须读）和 `references/GLOSSARY.md`（术语表）。

快速 QC 可直接读 `references/anti-regression-checklist.md`，按 6 条铁律逐项输出检查结论。

**核心要点：**
- 说人话，不说技术黑话
- 口语化短句，像跟朋友发微信
- 用 `## 01 小标题` 分段，不用 `PART`
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
