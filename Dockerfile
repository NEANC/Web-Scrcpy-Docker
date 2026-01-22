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
    pip3 install --no-cache-dir --no-compile -r requirements.txt && \
    # 清理虚拟环境中的不必要文件
    find /app/venv -name "__pycache__" -type d -exec rm -rf {} \; 2>/dev/null || true && \
    find /app/venv -name "*.pyc" -type f -exec rm -f {} \; 2>/dev/null || true && \
    find /app/venv -name "*.pyo" -type f -exec rm -f {} \; 2>/dev/null || true && \
    find /app/venv -name "*.egg-info" -type d -exec rm -rf {} \; 2>/dev/null || true && \
    find /app/venv -name "*.dist-info" -type d -exec rm -rf {} \; 2>/dev/null || true && \
    # 清理 pip 缓存
    rm -rf /root/.cache/pip/* 2>/dev/null || true && \
    # 清理虚拟环境中不需要的脚本和文档
    rm -rf /app/venv/share 2>/dev/null || true && \
    rm -rf /app/venv/bin/*.py 2>/dev/null || true

# 第二阶段：运行阶段
FROM alpine:latest

# 设置工作目录
WORKDIR /app

# 安装最小化的运行时依赖
RUN apk add --no-cache \
    python3 \
    libffi \
    openssl \
    libstdc++ \
    jpeg \
    zlib \
    freetype

# 从构建阶段复制 Python 依赖到系统路径
COPY --from=builder /app/venv/lib/python3.*/site-packages /usr/lib/python3.*/site-packages
COPY --from=builder /app/venv/bin/python3 /usr/bin/python3

# 复制必要的应用文件
COPY --from=builder /app/app.py /app/app.py
COPY --from=builder /app/scrcpy.py /app/scrcpy.py
COPY --from=builder /app/adb_manager.py /app/adb_manager.py
COPY --from=builder /app/scrcpy-server /app/scrcpy-server
COPY --from=builder /app/templates /app/templates
COPY --from=builder /app/static /app/static

# 只复制必要的 ADB 可执行文件和库
RUN mkdir -p /app/adb/linux/lib64
COPY --from=builder /app/adb/linux/adb /app/adb/linux/adb
COPY --from=builder /app/adb/linux/lib64 /app/adb/linux/lib64
# 给 ADB 可执行文件添加执行权限
RUN chmod +x /app/adb/linux/adb

# 暴露端口
EXPOSE 5000

# 设置环境变量
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# 启动应用（直接使用系统 Python）
CMD ["python3", "app.py", "--port", "5000"]