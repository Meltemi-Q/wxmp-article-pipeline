# 飞书素材全量导出与媒体完整性校验规范

本规范固化了飞书 Wiki/文档落地到本地素材库的关键防御机制，彻底杜绝“抓漏图”、“文章被截断”和“图片损坏报40137”的问题。

---

## 一、飞书长文档抓取铁律：严禁直接 DOM 粗暴抓取

### 1. 踩坑复盘
飞书云文档（尤其是带大量图文的长文档）采用了前端虚拟滚动（Virtual Scrolling）。
如果仅仅用普通浏览器的 `document.querySelectorAll('[data-block-type]')` 或者简单的向下滚动几屏，**只会抓取到最前部的几个 block，后面的核心测试、图表和结论会全部丢失**！

### 2. 标准导出工具：`feishu-doc-export/extract.js`
必须使用系统沉淀的完整提取脚本 `feishu-doc-export/extract.js`：
- 该脚本直接接入 `window.PageMain.blockManager.rootBlockModel`，通过 Block 树递归遍历，无视虚拟滚动的 DOM 卸载机制；
- 能够完整导出：文档标题、完整 Markdown 正文、包含有时效性签名（asynccode）的图片清单。

---

## 二、图片下载与二进制防损坏铁律（防 40137）

### 1. 致命踩坑：字节编码被 UTF-8 污染
在 Node.js 或浏览器上下文中，如果使用普通的字符串处理将图片数据写入文件，二进制字节会被强行按照 UTF-8 字符解码，导致非 UTF-8 字节被替换为 `\uFFFD`（十六进制 `ef bf bd`）。
结果就是：文件虽然看起来有几十 KB 或几 MB，但开头变成了 `efbf bd50 4e47...`，文件类型退化成 `data`，上传微信时直接报错：
`{'errcode': 40137, 'errmsg': 'invalid image format'}`

### 2. 标准下载操作流程
拿到了飞书导出的公开临时图片链接（包含 asynccode）后：
1. **统一使用 Python 原生二进制流下载**：
   ```python
   req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})
   with urllib.request.urlopen(req, timeout=15) as resp:
       content = resp.read()
       with open(target_path, 'wb') as fp:
           fp.write(content)
   ```
2. **下载完成后必须进行完整性自检**：
   使用 `file` 命令或 PIL 校验：
   ```bash
   file drafts/.../images/*
   ```
   必须全部显示为 `PNG image data` 或 `JPEG image data`，绝不能出现 `data`！
