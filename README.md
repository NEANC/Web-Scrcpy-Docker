# Web-Scrcpy Docker

基于 `[WebScrcpy-MobileAgent](https://github.com/ccizm/WebScrcpy-MobileAgent)` 修改，添加了链接时自动镜像与本地保存设备列表功能，移除了 AI 聊天与自动操作功能。  
使用 Docker 镜像在 `x86_64` 与 `arm64` 架构的 Linux 系统上运行；或使用源码形式在 `Windows/macOS/Linux` 系统上运行。

## 快速开始

### 使用 Docker Run 命令

1. 拉取镜像

   ```bash
   docker pull ghcr.io/neanc/web-scrcpy:latest
   ```

2. 运行容器

   ```bash
   docker run -d \
      --name web-scrcpy \
      --hostname web-scrcpy \
      -p 5000:5000 \
      -v ./data:/app/data \
      -v /dev/bus/usb:/dev/bus/usb \
      --privileged \
      --restart unless-stopped \
      -e FLASK_ENV=production \
      -e FLASK_APP=app.py \
      ghcr.io/neanc/web-scrcpy:latest
   ```

### 使用 Docker Compose

```bash
wget https://raw.githubusercontent.com/NEANC/Web-Scrcpy-Docker/main/docker-compose.yml

nano docker-compose.yml

docker-compose up -d
```

### 在本地构建 Docker 镜像

1. 克隆仓库

   ```bash
   git clone https://github.com/NEANC/Web-Scrcpy-Docker.git
   cd Web-Scrcpy-Docker
   ```

2. 构建镜像

   ```bash
   docker build -t web-scrcpy .
   ```

### 源码运行

1. 安装依赖

   ```bash
   pip install -r requirements.txt
   ```

2. 运行服务

   ```bash
   python app.py
   # 或指定视频码率
   python app.py --video_bit_rate 1024000
   ```

3. 访问 Web 界面
   - 打开浏览器访问 `http://localhost:5000/`。

## 许可证

Apache License 2.0
