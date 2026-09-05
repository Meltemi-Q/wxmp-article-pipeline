# 跨 Agent 同步体系与 Workbuddy（豆包工作）接入完全指南

本指南梳理了微信公众号全流程 Skill（`wxmp-article-pipeline`）在多 Agent、多设备之间的同步架构，以及如何将最新的规则和脚本无缝接入 **Workbuddy（豆包工作）** 等外部 Agent。

---

## 一、跨 Agent 同步架构现状（唯一真实源：GitHub）

为了避免不同 Agent（Antigravity、OpenClaw、Hermes、Workbuddy、Claude 等）各自为政、规则打架，整套流水线确立了以 **GitHub 官方仓库为唯一事实源（Single Source of Truth）** 的分布式协同架构：

```text
               ┌────────────────────────────────────────────────────────┐
               │    GitHub 官方仓库 (master 分支)                        │
               │    https://github.com/Meltemi-Q/wxmp-article-pipeline   │
               └──────────────────────────┬─────────────────────────────┘
                                          │
                  ┌───────────────────────┼───────────────────────┐
                  ▼                       ▼                       ▼
    ┌───────────────────────────┐ ┌───────────────┐ ┌───────────────────────────┐
    │ Mac 本地 / Antigravity    │ │ VPS 生产环境  │ │ Windows 本地 / Workbuddy  │
    │ (写稿、调试、发版源头)    │ │ (OpenClaw)    │ │ (豆包工作、桌面端协同)    │
    │ scripts/publish...sh      │ │ (Hermes)      │ │ git pull / 工作区挂载     │
    └───────────────────────────┘ └───────────────┘ └───────────────────────────┘
```

### 1. 各端同步现状盘点

| 环境 / Agent | 当前同步状态 | 同步机制 |
|---|---|---|
| **GitHub 官方源** | **实时基准** | 每次执行 `publish_wxmp_skill_changes.sh` 自动 push |
| **Mac 本地 (Antigravity / Codex)** | **实时同步** | 本地工作目录就是 git repo，改动即生效 |
| **VPS 云端 (OpenClaw / Hermes)** | **全自动同步** | 脚本 `deploy_wxmp_skill_to_vps.sh` 自动 rsync 到两个技能目录 |
| **Windows 本地** | **半自动 / 手动** | 跑 `update_wxmp_skill_from_github.sh` 或 `git pull` |
| **Workbuddy (豆包工作)** | **需配置工作区或指令** | 默认沙箱隔离，需按下列指引接入 |

---

## 二、Workbuddy（豆包工作）如何接入并保持同步？

Workbuddy 作为一个独立的桌面 AI 工作台，默认并不会自动嗅探外面的 Git 变动，除非将技能显式提供给它。

推荐以下 **三种接入方式**（按便捷程度排序）：

### 方案 1：工作空间直接绑定本地仓库（最推荐、零延迟）

将 Workbuddy 的当前会话或默认工作目录直接设为微信写作项目根目录：
- **Mac 路径**：`/Users/meltemi/Documents/yulong/weixin-write`
- **Windows 路径**：`D:\programs\weixin-write`

**在 Workbuddy 中的提示短语**：
> “写微信公众号文章前，请先完整阅读并严格遵守本地技能 `skills/wxmp-article-pipeline/SKILL.md` 及其 `references/` 下的个人口吻、图注规则与原生视频嵌入规范。”

**优势**：
- Workbuddy 每次读的都是你电脑上最新落盘的文件；
- Mac/Win 只要 `git pull` 过，Workbuddy 就能立刻享受到所有最新规则，无需重复配置。

---

### 方案 2：在 Workbuddy 的全局指令（Custom Instructions）中预设

如果 Workbuddy 支持设置个人偏好或预设 Prompt（Custom Instructions / Agent Settings），直接添加以下配置：

```markdown
### 微信公众号写作与发布规范
你的微信公众号文章发布流水线基于项目：
https://github.com/Meltemi-Q/wxmp-article-pipeline (branch: master)

核心纪律：
1. 飞书素材全量导出与保真：长文档必须基于 AST 完整抓取，严禁普通 DOM 滚动抓取漏图；图片纯二进制落地防损坏；结构与口吻 100% 遵从原稿，严禁脑补宏大战略与公关大词；
2. 微信原生视频优先：优先检测微信素材库中的用户原生上传视频（wxv_ 前缀），带原创认证与超清画质；
3. 图注与排版规范：每张图片正文精准对应，图注绝不带句号；文末唯一宇龙专属签名，避免多重签名。
```

---

### 方案 3：独立 Clone 与一键更新脚本（适用于独立沙箱环境）

如果在独立的机器或云端环境中运行 Workbuddy，直接使用标准 Git 命令拉取：

```bash
# 首次获取
git clone https://github.com/Meltemi-Q/wxmp-article-pipeline.git

# 以后每次写稿前一键拉取最新规则
cd wxmp-article-pipeline && git pull origin master
```

---

## 三、跨 Agent 规则更新与发版纪律

每次我们对 Skill 做出的修复（例如视频嵌入修复、防漏图机制、新主题等）：
1. **统一发版命令**：
   ```bash
   bash scripts/publish_wxmp_skill_changes.sh "更新说明"
   ```
   该脚本会自动：
   - Commit 本地更改；
   - Push 到 GitHub `master` 分支；
   - 自动调用 `deploy_wxmp_skill_to_vps.sh` 将更新打到 VPS（同步 OpenClaw 和 Hermes）。
2. **其他端（包括 Win 端、Workbuddy 所在环境）只需要**：
   ```bash
   git pull origin master
   ```
   即可保持全网 100% 逻辑对齐！
