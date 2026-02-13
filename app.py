from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, send
from scrcpy import Scrcpy
from adb_manager import ADBManager
import argparse
import queue
import atexit
import os
import sys
import threading
from pathlib import Path
import re
from dotenv import load_dotenv, dotenv_values

# 确保 data 目录存在
os.makedirs('data', exist_ok=True)

# 定义 .env 文件路径
ENV_FILE_PATH = os.path.join('data', '.env')

# 加载 .env 文件
load_dotenv(ENV_FILE_PATH)

import json

# 读取和写入 .env 文件中的 ADB 地址
def get_saved_devices():
    """
    从 data/.env 文件中读取保存的所有设备 ADB 地址
    支持旧格式（逗号分隔）和新格式（JSON）
    """
    config = dotenv_values(ENV_FILE_PATH)
    devices_str = config.get('ADB_DEVICES', '')
    if not devices_str:
        return []
    
    # 尝试解析为 JSON 格式（新格式）
    try:
        devices_data = json.loads(devices_str)
        # 转换为列表格式：[{"name": "设备名称", "address": "ADB地址"}]
        return [{'name': name, 'address': address} for name, address in devices_data.items()]
    except json.JSONDecodeError:
        # 解析失败，使用旧格式（逗号分隔）
        devices = [device.strip() for device in devices_str.split(',') if device.strip()]
        # 转换为新的列表格式，设备名称默认为地址
        return [{'name': device, 'address': device} for device in devices]

def get_auto_stop_time():
    """
    从 data/.env 文件中读取自动停止时间（分钟）
    如果未设置，返回默认值15分钟
    """
    config = dotenv_values(ENV_FILE_PATH)
    auto_stop_time = config.get('AUTO_STOP_TIME', '15')
    try:
        return int(auto_stop_time)
    except (ValueError, TypeError):
        return 15

def get_demo_mode():
    """
    从 data/.env 文件中读取演示模式配置
    如果未设置，返回默认值False
    """
    config = dotenv_values(ENV_FILE_PATH)
    demo_mode = config.get('DEMO_MODE', 'False')
    return demo_mode.lower() in ('true')

def save_devices(devices):
    """
    将所有已连接的设备 ADB 地址保存到 data/.env 文件中
    使用 JSON 格式存储设备名称和地址的映射关系
    """
    config = dotenv_values(ENV_FILE_PATH)
    
    # 转换为字典格式：{"设备名称": "ADB地址"}
    devices_dict = {device['name']: device['address'] for device in devices}
    config['ADB_DEVICES'] = json.dumps(devices_dict)
    
    with open(ENV_FILE_PATH, 'w') as f:
        for key, value in config.items():
            f.write(f'{key}={value}\n')

# 设备管理器
class DeviceManager:
    def __init__(self):
        self.devices = {}  # 存储所有连接的设备
        self.adb_manager = ADBManager()

    def add_device(self, device_id, state="device", name=None):
        # 检查设备是否已存在
        if device_id not in self.devices:
            # 如果没有提供名称，使用设备ID作为名称
            device_name = name if name else device_id
            self.devices[device_id] = {
                "id": device_id,
                "name": device_name,
                "state": state,
                "is_mirroring": False,
                "scrcpy": None
            }
            return True
        return False
    
    def rename_device(self, device_id, new_name):
        """
        重命名已连接的设备
        """
        if device_id in self.devices:
            self.devices[device_id]["name"] = new_name
            return True
        return False

    def remove_device(self, device_id):
        if device_id in self.devices:
            if self.devices[device_id]["scrcpy"]:
                self.devices[device_id]["scrcpy"].scrcpy_stop()
            del self.devices[device_id]

    def start_mirror(self, device_id, callback):
        if device_id in self.devices and not self.devices[device_id]["is_mirroring"]:
            scpy = Scrcpy()
            scpy.device_id = device_id  # 设置设备ID
            if scpy.scrcpy_start(callback, video_bit_rate):
                self.devices[device_id]["scrcpy"] = scpy
                self.devices[device_id]["is_mirroring"] = True
                return True
            else:
                print(f"Failed to start scrcpy for device {device_id}")
        return False

    def stop_mirror(self, device_id):
        if device_id in self.devices and self.devices[device_id]["is_mirroring"]:
            self.devices[device_id]["scrcpy"].scrcpy_stop()
            self.devices[device_id]["scrcpy"] = None
            self.devices[device_id]["is_mirroring"] = False
            return True
        return False

    def get_device_list(self):
        return [
            {
                "id": d["id"],
                "name": d["name"],
                "state": d["state"],
                "is_mirroring": d["is_mirroring"]
            }
            for d in self.devices.values()
        ]

    def cleanup(self):
        for device_id in list(self.devices.keys()):
            self.remove_device(device_id)
        self.adb_manager.disconnect_device()

client_sid = None
message_queue = queue.Queue()
video_bit_rate = "1024000"
device_manager = DeviceManager()

# 注册退出时的清理函数
def cleanup_on_exit():
    device_manager.cleanup()

atexit.register(cleanup_on_exit)



app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# 显式使用线程模式，避免不必要的依赖探测带来的启动开销
socketio = SocketIO(app, async_mode='threading')

@app.route('/')
def index():
    return render_template('index.html')

def video_send_task():
    global client_sid
    while client_sid is not None:
        try:
            message = message_queue.get(timeout=0.01)
            if client_sid:  # 确保客户端仍然连接
                socketio.emit('video_data', message, to=client_sid)
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Error sending data: {e}")
        finally:
            socketio.sleep(0.001)
    print(f"video_send_task stopped")

def send_video_data(data):
    if not message_queue.full():
        message_queue.put(data)

@socketio.on('connect')
def handle_connect():
    global client_sid
    print('Client connected')
    client_sid = request.sid
    # 发送当前设备列表
    emit('device_list_update', device_manager.get_device_list())
    # 发送保存的设备列表
    saved_devices = get_saved_devices()
    emit('saved_devices', saved_devices)
    # 发送自动停止时间
    auto_stop_time = get_auto_stop_time()
    emit('auto_stop_time', {'minutes': auto_stop_time})
    # 发送演示模式状态
    demo_mode = get_demo_mode()
    emit('demo_mode', {'enabled': demo_mode})
    return True

def get_current_mirroring_device_id():
    for did, info in device_manager.devices.items():
        if info.get("is_mirroring"):
            return did
    return None



@socketio.on('connect_device')
def handle_device_connect(data):
    try:
        ip = data.get('ip')
        port = int(data.get('port', 5555))
        device_id = f"{ip}:{port}"
        
        # 检查设备是否已连接
        if device_id in device_manager.devices:
            emit('connection_error', f'设备 {device_id} 已连接')
            return
        
        # 演示模式验证
        if get_demo_mode():
            # 获取保存的设备列表（包含预设IP）
            saved_devices = get_saved_devices()
            # 检查设备ID是否在预设列表中
            if not any(device['address'] == device_id for device in saved_devices):
                emit('connection_error', '演示模式下只允许连接预设的设备')
                return
        
        # 尝试连接设备
        print(f'Trying to connect to device: {device_id}')
        success, output = device_manager.adb_manager.connect_to_device(ip, port)
        if success:
            # 检查设备是否已保存，获取保存的名称
            saved_devices = get_saved_devices()
            device_name = device_id
            for device in saved_devices:
                if device['address'] == device_id:
                    device_name = device['name']
                    break
            
            if device_manager.add_device(device_id, name=device_name):
                # 更新保存的设备列表
                # 检查设备是否已保存（通过address字段）
                device_exists = any(device['address'] == device_id for device in saved_devices)
                if not device_exists:
                    # 添加新设备，名称默认为地址
                    saved_devices.append({'name': device_id, 'address': device_id})
                    save_devices(saved_devices)
                emit('device_list_update', device_manager.get_device_list())
                print(f'Device connected successfully: {device_id}')
                
                # 若已有其他设备在镜像，先关闭它们
                try:
                    for did, info in list(device_manager.devices.items()):
                        if info["is_mirroring"] and did != device_id:
                            device_manager.stop_mirror(did)
                            emit('mirror_stopped', {'device_id': did})
                    # 更新设备列表（状态变更）
                    emit('device_list_update', device_manager.get_device_list())
                except Exception as e:
                    print(f"Error stopping previous mirrors: {e}")
                
                # 自动开始镜像
                if device_manager.start_mirror(device_id, send_video_data):
                    socketio.start_background_task(video_send_task)
                    emit('device_list_update', device_manager.get_device_list())
                    emit('mirror_started', {'device_id': device_id})
                else:
                    emit('mirror_error', '启动镜像失败')
            else:
                device_manager.adb_manager.disconnect_device(ip, port)
                emit('connection_error', '设备添加失败')
        else:
            safe_output = (output or '').strip()
            emit('connection_error', f'无法连接到设备 {device_id}: {safe_output}')
    except Exception as e:
        print(f"Connection error: {str(e)}")
        emit('connection_error', f'连接错误: {str(e)}')

@socketio.on('disconnect_device')
def handle_device_disconnect(data):
    device_id = data.get('device_id')
    if device_id in device_manager.devices:
        device_manager.remove_device(device_id)
        device_manager.adb_manager.disconnect_device(
            *device_id.split(':') if ':' in device_id else (device_id, None)
        )
        emit('device_list_update', device_manager.get_device_list())
        print(f'Device disconnected: {device_id}')

@socketio.on('delete_saved_device')
def handle_delete_saved_device(data):
    """
    处理删除保存设备的请求
    """
    # 演示模式验证
    if get_demo_mode():
        emit('error', {'message': '演示模式下不允许删除设备'})
        return
    
    device_address = data.get('device_id')
    try:
        # 从保存的设备列表中移除该设备（通过address字段）
        saved_devices = get_saved_devices()
        # 过滤掉要删除的设备
        new_saved_devices = [device for device in saved_devices if device['address'] != device_address]
        if len(new_saved_devices) < len(saved_devices):
            save_devices(new_saved_devices)
            # 发送更新后的设备列表
            emit('saved_devices', new_saved_devices)
            print(f'Saved device deleted: {device_address}')
        else:
            emit('error', {'message': '设备未找到'})
    except Exception as e:
        emit('error', {'message': f'删除设备失败: {str(e)}'})
        print(f'Error deleting saved device: {e}')

@socketio.on('rename_saved_device')
def handle_rename_saved_device(data):
    """
    处理重命名保存设备的请求
    """
    device_address = data.get('device_address')
    new_name = data.get('new_name')
    try:
        if not device_address or not new_name:
            emit('error', {'message': '设备地址和新名称不能为空'})
            return
        
        # 从保存的设备列表中找到对应的设备
        saved_devices = get_saved_devices()
        device_found = False
        
        for device in saved_devices:
            if device['address'] == device_address:
                device['name'] = new_name
                device_found = True
                break
        
        if device_found:
            save_devices(saved_devices)
            # 发送更新后的设备列表
            emit('saved_devices', saved_devices)
            # 同时更新已连接设备的名称
            if device_address in device_manager.devices:
                device_manager.rename_device(device_address, new_name)
                emit('device_list_update', device_manager.get_device_list())
            print(f'Saved device renamed: {device_address} -> {new_name}')
        else:
            emit('error', {'message': '设备未找到'})
    except Exception as e:
        emit('error', {'message': f'重命名设备失败: {str(e)}'})
        print(f'Error renaming saved device: {e}')

@socketio.on('rename_device')
def handle_rename_device(data):
    """
    处理重命名已连接设备的请求
    """
    device_id = data.get('device_id')
    new_name = data.get('new_name')
    try:
        if not device_id or not new_name:
            emit('error', {'message': '设备ID和新名称不能为空'})
            return
        
        # 重命名已连接的设备
        if device_manager.rename_device(device_id, new_name):
            # 同时更新保存的设备列表中的设备名称
            saved_devices = get_saved_devices()
            for device in saved_devices:
                if device['address'] == device_id:
                    device['name'] = new_name
                    save_devices(saved_devices)
                    emit('saved_devices', saved_devices)
                    break
            
            # 发送更新后的设备列表
            emit('device_list_update', device_manager.get_device_list())
            print(f'Device renamed: {device_id} -> {new_name}')
        else:
            emit('error', {'message': '设备未找到'})
    except Exception as e:
        emit('error', {'message': f'重命名设备失败: {str(e)}'})
        print(f'Error renaming device: {e}')

@socketio.on('start_mirror')
def handle_start_mirror(data):
    device_id = data.get('device_id')
    # 若已有其他设备在镜像，先关闭它们
    try:
        for did, info in list(device_manager.devices.items()):
            if info["is_mirroring"] and did != device_id:
                device_manager.stop_mirror(did)
                emit('mirror_stopped', {'device_id': did})
        # 更新设备列表（状态变更）
        emit('device_list_update', device_manager.get_device_list())
    except Exception as e:
        print(f"Error stopping previous mirrors: {e}")

    # 确保设备被保存到 .env 文件
    saved_devices = get_saved_devices()
    # 检查设备是否已保存（通过address字段）
    device_exists = any(device['address'] == device_id for device in saved_devices)
    if not device_exists:
        # 添加新设备，名称默认为地址
        saved_devices.append({'name': device_id, 'address': device_id})
        save_devices(saved_devices)
        emit('saved_devices', saved_devices)
        print(f'Device saved to .env: {device_id}')

    if device_manager.start_mirror(device_id, send_video_data):
        socketio.start_background_task(video_send_task)
        emit('device_list_update', device_manager.get_device_list())
        emit('mirror_started', {'device_id': device_id})
    else:
        emit('mirror_error', '启动镜像失败')

@socketio.on('stop_mirror')
def handle_stop_mirror(data):
    device_id = data.get('device_id')
    if device_manager.stop_mirror(device_id):
        emit('device_list_update', device_manager.get_device_list())
        emit('mirror_stopped', {'device_id': device_id})
    else:
        emit('mirror_error', '停止镜像失败')

@socketio.on('disconnect')
def handle_disconnect():
    global client_sid
    client_sid = None
    print('Client disconnected')
    # 停止所有正在镜像的设备
    for device_id in list(device_manager.devices.keys()):
        if device_manager.devices[device_id]["is_mirroring"]:
            device_manager.stop_mirror(device_id)
    print('Session cleaned up')

@socketio.on('control_data')
def handle_control_data(data):
    print(f"Received control data: {data}")  # 添加调试信息
    device_id = data.get('device_id')
    if device_id and device_id in device_manager.devices:
        device_info = device_manager.devices[device_id]
        if device_info["is_mirroring"] and device_info["scrcpy"]:
            try:
                control_data = data.get('data')
                if control_data:
                    print(f"Sending control data to device {device_id}: {len(control_data)} bytes")  # 调试信息
                    device_info["scrcpy"].scrcpy_send_control(control_data)
                    print("Control data sent successfully")  # 调试信息
                else:
                    print("No control data found in request")  # 调试信息
            except Exception as e:
                print(f"Error sending control data: {e}")
                emit('control_error', f'发送控制数据失败: {e}')
        else:
            print(f"Device {device_id} is not mirroring or scrcpy instance not found")  # 调试信息
            emit('control_error', '设备未在镜像状态')
    else:
        print(f"Device {device_id} not found in device manager")  # 调试信息
        emit('control_error', '设备未找到')



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Web server for scrcpy')
    parser.add_argument('--video_bit_rate', default="1024000", help='scrcpy video bit rate')
    parser.add_argument('--port', type=int, default=5000, help='port to bind the web server to')
    args = parser.parse_args()
    video_bit_rate = args.video_bit_rate
    socketio.run(app, host='0.0.0.0', port=args.port, allow_unsafe_werkzeug=True)