#!/usr/bin/env python3
"""
构建独立 macOS 可执行文件的打包脚本。
- 依赖：本机已有 Python 3.10.x（当前为 3.10.0）
- 生成产物：dist/<name> (单文件可执行)
使用示例：
    python3 macos_build_binary.py --entry app.py --name web-scrcpy
    python3 macos_build_binary.py --entry app.py --name web-scrcpy --extra --add-data static:static
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PYINSTALLER_VERSION = "5.13.2"  # 支持 Python 3.10，macOS 稳定
PYINSTALLER_HOOKS = "2023.9"     # 与 PyInstaller 5.13.2 兼容的 hooks 版本
PACKAGING_VERSION = "23.2"       # 避免 packaging 25.x 与旧 PyInstaller 组合导致的分析问题
DEFAULT_HIDDEN_IMPORTS = [
    "simple_websocket",  # flask-socketio threading 模式依赖
]
DEFAULT_COLLECT_ALL = [
    "simple_websocket",
]
DEFAULT_COLLECT_SUBMODS = [
    "socketio",
    "engineio",
    "flask_socketio",
]
DEFAULT_DATAS = [
    ("scrcpy-server", "scrcpy-server"),  # scrcpy server jar/binary
]

def run(cmd, env=None):
    print(f"[cmd] {' '.join(cmd)}")
    subprocess.check_call(cmd, env=env)

def ensure_venv(venv_path: Path, fresh: bool, python_exe: Path | None):
    if fresh and venv_path.exists():
        shutil.rmtree(venv_path)
    if not venv_path.exists():
        py = str(python_exe) if python_exe else sys.executable
        run([py, "-m", "venv", str(venv_path)])
    python_bin = venv_path / "bin" / "python"
    pip_bin = venv_path / "bin" / "pip"
    return python_bin, pip_bin

def clean_pyc(root: Path):
    """清理项目内的 __pycache__ 和 *.pyc，避免旧版本字节码导致分析出错。"""
    for path in root.rglob("__pycache__"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    for path in root.rglob("*.pyc"):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

def install_deps(pip_bin: Path, requirements: Path | None):
    # 先升级 pip，避免旧 pip 解析依赖异常
    run([str(pip_bin), "install", "--upgrade", "pip"])
    # 固定 PyInstaller 及其依赖版本，避免 packaging 25.x 与旧 PyInstaller 组合的解析崩溃
    run(
        [
            str(pip_bin),
            "install",
            f"pyinstaller=={PYINSTALLER_VERSION}",
            f"pyinstaller-hooks-contrib=={PYINSTALLER_HOOKS}",
            f"packaging=={PACKAGING_VERSION}",
        ]
    )
    if requirements and requirements.exists():
        run([str(pip_bin), "install", "-r", str(requirements)])

def build(python_bin: Path, entry: Path, name: str, icon: Path | None, extra_args: list[str]):
    # 清理旧构建
    for folder in ("build", "dist", f"{name}.spec"):
        path = Path(folder)
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    cmd = [
        str(python_bin),
        "-m",
        "PyInstaller",
        "--onefile",
        "--clean",
        "--name",
        name,
    ]
    for hidden in DEFAULT_HIDDEN_IMPORTS:
        cmd += ["--hidden-import", hidden]
    for pkg in DEFAULT_COLLECT_ALL:
        cmd += ["--collect-all", pkg]
    for pkg in DEFAULT_COLLECT_SUBMODS:
        cmd += ["--collect-submodules", pkg]
    # bundle scrcpy-server if present
    for src, dst in DEFAULT_DATAS:
        if (Path(src)).exists():
            cmd += ["--add-data", f"{src}:{dst}"]
    if icon:
        cmd += ["--icon", str(icon)]
    cmd += extra_args
    cmd.append(str(entry))
    run(cmd)

def main():
    parser = argparse.ArgumentParser(description="Build macOS binary with PyInstaller")
    parser.add_argument("--entry", required=True, help="入口 Python 文件，如 app.py")
    parser.add_argument("--name", default="app", help="生成的可执行名称")
    parser.add_argument("--icon", help="可选 .icns 图标路径")
    parser.add_argument(
        "--requirements", default="requirements.txt", help="依赖文件路径（可不存在）"
    )
    parser.add_argument(
        "--python-bin",
        help="用于创建构建虚拟环境的 Python 解释器路径（建议 3.10.13/3.10.14）",
    )
    parser.add_argument(
        "--extra",
        nargs="*",
        default=[],
        help="附加的 PyInstaller 参数，例如 --add-data 'static:static'",
    )
    parser.add_argument(
        "--reuse-venv",
        action="store_true",
        help="复用已有 .build-venv（默认每次重建以规避旧 pyc/依赖导致的解析错误）",
    )
    args, passthrough = parser.parse_known_args()

    project_root = Path(__file__).resolve().parent
    entry = (project_root / args.entry).resolve()
    icon = (project_root / args.icon).resolve() if args.icon else None
    requirements = (project_root / args.requirements).resolve() if args.requirements else None

    if not entry.exists():
        raise FileNotFoundError(f"入口文件不存在: {entry}")

    # 清理旧字节码，避免 PyInstaller 在 Python 3.10.0 上解析到不兼容的 .pyc
    clean_pyc(project_root)

    venv_path = project_root / ".build-venv"
    python_bin, pip_bin = ensure_venv(
        venv_path, fresh=not args.reuse_venv, python_exe=Path(args.python_bin) if args.python_bin else None
    )
    install_deps(pip_bin, requirements if requirements and requirements.exists() else None)
    # 同时清理虚拟环境内的 pyc，避免残留的跨版本字节码
    clean_pyc(venv_path)
    # 将显式传入的 --extra 以及未被 argparse 识别的参数一起透传给 PyInstaller
    extra_args = list(args.extra) + passthrough
    build(python_bin, entry, args.name, icon, extra_args)

    dist_bin = project_root / "dist" / args.name
    print(f"\n✅ 打包完成，可执行文件：{dist_bin}")
    print("复制 dist/<name> 到无 Python 的 macOS 即可运行。")

if __name__ == "__main__":
    main()