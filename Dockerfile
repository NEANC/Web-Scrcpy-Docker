# 第一阶段：构建阶段
FROM alpine:latest AS builder

# 设置工作目录
WORKDIR /app

# 安装构建依赖
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-setuptools \
    py3-wheel \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev \
    make \
    jpeg-dev \
    zlib-dev \
    freetype-dev \
    lcms2-dev \
    openjpeg-dev \
    tiff-dev \
    libwebp-dev \
    gfortran \
    libstdc++ \
    lapack-dev \
    blas-dev

# 复制项目文件
COPY . /app

# 创建虚拟环境并安装 Python 依赖
RUN python3 -m venv /app/venv && \
    . /app/venv/bin/activate && \
    pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt && \
    # 清理虚拟环境中的不必要文件
    find /app/venv -name "__pycache__" -type d -exec rm -rf {} \; 2>/dev/null || true && \
    find /app/venv -name "*.pyc" -type f -exec rm -f {} \; 2>/dev/null || true && \
    find /app/venv -name "*.pyo" -type f -exec rm -f {} \; 2>/dev/null || true && \
    find /app/venv -name "*.egg-info" -type d -exec rm -rf {} \; 2>/dev/null || true && \
    find /app/venv -name "*.dist-info" -type d -exec rm -rf {} \; 2>/dev/null || true

# 第二阶段：运行阶段
FROM alpine:latest

# 设置工作目录
WORKDIR /app

# 安装运行时依赖
RUN apk add --no-cache \
    python3 \
    libffi \
    openssl \
    libstdc++ \
    jpeg \
    zlib \
    freetype \
    lcms2 \
    openjpeg \
    tiff \
    libwebp

# 从构建阶段复制必要的文件
COPY --from=builder /app/venv /app/venv
COPY --from=builder /app/app.py /app/app.py
COPY --from=builder /app/scrcpy.py /app/scrcpy.py
COPY --from=builder /app/adb_manager.py /app/adb_manager.py
COPY --from=builder /app/scrcpy-server /app/scrcpy-server
COPY --from=builder /app/templates /app/templates
COPY --from=builder /app/static /app/static
# 只复制 linux 平台的 ADB 工具，保持目录结构一致
RUN mkdir -p /app/adb/linux
COPY --from=builder /app/adb/linux /app/adb/linux

# 暴露端口
EXPOSE 5000

# 设置环境变量
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# 启动应用
CMD ["sh", "-c", ". /app/venv/bin/activate && python3 app.py --port 5000"]