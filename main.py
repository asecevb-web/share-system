"""
文件共享Android客户端 (Kivy)
"""

import os
import socket
import threading
import time
from pathlib import Path
from typing import List, Dict

import requests
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.properties import ListProperty, ObjectProperty, StringProperty
from kivy.clock import Clock
from kivy.utils import platform

from protocol import DeviceInfo, UDPProtocol, MessageType, UDP_BROADCAST_PORT


class FileShareApp(App):
    title = '文件共享'
    status_text = StringProperty('等待扫描设备...')
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
        self.init_device_info()
        self.start_udp_service()

        root = BoxLayout(orientation='vertical', padding=10, spacing=5)

        # 标题栏
        title_bar = BoxLayout(size_hint_y=0.08)
        title_bar.add_widget(Label(text='文件共享', font_size=24, bold=True))
        root.add_widget(title_bar)

        # 状态栏
        self.status_label = Label(text=self.status_text, size_hint_y=0.05, color=(0.7, 0.7, 0.7, 1))
        root.add_widget(self.status_label)

        # 设备列表
        root.add_widget(Label(text='发现的设备:', size_hint_y=0.05, bold=True))
        self.device_scroll = ScrollView(size_hint_y=0.3)
        self.device_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=3)
        self.device_box.bind(minimum_height=self.device_box.setter('height'))
        self.device_scroll.add_widget(self.device_box)
        root.add_widget(self.device_scroll)

        # 文件列表
        root.add_widget(Label(text='远端文件:', size_hint_y=0.05, bold=True))
        self.file_scroll = ScrollView(size_hint_y=0.3)
        self.file_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=3)
        self.file_box.bind(minimum_height=self.file_box.setter('height'))
        self.file_scroll.add_widget(self.file_box)
        root.add_widget(self.file_scroll)

        # 操作按钮
        btn_box = BoxLayout(size_hint_y=0.1, spacing=5)
        btn_scan = Button(text='扫描设备')
        btn_scan.bind(on_press=self.scan_devices)
        btn_refresh = Button(text='刷新文件')
        btn_refresh.bind(on_press=self.refresh_files_btn)
        btn_upload = Button(text='上传文件')
        btn_upload.bind(on_press=self.upload_file_btn)
        btn_box.add_widget(btn_scan)
        btn_box.add_widget(btn_refresh)
        btn_box.add_widget(btn_upload)
        root.add_widget(btn_box)

        self.bind(status_text=self.status_label.setter('text'))
        self.bind(devices=self.update_device_ui)
        self.bind(files=self.update_file_ui)

        return root

    def init_device_info(self):
        device_id = self._get_device_id()
        device_name = f"Android-{self._get_device_name()}"
        ip = self._get_local_ip()
        self.device_info = DeviceInfo(
            device_id=device_id,
            name=device_name,
            ip=ip,
            port=0
        )
        self.device_info.platform = "Android"

    def _get_device_id(self) -> str:
        if platform == 'android':
            try:
                from jnius import autoclass
                Settings = autoclass('android.provider.Settings$Secure')
                context = autoclass('org.kivy.android.PythonActivity').mActivity
                return Settings.getString(context.getContentResolver(), Settings.ANDROID_ID)
            except:
                pass
        return "android-device-" + str(int(time.time()))

    def _get_device_name(self) -> str:
        if platform == 'android':
            try:
                from jnius import autoclass
                Build = autoclass('android.os.Build')
                return Build.MODEL
            except:
                pass
        return "Android Device"

    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "0.0.0.0"

    def start_udp_service(self):
        def udp_service():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)
            try:
                sock.bind(('', UDP_BROADCAST_PORT))
            except:
                return

            last_broadcast = time.time()
            while self.udp_running:
                try:
                    if time.time() - last_broadcast >= 10:
                        msg = UDPProtocol.create_broadcast_message(self.device_info, MessageType.DEVICE_ANNOUNCE)
                        UDPProtocol.broadcast(msg)
                        last_broadcast = time.time()
                    try:
                        data, addr = sock.recvfrom(1024)
                        msg = UDPProtocol.parse_message(data)
                        if msg and msg.get('type') == MessageType.DEVICE_ANNOUNCE:
                            dev = DeviceInfo.from_dict(msg.get('data', {}))
                            if dev.device_id != self.device_info.device_id:
                                self.update_devices(dev)
                    except socket.timeout:
                        continue
                except Exception as e:
                    time.sleep(1)
            sock.close()

        self.udp_thread = threading.Thread(target=udp_service, daemon=True)
        self.udp_thread.start()

    def update_devices(self, device_info):
        def update(dt):
            found = False
            for i, dev in enumerate(self.devices):
                if dev['device_id'] == device_info.device_id:
                    self.devices[i] = device_info.to_dict()
                    found = True
                    break
            if not found:
                self.devices.append(device_info.to_dict())
                self.status_text = f'发现设备: {device_info.name}'
        Clock.schedule_once(update, 0)

    def update_device_ui(self, *args):
        self.device_box.clear_widgets()
        if not self.devices:
            self.device_box.add_widget(Label(text='暂无设备，请点击扫描', size_hint_y=None, height=40))
            return
        for dev in self.devices:
            btn = Button(
                text=f"{dev['name']} ({dev['ip']})",
                size_hint_y=None, height=45
            )
            btn.bind(on_press=lambda b, d=dev: self.connect_to_device(d))
            self.device_box.add_widget(btn)

    def connect_to_device(self, device):
        self.current_device = device
        self.status_text = f'已连接: {device["name"]}，正在获取文件...'
        self.refresh_files()

    def refresh_files(self):
        if not self.current_device:
            self.status_text = '请先选择一个设备'
            return

        def fetch():
            try:
                url = f"http://{self.current_device['ip']}:{self.current_device['port']}/api/files"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data['status'] == 'success':
                        files = data['data']['files']
                        Clock.schedule_once(lambda dt: self.set_files(files), 0)
                    else:
                        Clock.schedule_once(lambda dt: setattr(self, 'status_text', '获取文件失败'), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self, 'status_text', f'连接失败: {e}'), 0)

        threading.Thread(target=fetch, daemon=True).start()

    def set_files(self, files):
        self.files = files
        self.status_text = f'已连接: {self.current_device["name"]}，共 {len(files)} 个文件'

    def update_file_ui(self, *args):
        self.file_box.clear_widgets()
        if not self.files:
            self.file_box.add_widget(Label(text='暂无文件', size_hint_y=None, height=40))
            return
        for f in self.files:
            size_kb = f['size'] / 1024
            btn = Button(
                text=f"{f['name']} ({size_kb:.1f}KB)",
                size_hint_y=None, height=45
            )
            btn.bind(on_press=lambda b, name=f['name']: self.download_file(name))
            self.file_box.add_widget(btn)

    def scan_devices(self, *args):
        self.status_text = '正在扫描...'
        msg = UDPProtocol.create_broadcast_message(self.device_info, MessageType.DEVICE_ANNOUNCE)
        UDPProtocol.broadcast(msg)
        Clock.schedule_once(lambda dt: setattr(self, 'status_text', '扫描已发送，等待设备响应...'), 0)

    def refresh_files_btn(self, *args):
        self.refresh_files()

    def download_file(self, filename):
        if not self.current_device:
            return

        def do_download():
            try:
                url = f"http://{self.current_device['ip']}:{self.current_device['port']}/api/files/{filename}"
                resp = requests.get(url, timeout=30, stream=True)
                if resp.status_code == 200:
                    path = self.upload_dir / filename
                    with open(path, 'wb') as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
                    Clock.schedule_once(lambda dt: setattr(self, 'status_text', f'下载完成: {filename}'), 0)
                else:
                    Clock.schedule_once(lambda dt: setattr(self, 'status_text', f'下载失败: {resp.status_code}'), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self, 'status_text', f'下载错误: {e}'), 0)

        self.status_text = f'正在下载: {filename}...'
        threading.Thread(target=do_download, daemon=True).start()

    def upload_file_btn(self, *args):
        if not self.current_device:
            self.status_text = '请先选择一个设备'
            return

        # 简单实现：上传 downloads 目录下的所有文件
        files = list(self.upload_dir.iterdir())
        if not files:
            self.status_text = '没有可上传的文件'
            return

        def do_upload(file_path):
            try:
                url = f"http://{self.current_device['ip']}:{self.current_device['port']}/api/files"
                with open(file_path, 'rb') as f:
                    resp = requests.post(url, files={'file': (file_path.name, f)}, timeout=30)
                if resp.status_code == 201:
                    Clock.schedule_once(lambda dt: setattr(self, 'status_text', f'上传成功: {file_path.name}'), 0)
                    self.refresh_files()
                else:
                    Clock.schedule_once(lambda dt: setattr(self, 'status_text', f'上传失败'), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self, 'status_text', f'上传错误: {e}'), 0)

        self.status_text = f'正在上传: {files[0].name}...'
        threading.Thread(target=do_upload, args=(files[0],), daemon=True).start()

    def on_stop(self):
        self.udp_running = False
        if self.udp_thread and self.udp_thread.is_alive():
            self.udp_thread.join(timeout=2)


if __name__ == '__main__':
    FileShareApp().run()
