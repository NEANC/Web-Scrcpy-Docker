# 使用指定的 Python 3.10.14 打包，确保目标机无需 Python 运行时
PY314_BIN=${PY314_BIN:-/Users/honghe/.pyenv/versions/3.10.14/bin/python3}

python3 macos_build_binary.py \
  --entry app.py \
  --name web-scrcpy \
  --extra --add-data static:static --add-data templates:templates \
  --python-bin "$PY314_BIN"