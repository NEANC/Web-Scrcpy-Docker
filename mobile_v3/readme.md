### 安装 qwen 模型所需的依赖项
```
pip install qwen_agent
pip install qwen_vl_utils
pip install numpy
```

### 在你的移动设备上安装 ADB 键盘
1. 下载 ADB 键盘的 [apk](https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk)  安装包。
2. 在设备上点击该 apk 来安装。
3. 在系统设置中将默认输入法切换为 “ADB Keyboard”。

### 运行
#### 安卓
```
cd Mobile-Agent-v3/mobile_v3
python run_mobileagentv3.py \
    --adb_path "../adb/windows/adb.exe" \
    --api_key "sk-6f502b9ebfd04a608068548214d130d4" \
    --base_url "https://dashscope.aliyuncs.com/compatible-mode/v1" \
    --model "qwen3-vl-plus" \
    --instruction "打开设置，查看系统版本" \
    --add_info ""
```
