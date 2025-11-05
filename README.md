## 项目简介

- 基于 `scrcpy` 的浏览器端控制与投屏服务，允许你在网页中实时镜像并操控 Android 设备。
- 本项目为 fork 并改进自 `baixin1228/web-scrcpy`，在设备管理、端口转发、输入控制、前端交互与稳定性方面做了多处增强。

## 视频演示


https://github.com/user-attachments/assets/adb5748d-e84e-448a-8dfb-283e7845232b



## 功能特性

- 浏览器实时镜像：H.264 码流在前端通过 `JMuxer` 低延时播放。
- 多设备管理：页面展示设备列表，支持连接、断开、开始/停止镜像，避免并发镜像冲突。
- 交互控制完整：鼠标点击/拖动、滚轮、键盘按键，以及电源、音量、返回、主页、菜单等按钮控制。
- 分辨率自适应：自动适配横竖屏变化与大小变更，更新输入坐标映射。
- 动态端口转发：自动查找可用本地端口（起始 `6666`），避免与常用端口冲突。
- 可配置视频码率：通过命令行参数 `--video_bit_rate` 设置码率。
- 内置 ADB：已包含 `adb` 二进制（Windows/macOS/Linux），开箱即用。
 - AI 聊天与自动操作：前端聊天面板发送自然语言指令，后端基于 Mobile-Agent-v3 驱动当前镜像设备执行操作，支持流式日志与最终回答。

## 架构说明

- 后端（Python）
  - `Flask` + `Flask-SocketIO` 提供页面与双向通信。
  - `app.py`：
    - 维护 `DeviceManager`（设备列表、镜像状态与 `Scrcpy` 实例）。
    - Socket 事件：`connect_device`、`disconnect_device`、`start_mirror`、`stop_mirror`、`control_data`。
    - 视频发送：后端接收 H.264 字节流并通过事件 `video_data` 推送到前端，采用消息队列 + 后台任务解耦。
  - `scrcpy.py`：
    - 向设备 `push` `scrcpy-server.jar` 至 `/data/local/tmp/scrcpy-server.jar`。
    - `adb forward tcp:<local_port> localabstract:scrcpy` 建立隧道；依次创建三路连接（video/audio/control）。
    - 读取视频数据并回调给后端；将前端的控制数据通过 `control_socket` 发送到 scrcpy 服务端。
  - `adb_manager.py`：
    - 自动选择平台对应的 `adb` 路径。
    - 提供 `connect_to_device(ip, port)`；含启用 TCP/IP 的辅助方法（未在页面直接暴露）。

- 前端（HTML/JS/CSS）
  - `templates/index.html`：设备列表、控制面板、视频容器与交互逻辑。
  - `static/js`：
    - `jmuxer.min.js`：H.264 播放。
    - `video_parser.js` + `h264-sps-parser.js`：解析 NALU、SPS/PPS 与分辨率变化。
    - `input.js`：封装鼠标、滚轮与键盘事件，组包为 scrcpy 控制协议，通过 `Socket.IO` 发送 `control_data`。

## 快速开始

- 环境要求
  - Python 3.8+。
  - 浏览器（Chrome/Edge/Firefox 等）。
  - Android 设备开启开发者选项与 `USB 调试` 或已启用 `TCP/IP 调试`。

- 安装依赖
  - 在项目根目录执行：
    - `pip install -r requirements.txt`

- 配置环境变量（可选，用于 AI 聊天与自动操作）
  - 在项目根目录创建 `.env` 文件，填入以下变量（示例占位即可，按你的服务提供者填写）：
    - `AGENT_API_KEY=你的密钥`
    - `AGENT_BASE_URL=你的接口地址`
    - `AGENT_MODEL=你的模型标识`
  - 注意：未设置上述变量时，AI 聊天功能不可用，页面会提示“后端未配置 AI 模型服务…”。

- 运行后端
  - 默认码率运行：
    - `python app.py`
  - 指定视频码率（例如 `1024000`）：
    - `python app.py --video_bit_rate 1024000`
  - 服务启动后监听 `http://localhost:5000/`。

- 连接设备（页面操作）
  - 打开浏览器访问 `http://localhost:5000/`。
  - 在左侧“设备连接”区域输入设备 `IP` 与 `端口`（默认 `5555`），点击“连接设备”。
  - 在设备列表中点击“开始镜像”，开始视频播放并显示控制面板。
  - 可随时“停止镜像”或“断开连接”。

## 使用指南

- 视频播放
  - 首帧等待关键帧（IDR），确保画面正常；分辨率变化时自动重建播放器并等待新关键帧。

- 输入与控制
  - 鼠标左键：触摸按下/移动/抬起。
  - 鼠标右键：映射为“返回”。
  - 鼠标滚轮：滚动事件传递至设备。（注意：部分设备可能不支持）
  - 键盘按键：已映射常见字母/数字/方向键/控制键；可在视频区域获得焦点后直接输入。
  - 顶部控制图标：电源、音量加/减、返回、主页、菜单等。

- 设备管理
  - 页面展示已连接设备的状态（`device`/镜像中/未镜像）。
  - 启动新的镜像前会自动停止其他设备的镜像，避免资源竞争。

### AI 聊天与自动操作

- 前提条件
  - 至少有一个设备在“开始镜像”状态。
  - `.env` 中已正确配置 `AGENT_API_KEY`、`AGENT_BASE_URL`、`AGENT_MODEL`。

- 使用方式（页面端）
  - 在右侧聊天面板输入指令，例如“打开设置”。
  - 点击“发送”，后端会启动 Mobile-Agent-v3 针对当前镜像设备执行步骤；过程日志以流式文本显示在气泡中，结束后返回最终回答。
  - 如需中止正在进行的任务，点击“停止”。

- 日志与图片
  - 后端将操作过程日志保存在 `./logs/<时间戳>_<指令>/step_x/` 下，包含 `manager.json`、`operator.json`、`reflector.json` 等。
  - 部分 JSON 内含图片（base64 编码）。你可在后处理脚本中解析并保存为文件，或扩展前端将相关截图以图片卡片形式展示。

> 说明：当前前端聊天泡泡内默认显示流式文本与最终回答；图片展示可按需扩展（不影响日志文件的生成与保存）。

## 常见问题与提示

- 首次镜像会向设备推送 `scrcpy-server.jar` 到路径 `/data/local/tmp/scrcpy-server.jar`。
- ADB 端口转发使用本地动态端口（起始 `6666`），通过 `localabstract:scrcpy` 隧道到设备，无需开放外部端口。
- 设备授权：若通过 USB 首次连接，请确认设备上弹出的授权提示已接受。
- 音频：已建立音频 socket，当前前端未播放音频（如需可扩展为音频解码/播放）。
- TCP/IP 模式：未开启时可使用标准命令在 USB 下启用（示例）：
  - `adb tcpip 5555` 后拔线，`adb connect <设备IP>:5555`。

- AI 聊天无法使用并提示“后端未配置 AI 模型服务（环境变量 AGENT_API_KEY/AGENT_BASE_URL/AGENT_MODEL）”
  - 请在仓库根目录创建 `.env`，补齐上述三项变量；重启后端服务后再试。
  - 如果你在多设备场景下使用 AI 聊天，请确保页面上已有设备处于“开始镜像”状态，否则会提示“未找到正在镜像的设备…”。

## 与上游项目的差异（本仓库改进点）

- 多设备管理：新增 `DeviceManager` 与设备列表 UI；支持连接/断开与状态同步。
- 动态端口转发：自动查找可用端口（起始 `6666`），降低端口冲突概率。
- 前端交互优化：横竖屏、分辨率变化的自动适配，UI 提示更明确。
- 错误处理增强：连接、镜像、控制链路的异常反馈更清晰。

## 目录结构（摘录）

- `app.py`：后端入口与 Socket 事件处理。
- `scrcpy.py`：与设备交互（推送 server、端口转发、三路连接、读写数据）。
- `adb_manager.py`：ADB 路径与连接管理工具。
- `scrcpy-server`：scrcpy 服务端 jar 文件（推送至设备）。
- `templates/index.html`：页面模板与核心前端逻辑。
- `static/js/`：前端脚本（`jmuxer.min.js`、视频解析、输入控制等）。
- `adb/`：跨平台 ADB 二进制（`windows/adb.exe`、`linux/adb`、`darwin/adb`）。
- `mobile_v3/`：Mobile-Agent-v3 相关代码与工具（`run_mobileagentv3.py`、`utils/`）。
- `logs/`：AI 自动化运行日志输出目录（按时间戳与指令分组）。

## 许可证

- 详见仓库内 `LICENSE.txt`。

## 致谢

- 上游项目：`baixin1228/web-scrcpy`。
- `scrcpy` 与相关开源组件的贡献者们。
