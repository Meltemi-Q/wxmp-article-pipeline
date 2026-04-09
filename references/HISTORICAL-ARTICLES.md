# 历史文章索引

> 每次推送新文章后，必须更新此文件。
> 写新文章前，必须先读最近3篇参考风格。

## 存档目录结构

```
archives/
  published/           ← 已发布文章（md + 图片）
  drafts/              ← 废弃草稿（保留不删）
  revisions/           ← 修改记录
```

## 已发布文章（从微信后台拉取）

| 日期 | 标题 | 链接 | 摘要 |
|------|------|------|------|
| 2026-04-09 | 我给AI装上了外挂，它能自动帮我搞副业 | https://mp.weixin.qq.com/s/XyYQj1vBIjG6p_9mTwG9zQ | 高手做事，牵牛要牵牛鼻子，找到主要矛盾。 |
| 2026-04-06 | 顶级AI工具仍然离不开各种狗链子？😂 | https://mp.weixin.qq.com/s/TdMXB_A5_gvuAriDL8ZxXw | |
| 2026-04-05 | 同样是刷视频，为什么有人越刷越聪明？ | https://mp.weixin.qq.com/s/4w2xrBWbo1BzkvGQS8_5eg | 工具只是入口，真正拉开差距的是谁愿意多想一步 |
| 2026-04-02 | AI 治好了我的拖延症 | https://mp.weixin.qq.com/s/u-cLpudNfnpjKSD7wFsukw | |
| 2026-03-31 | 最强 AI 编程工具 Claude Code 被扒了个底朝天，我看到了 AI 行业不想让你知道的事 | https://mp.weixin.qq.com/s/H0Jbw2ShR2vkOYnW6b5XRQ | Claude Code 源码泄露，1902份文件被扒了个底朝天。造 AI 的人，比谁都不信 AI。 |
| 2026-03-28 | 我花了两个小时，给自己开了一条赚美元的路 | https://mp.weixin.qq.com/s/osgbt079Rw9zi38F4ahsXg | 从算账到注册 Upwork，AI 助手小龙虾全程陪我搞定 |
| 2026-03-24 | 能把有限资源用好的人，都很厉害 | https://mp.weixin.qq.com/s/Gqq5Yx6Hl2MlIEuP5h9oeQ | |
| 2026-03-23 | 我把10个AI拉进一个群，第一天就乱了——但结果很香 | https://mp.weixin.qq.com/s/lBlYqiJWONYE2p3qP81JhA | 群建好的那晚，我随便发了一条消息。罗宾秒回了。就这一句，有点奇妙。 |
| 2026-03-22 | 你的小龙虾，微信也能养啦（附教程） | https://mp.weixin.qq.com/s/b5F0mqFDcFNuVHjdi7BRPg | 微信刚刚更新了，可以直接连接你的 OpenClaw（小龙虾）了！ |
| 2026-03-21 | 我给我的10个AI员工写了份简历，挂到了网上 | https://mp.weixin.qq.com/s/OBKUE2Ky_CVAj8a4VcNEvQ | 做副业有段时间了，一开始我就一个AI助手，什么事都扔给它。 |

## 草稿存档

| 日期 | 标题 | 目录 | 状态 | 备注 |
|------|------|------|------|------|
| 2026-04-09 | 我给AI装上了外挂，它能自动帮我搞副业了 | 20260409-090548-2207dd | 已发布 | 与发布版有差异：标题少"了"、PART3标题不同；草稿存档：2026-04-09-ai外挂-副业自动化-published.md |
| 2026-04-08 | 小红书正文全在图里？AI给我全扒完了 | 20260408-162720-baa108 | 草稿 | 未推送，风格参考 |

## 读文章流程

写新文章前必须执行：

```bash
# 1. 查看最近发布文章列表
cat references/HISTORICAL-ARTICLES.md

# 2. 读最近3篇已发布文章的完整内容（md格式）
cat archives/published/*.md | head -100

# 3. 确认写作风格一致后再动笔
```

## 拉取新文章

```bash
# 查看文章列表
cd skills/wxmp-wxdown && python3 scripts/wxdown-manage.py articles findyi --size 10

# 下载已发布文章存档
cd skills/wxmp-wxdown && python3 scripts/wxdown-manage.py download "<url>" --format md > archives/published/<date>-slug-published.md
```

## 文章命名规范

已发布文章文件名：`YYYY-MM-DD-文章标题-slug-published.md`
草稿文件名：`YYYYMMDD-HHMMSS-xxx/content.md`
例如：`2026-04-09-ai外挂-副业自动化-published.md`
