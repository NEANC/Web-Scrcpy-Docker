from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, send
from scrcpy import Scrcpy
from adb_manager import ADBManager
import argparse
import queue
import atexit
import os
from dotenv import load_dotenv
import sys
from contextlib import redirect_stdout, redirect_stderr
import threading
import base64
from pathlib import Path
import re

# 设备管理器
class DeviceManager:
    def __init__(self):
        self.devices = {}  # 存储所有连接的设备
        self.adb_manager = ADBManager()

    def add_device(self, device_id, state="device"):
        # 检查设备是否已存在
        if device_id not in self.devices:
            self.devices[device_id] = {
                "id": device_id,
                "state": state,
                "is_mirroring": False,
                "scrcpy": None
            }
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

# 先加载 .env，再读取相关配置，避免未加载导致的默认值不生效
load_dotenv()  # 读取项目根目录下的 .env
AGENT_API_KEY = os.getenv('AGENT_API_KEY')
AGENT_BASE_URL = os.getenv('AGENT_BASE_URL')
AGENT_MODEL = os.getenv('AGENT_MODEL')

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
    return True

def get_current_mirroring_device_id():
    for did, info in device_manager.devices.items():
        if info.get("is_mirroring"):
            return did
    return None

AGENT_JOBS = {}

def run_agent_and_reply(mid, text, stop_event: threading.Event):
    try:
        device_id = get_current_mirroring_device_id()
        if not device_id:
            socketio.emit('ai_chat_reply', { 'mid': mid, 'text': '未找到正在镜像的设备，请先连接并开始镜像。' })
            return

        # 读取 agent 配置
        api_key = AGENT_API_KEY
        base_url = AGENT_BASE_URL
        model = AGENT_MODEL

        if not api_key or not base_url or not model:
            socketio.emit('ai_chat_reply', { 'mid': mid, 'text': '后端未配置 AI 模型服务（环境变量 AGENT_API_KEY/AGENT_BASE_URL/AGENT_MODEL）。' })
            return

        # 绑定到当前设备：在 adb 路径后追加 -s <serial>
        adb_path = device_manager.adb_manager.adb_path
        adb_with_serial = f'"{adb_path}" -s {device_id}'

        # 按需加载重型依赖，避免后端启动时加载导致慢启动
        mobile_v3_path = os.path.join(os.path.dirname(__file__), 'mobile_v3')
        if mobile_v3_path not in sys.path:
            sys.path.insert(0, mobile_v3_path)
        from run_mobileagentv3 import run_instruction

        class _SocketStream:
            def __init__(self, mid):
                self.mid = mid
                self._buf = ""
            def write(self, s):
                try:
                    self._buf += s
                    while "\n" in self._buf:
                        line, self._buf = self._buf.split("\n", 1)
                        if line.strip():
                            socketio.emit('ai_chat_stream', { 'mid': self.mid, 'text': line })
                except Exception:
                    pass
            def flush(self):
                try:
                    if self._buf.strip():
                        socketio.emit('ai_chat_stream', { 'mid': self.mid, 'text': self._buf })
                        self._buf = ""
                except Exception:
                    pass

        out = _SocketStream(mid)
        err = _SocketStream(mid)

        with redirect_stdout(out), redirect_stderr(err):
            answer = run_instruction(
                adb_with_serial,
                None,
                api_key,
                base_url,
                model,
                text,
                "",
                "rel",
                False,
                max_step=25,
                log_path="./logs",
                stop_event=stop_event
            )

        if answer and isinstance(answer, str) and answer.strip():
            socketio.emit('ai_chat_reply', { 'mid': mid, 'text': answer })
        else:
            socketio.emit('ai_chat_reply', { 'mid': mid, 'text': '已执行操作（可能无显式回答）。如需答案类输出，请明确提出问题或等待更多步骤。' })

        # 推送本次指令的截图到前端聊天气泡
        try:
            def _emit_latest_images_for_instruction(mid, instruction: str, base_dir: str = './logs', limit: int = 8):
                base_path = Path(base_dir).resolve()
                if not base_path.exists():
                    return
                # 目录命名：YYYYMMDD_HHMMSS_<instruction[:10]>
                prefix = (instruction or '').strip()[:10]
                candidates = []
                for p in base_path.iterdir():
                    if not p.is_dir():
                        continue
                    name = p.name
                    if name.endswith(f"_{prefix}"):
                        try:
                            mtime = p.stat().st_mtime
                        except Exception:
                            mtime = 0
                        candidates.append((mtime, p))
                if not candidates:
                    return
                candidates.sort(key=lambda x: x[0], reverse=True)
                latest_dir = candidates[0][1]
                images_dir = latest_dir / 'images'
                if not images_dir.exists():
                    return
                imgs = []
                for fp in sorted(images_dir.glob('*.png')):
                    try:
                        b = fp.read_bytes()
                        b64 = base64.b64encode(b).decode('utf-8')
                        imgs.append(f'data:image/png;base64,{b64}')
                        if len(imgs) >= limit:
                            break
                    except Exception:
                        continue
                if imgs:
                    socketio.emit('ai_chat_images', { 'mid': mid, 'images': imgs })

            _emit_latest_images_for_instruction(mid, text)
        except Exception:
            # 图片推送失败不影响主流程
            pass

        # 推送每个 step 的摘要与前后截图（若可解析）
        try:
            def _is_b64(s: str):
                try:
                    if not s or len(s) < 64:
                        return False
                    return re.fullmatch(r'[A-Za-z0-9+/=]+', s) is not None
                except Exception:
                    return False

            def _parse_sections(text: str):
                text = text or ''
                def _extract(section):
                    pat = re.compile(rf'###\s*{section}\s*###\s*(.*?)\s*(?=###|$)', re.S)
                    m = pat.search(text)
                    return (m.group(1).strip() if m else '')
                return {
                    'thought': _extract('Thought'),
                    'action': _extract('Action'),
                    'description': _extract('Description'),
                    'outcome': _extract('Outcome'),
                    'error_description': _extract('Error Description'),
                }

            def _extract_images_from_messages(msgs, max_count=2):
                imgs = []
                try:
                    def walk(obj):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if isinstance(v, (dict, list)):
                                    walk(v)
                                elif isinstance(v, str) and _is_b64(v):
                                    imgs.append('data:image/png;base64,' + v)
                        elif isinstance(obj, list):
                            for it in obj:
                                walk(it)
                    walk(msgs)
                except Exception:
                    pass
                # 去重并限量
                uniq = []
                seen = set()
                for u in imgs:
                    if u not in seen:
                        uniq.append(u)
                        seen.add(u)
                        if len(uniq) >= max_count:
                            break
                return uniq

            def _emit_steps(mid, instruction: str, base_dir: str = './logs'):
                base_path = Path(base_dir).resolve()
                if not base_path.exists():
                    return
                prefix = (instruction or '').strip()[:10]
                candidates = []
                for p in base_path.iterdir():
                    if p.is_dir() and p.name.endswith(f'_{prefix}'):
                        try:
                            candidates.append((p.stat().st_mtime, p))
                        except Exception:
                            candidates.append((0, p))
                if not candidates:
                    return
                candidates.sort(key=lambda x: x[0], reverse=True)
                latest_dir = candidates[0][1]
                steps = []
                for step_dir in sorted(latest_dir.glob('step_*')):
                    try:
                        step_id = int(step_dir.name.replace('step_', '').strip())
                    except Exception:
                        step_id = None
                    data = {'step_id': step_id}
                    # 读三个文件
                    manager_json = step_dir / 'manager.json'
                    operator_json = step_dir / 'operator.json'
                    reflector_json = step_dir / 'reflector.json'
                    # manager
                    try:
                        if manager_json.exists():
                            mj = manager_json.read_text(encoding='utf-8')
                            import json
                            mjd = json.loads(mj)
                            sections = _parse_sections(mjd.get('response') or '')
                            data['manager'] = {
                                'thought': sections.get('thought', ''),
                                'plan': sections.get('description', ''),
                            }
                    except Exception:
                        pass
                    # operator
                    try:
                        if operator_json.exists():
                            oj = operator_json.read_text(encoding='utf-8')
                            import json
                            ojd = json.loads(oj)
                            sections = _parse_sections(ojd.get('response') or '')
                            data['operator'] = {
                                'thought': sections.get('thought', ''),
                                'action': sections.get('action', ''),
                                'description': sections.get('description', ''),
                            }
                    except Exception:
                        pass
                    # reflector + 图片
                    try:
                        imgs = []
                        if reflector_json.exists():
                            rj = reflector_json.read_text(encoding='utf-8')
                            import json
                            rjd = json.loads(rj)
                            sections = _parse_sections(rjd.get('response') or '')
                            data['reflector'] = {
                                'outcome': sections.get('outcome', ''),
                                'error_description': sections.get('error_description', ''),
                            }
                            imgs = _extract_images_from_messages(rjd.get('messages'))
                        # 标注前后
                        labeled = []
                        for i, url in enumerate(imgs[:2]):
                            labeled.append({
                                'label': ('前' if i == 0 else '后'),
                                'url': url
                            })
                        if labeled:
                            data['images'] = labeled
                    except Exception:
                        pass
                    steps.append(data)
                if steps:
                    socketio.emit('ai_chat_steps', { 'mid': mid, 'steps': steps })

            _emit_steps(mid, text)
        except Exception:
            pass
    except Exception as e:
        socketio.emit('ai_chat_reply', { 'mid': mid, 'text': f'执行出错：{str(e)}' })
    finally:
        try:
            AGENT_JOBS.pop(mid, None)
        except Exception:
            pass

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
        
        # 尝试连接设备
        print(f'Trying to connect to device: {device_id}')
        success, output = device_manager.adb_manager.connect_to_device(ip, port)
        if success:
            if device_manager.add_device(device_id):
                emit('device_list_update', device_manager.get_device_list())
                print(f'Device connected successfully: {device_id}')
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

@socketio.on('ai_chat_message')
def handle_ai_chat_message(data):
    try:
        mid = data.get('mid')
        text = (data.get('text') or '').strip()
        if not text:
            emit('ai_chat_reply', { 'mid': mid, 'text': '消息为空，请输入要执行的指令或问题。' })
            return
        # 准备可中止的任务
        stop_event = threading.Event()
        AGENT_JOBS[str(mid)] = {
            'stop_event': stop_event
        }
        socketio.start_background_task(run_agent_and_reply, mid, text, stop_event)
    except Exception as e:
        emit('ai_chat_reply', { 'mid': data.get('mid'), 'text': f'后端处理异常：{str(e)}' })

@socketio.on('ai_chat_stop')
def handle_ai_chat_stop(data):
    try:
        mid = str(data.get('mid'))
        job = AGENT_JOBS.get(mid)
        if not job:
            emit('ai_chat_stopped', { 'mid': mid, 'ok': False, 'msg': '未找到对应任务或已结束' })
            return
        job['stop_event'].set()
        emit('ai_chat_stopped', { 'mid': mid, 'ok': True, 'msg': '已发送停止信号' })
    except Exception as e:
        emit('ai_chat_stopped', { 'mid': data.get('mid'), 'ok': False, 'msg': f'停止异常：{str(e)}' })

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Web server for scrcpy')
    parser.add_argument('--video_bit_rate', default="1024000", help='scrcpy video bit rate')
    parser.add_argument('--port', type=int, default=5000, help='port to bind the web server to')
    args = parser.parse_args()
    video_bit_rate = args.video_bit_rate
    socketio.run(app, host='0.0.0.0', port=args.port)