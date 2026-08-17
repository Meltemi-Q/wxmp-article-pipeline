# 朱雀替代：VPS 自托管检测

朱雀网页（`matrix.tencent.com/ai-detect`）有验证码、每日 5 次、无头常 `Invalid request`，不能当流水线硬依赖。

VPS / tx 都是无 GPU、3–6G 内存。Binoculars、Fast-DetectGPT、7B 双模型跑不动。

## 已落地（VPS，2026-08-17）

开源模型：`yuchuantian/AIGC_detector_zhv3` 的 INT8 ONNX（`Eslzzyl/aigc-detector-zh-onnx`，约 98MB）。

运行时只要 `onnxruntime` + `tokenizers` + `numpy`，不要 PyTorch。模型在 `~/.aigc-detector-zh-onnx/`，不进 Git。

```bash
scripts/aigc_fetch_model.sh          # 第一次
python3 scripts/aigc_detect.py 正文.txt
scripts/aigc_check.sh 正文.txt       # 优先打 127.0.0.1:8767
```

VPS 常驻：`aigc-server.service` 绑 `127.0.0.1:8767`，不要对公网开放。

退出码：`0=pass`（接近锚点）`2=review`（中间）`1=fail`（偏AI）`10=SKIP`。

## 和朱雀不是同一套分

用朱雀已测原文校准。**显著锚点分最低**，但四档对不齐。

| 文本 | 朱雀 | 自托管 ai / max | gate |
|---|---|---|---|
| 已发 30美元 Grok | 显著 | 0.020 / 0.020 | pass |
| 8/16 v5 正文 | 显著 | 0.108 / 0.229 | pass |
| 已发 10个AI进群 | 未发现 | 0.151 / 0.315 | review |
| 8/16 grokcli 裁段 | 较弱 | 0.259 / 0.457 | review |
| 8/14 四万条原稿 | 较弱 | 0.409 / 0.642 | review |
| Kindle 旧稿 | 未发现 | 0.405 / 0.808 | review |
| 已发 WorkBuddy一直免费 | 显著 | 0.511 / 0.927 | fail |
| Windows 旧稿 | 较弱 | 0.562 / 0.862 | fail |
| 已发 库克卖小米 | 未发现 | 0.733 / 0.968 | fail |

硬教训：

- 原话填骨架 / 短评口语，两边都认。
- 早期解释文、时评，朱雀更严；这边有时看起来还行（10个AI进群）。
- 短分析带商业推理，朱雀可能显著，这边第一窗会打成偏AI（WorkBuddy）。
- 「说白了」掉档是朱雀特有的，这边 8/14 原稿和 v2 分差不多。

所以：`gate=pass` 只表示「接近 8/16 v5 / 短评锚点」，**不要写成朱雀显著**。

## 流水线

```text
voice_match（像他）
  → aigc_check（VPS，必跑，无验证码）
  → gate=pass 才能自动交付
  → review/fail 先改稿；有空再抽朱雀
```

朱雀网页改抽检，能出分最好，出不了分不要卡死。

## 更接近朱雀的官方口（可选）

腾讯云「文本内容安全」`TextModeration`，`Type=TEXT_AIGC`。无网页验证码，最长 10000 字。控制台档位 Block / Review / Pass。

要开通内容安全、账户余额>0、控制台拿 BizType、云 API 密钥。密钥只放环境变量，不进仓库。

```bash
# TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY / TMS_BIZTYPE
python3 scripts/tencent_tms_aigc.py 正文.txt
```

文档：https://cloud.tencent.com/document/product/1124/118694

tx 在腾讯云，这条若开通，优先放 tx。

## 不要选

- Binoculars / Fast-DetectGPT：要 GPU 或 7B，VPS/tx 跑不动
- 网页朱雀当流水线：验证码 + 额度 + Invalid request
- 把开源分当成朱雀四档
