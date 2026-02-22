import subprocess
import re
import time
import platform
import os
from typing import Optional, Tuple

class ADBManager:
    def __init__(self):
        self.adb_path = self._get_adb_path()
        self.current_device = None
        self.is_tcp_mode = False

    def _get_adb_path(self) -> str:
        """获取adb路径"""
        system = platform.system().lower()
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        if system == "windows":
            adb_path = os.path.join(current_dir, "adb", "windows", "adb.exe")
        elif system == "darwin":  # macOS
            adb_path = os.path.join(current_dir, "adb", "darwin", "adb")
        elif system == "linux":
            adb_path = os.path.join(current_dir, "adb", "linux", "adb")
        else:
            raise Exception(f"不支持的操作系统: {system}")
        
        return adb_path

    def _run_adb_command(self, command: list, device_id: str = None) -> Tuple[bool, str]:
        """运行adb命令并返回结果"""
        try:
            cmd = [self.adb_path]
            if device_id:
                cmd.extend(['-s', device_id])
            cmd.extend(command)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            return result.returncode == 0, result.stdout if result.returncode == 0 else result.stderr
        except Exception as e:
            return False, str(e)

    def get_devices(self) -> list:
        """获取已连接的设备列表"""
        success, output = self._run_adb_command(['devices'])
        if not success:
            return []
        
        devices = []
        for line in output.split('\n')[1:]:  # 跳过第一行 "List of devices attached"
            if line.strip():
                parts = line.split('\t')
                if len(parts) >= 2:
                    devices.append({
                        'id': parts[0],
                        'state': parts[1],
                        'is_tcp': ':' in parts[0]
                    })
        return devices

    def get_device_ip(self) -> Optional[str]:
        """获取设备IP地址"""
        success, output = self._run_adb_command(['shell', 'ip', 'route'])
        if not success:
            return None

        # 查找wlan0接口的IP地址
        pattern = r'src (\d+\.\d+\.\d+\.\d+)'
        match = re.search(pattern, output)
        if match:
            return match.group(1)
        return None

    def connect_to_device(self, ip: str, port: int = 5555):
        """通过TCP/IP连接设备，返回 (success, output)"""
        address = f"{ip}:{port}"
        success, output = self._run_adb_command(['connect', address])
        out_lower = (output or '').lower()
        if success and ('connected' in out_lower or 'already connected' in out_lower):
            self.current_device = address
            self.is_tcp_mode = True
            return True, output
        return False, output

    def disconnect_device(self, ip: str = None, port: int = 5555) -> bool:
        """断开TCP/IP连接"""
        if ip:
            address = f"{ip}:{port}"
            success, _ = self._run_adb_command(['disconnect', address])
        else:
            success, _ = self._run_adb_command(['disconnect'])
        
        if success:
            self.current_device = None
            self.is_tcp_mode = False
        return success

    def enable_tcp_mode(self) -> Tuple[bool, Optional[str]]:
        """启用设备的TCP/IP模式"""
        # 检查是否有USB设备连接
        devices = self.get_devices()
        usb_devices = [d for d in devices if not d['is_tcp']]
        if not usb_devices:
            return False, "没有找到通过USB连接的设备"

        # 获取设备IP地址
        ip = self.get_device_ip()
        if not ip:
            return False, "无法获取设备IP地址"

        # 启用TCP/IP模式
        success, output = self._run_adb_command(['tcpip', '5555'])
        if not success:
            return False, f"启用TCP/IP模式失败: {output}"

        # 等待服务重启
        time.sleep(1)

        # 尝试TCP/IP连接
        if self.connect_to_device(ip):
            return True, ip
        return False, "TCP/IP连接失败"

    def get_current_connection_info(self) -> dict:
        """获取当前连接信息"""
        return {
            'device': self.current_device,
            'is_tcp_mode': self.is_tcp_mode,
            'all_devices': self.get_devices()
        }

# 使用示例
if __name__ == '__main__':
    adb = ADBManager()
    print("已连接设备:", adb.get_devices())
    
    # 启用TCP/IP模式
    success, result = adb.enable_tcp_mode()
    if success:
        print(f"成功启用TCP/IP模式，设备IP: {result}")
    else:
        print(f"启用TCP/IP模式失败: {result}")