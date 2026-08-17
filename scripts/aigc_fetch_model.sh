#!/usr/bin/env bash
# 拉中文 AIGC 检测 ONNX（约 98MB）。默认放到 ~/.aigc-detector-zh-onnx
set -euo pipefail
dest="${1:-$HOME/.aigc-detector-zh-onnx}"
base="${HF_ENDPOINT:-https://huggingface.co}/Eslzzyl/aigc-detector-zh-onnx/resolve/main"
mkdir -p "$dest/onnx"
echo "DEST=$dest"
echo "BASE=$base"
curl -fL --retry 3 --retry-delay 2 -o "$dest/tokenizer.json" "$base/tokenizer.json"
curl -fL --retry 3 --retry-delay 2 -o "$dest/onnx/model_quantized.onnx" "$base/onnx/model_quantized.onnx"
ls -lh "$dest/tokenizer.json" "$dest/onnx/model_quantized.onnx"
echo "OK"
