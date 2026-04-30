"""
文件共享Android客户端 (Kivy)
"""

import os
import socket
import threading
import time
from pathlib import Path
from typing import List, Dict, Optional

import requests
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ListProperty, ObjectProperty
from kivy.clock import Clock
from kivy.utils import platform

from protocol import DeviceInfo, UDPProtocol, MessageType, UDP_BROADCAST_PORT

class FileShareApp(App):
    title = '文件共享'

    devices = ListProperty([])
    files = ListProperty([])
    current_device = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.device_info = None
        self.upload_dir = Path("downloads")
        self.upload_dir.mkdir(exist_ok=True)
        self.udp_running = True
        self.udp_thread = None

    def build(self):
        """构建UI"""
        self.init_device_info()
        self.start_udp_service()

        # 简化UI，实际应用中需要更复杂的布局
        layout = BoxLayout(orientation='vertical')
        return layout

    def init_device_info(self):
        """初始化设备信息"""
        device_id = self._get_device_id()
        device_name = f"Android-{self._get_device_name()}"
        ip = self._get_local_ip()

        self.device_info = DeviceInfo(
            device_id=device_id,
            name=device_name,
            ip=ip,
            port=0  # Android端不运行服务器
        )
        self.device_info.platform = "Android"

    def _get_device_id(self) -> str:
        """获取设备ID"""
        if platform == 'android':
            try:
                from jnius import autoclass
                Context = autoclass('android.content.Context')
                Settings = autoclass('android.provider.Settings$Secure')
                context = autoclass('org.kivy.android.PythonActivity').mActivity
                return Settings.getString(
                    context.getContentResolver(),
                    Settings.ANDROID_ID
                )
            except:
                pass
        return "android-device-" + str(int(time.time()))

    def _get_device_name(self) -> str:
        """获取设备名称"""
        if platform == 'android':
            try:
                from jnius import autoclass
                Build = autoclass('android.os.Build')
                return Build.MODEL
            except:
                pass
        return "Android Device"

    def _get_local_ip(self) -> str:
        """获取本地IP"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "0.0.0.0"

    def start_udp_service(self):
        """启动UDP服务"""
        def udp_service():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)

            try:
                sock.bind(('', UDP_BROADCAST_PORT))
            except:
                print("Could not bind to broadcast port")
                return

            last_broadcast = time.time()

            while self.udp_running:
                try:
                    # 发送广播
                    if time.time() - last_broadcast >= 30:
                        message = UDPProtocol.create_broadcast_message(
                            self.device_info,
                            MessageType.DEVICE_ANNOUNCE
                        )
                        UDPProtocol.broadcast(message)
                        last_broadcast = time.time()

                    # 接收广播
                    try:
                        data, addr = sock.recvfrom(1024)
                        message = UDPProtocol.parse_message(data)

                        if message and message.get('type') == MessageType.DEVICE_ANNOUNCE:
                            device_data = message.get('data', {})
                            device_info = DeviceInfo.from_dict(device_data)

                            # 不添加自己
                            if device_info.device_id != self.device_info.device_id:
                                self.update_devices(device_info)
                    except socket.timeout:
                        continue

                except Exception as e:
                    print(f"UDP error: {e}")
                    time.sleep(1)

            sock.close()

        self.udp_thread = threading.Thread(target=udp_service, daemon=True)
        self.udp_thread.start()

    def update_devices(self, device_info: DeviceInfo):
        """更新设备列表"""
        def update(dt):
            found = False
            for i, dev in enumerate(self.devices):
                if dev['device_id'] == device_info.device_id:
                    self.devices[i] = device_info.to_dict()
                    found = True
                    break
            if not found:
                self.devices.append(device_info.to_dict())

        Clock.schedule_once(update, 0)

    def connect_to_device(self, device: Dict):
        """连接到设备"""
        self.current_device = device
        self.refresh_files()

    def refresh_files(self):
        """刷新文件列表"""
        if not self.current_device:
            return

        def fetch_files():
            try:
                url = f"http://{self.current_device['ip']}:{self.current_device['port']}/api/files"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data['status'] == 'success':
                        files = data['data']['files']
                        Clock.schedule_once(lambda dt: self.update_files(files), 0)
            except Exception as e:
                print(f"Error fetching files: {e}")

        threading.Thread(target=fetch_files, daemon=True).start()

    def update_files(self, files: List[Dict]):
        """更新文件列表"""
        self.files = files

    def download_file(self, filename: str):
        """下载文件"""
        if not self.current_device:
            return

        def do_download():
            try:
                url = f"http://{self.current_device['ip']}:{self.current_device['port']}/api/files/{filename}"
                response = requests.get(url, timeout=30, stream=True)
                if response.status_code == 200:
                    file_path = self.upload_dir / filename
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    print(f"Downloaded: {file_path}")
                    Clock.schedule_once(lambda dt: self.on_download_complete(filename), 0)
            except Exception as e:
                print(f"Download error: {e}")

        threading.Thread(target=do_download, daemon=True).start()

    def on_download_complete(self, filename: str):
        """下载完成回调"""
        print(f"File downloaded: {filename}")

    def upload_file(self, file_path: str):
        """上传文件"""
        if not self.current_device:
            return

        def do_upload():
            try:
                url = f"http://{self.current_device['ip']}:{self.current_device['port']}/api/files"
                with open(file_path, 'rb') as f:
                    files = {'file': (os.path.basename(file_path), f)}
                    response = requests.post(url, files=files, timeout=30)
                if response.status_code == 201:
                    data = response.json()
                    print(f"Uploaded: {data}")
                    Clock.schedule_once(lambda dt: self.refresh_files(), 0)
            except Exception as e:
                print(f"Upload error: {e}")

        threading.Thread(target=do_upload, daemon=True).start()

    def on_stop(self):
        """应用停止"""
        self.udp_running = False
        if self.udp_thread and self.udp_thread.is_alive():
            self.udp_thread.join(timeout=2)

if __name__ == '__main__':
    FileShareApp().run()
