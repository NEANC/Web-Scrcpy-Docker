#!/bin/bash
# Debian 10 打包脚本
# 使用 Python 3.10.14 或更高版本进行打包（如果已安装）
# 可以通过环境变量 PY310_BIN 指定 Python 解释器路径

PY310_BIN="${PY310_BIN:-python3}"

python3 debian_build_binary.py \
  --entry app.py \
  --name web-scrcpy \
  --extra \
  --add-data static:static \
  --add-data templates:templates \
  ${PY310_BIN:+--python-bin "$PY310_BIN"}

