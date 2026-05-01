"""
文件共享Android客户端 (Kivy)
重写版 - 修复黑屏问题，添加全面错误处理
"""

import os
import sys
import socket
import threading
import time
import traceback
from pathlib import Path

# 确保当前目录在 sys.path 中（Android 上需要）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import requests
except ImportError:
    requests = None

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.properties import ListProperty, ObjectProperty, StringProperty
from kivy.clock import Clock
from kivy.utils import platform
from kivy.logger import Logger

# 协议常量（内联，避免导入失败）
UDP_BROADCAST_PORT = 5555
HTTP_PORT = 8080


class FileShareApp(App):
    title = '文件共享'
    status_text = StringProperty('正在初始化...')
    devices = ListProperty([])
    files = ListProperty([])
    current_device = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.device_info = None
        self.upload_dir = None
        self.udp_running = False
        self.udp_thread = None
        self.device_id = "unknown"
        self.device_name = "Android Device"
        self.local_ip = "0.0.0.0"

    def build(self):
        """构建UI - 即使初始化失败也要显示基本界面"""
        try:
            # 先创建UI，再初始化功能
            root = self._build_ui()
            # 延迟初始化，确保UI先显示
            Clock.schedule_once(self._delayed_init, 0.5)
            return root
        except Exception as e:
            Logger.error(f"FileShare: build() failed: {e}")
            Logger.error(traceback.format_exc())
            # 返回一个基本的错误界面
            return self._build_error_ui(str(e))

    def _build_ui(self):
        """构建主界面"""
        root = BoxLayout(orientation='vertical', padding=10, spacing=8)

        # 标题栏
        title_bar = BoxLayout(size_hint_y=0.08)
        title_bar.add_widget(Label(
            text='[b]文件共享[/b]',
            font_size=24,
            markup=True
        ))
        root.add_widget(title_bar)

        # 状态栏
        self.status_label = Label(
            text=self.status_text,
            size_hint_y=0.05,
            color=(0.7, 0.7, 0.7, 1),
            text_size=(None, None),
            halign='center'
        )
        root.add_widget(self.status_label)
        self.bind(status_text=self._update_status)

        # 设备列表
        root.add_widget(Label(
            text='[b]发现的设备:[/b]',
            size_hint_y=0.05,
            markup=True
        ))
        self.device_scroll = ScrollView(size_hint_y=0.25)
        self.device_box = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            spacing=3,
            padding=[0, 5]
        )
        self.device_box.bind(minimum_height=self.device_box.setter('height'))
        self.device_scroll.add_widget(self.device_box)
        root.add_widget(self.device_scroll)

        # 手动输入IP
        ip_box = BoxLayout(size_hint_y=0.06, spacing=5)
        ip_box.add_widget(Label(text='手动连接:', size_hint_x=0.3))
        self.ip_input = TextInput(
            hint_text='输入IP地址:端口',
            multiline=False,
            size_hint_x=0.5
        )
        ip_box.add_widget(self.ip_input)
        btn_connect = Button(text='连接', size_hint_x=0.2)
        btn_connect.bind(on_press=self._manual_connect)
        ip_box.add_widget(btn_connect)
        root.add_widget(ip_box)

        # 文件列表
        root.add_widget(Label(
            text='[b]远端文件:[/b]',
            size_hint_y=0.05,
            markup=True
        ))
        self.file_scroll = ScrollView(size_hint_y=0.3)
        self.file_box = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            spacing=3,
            padding=[0, 5]
        )
        self.file_box.bind(minimum_height=self.file_box.setter('height'))
        self.file_scroll.add_widget(self.file_box)
        root.add_widget(self.file_scroll)

        # 操作按钮
        btn_box = BoxLayout(size_hint_y=0.08, spacing=5)
        btn_scan = Button(text='扫描设备')
        btn_scan.bind(on_press=self._scan_devices)
        btn_refresh = Button(text='刷新文件')
        btn_refresh.bind(on_press=self._refresh_files_btn)
        btn_upload = Button(text='上传文件')
        btn_upload.bind(on_press=self._upload_file_btn)
        btn_box.add_widget(btn_scan)
        btn_box.add_widget(btn_refresh)
        btn_box.add_widget(btn_upload)
        root.add_widget(btn_box)

        # 初始化设备列表UI
        self._update_device_ui()

        return root

    def _build_error_ui(self, error_msg):
        """构建错误界面"""
        root = BoxLayout(orientation='vertical', padding=20, spacing=10)
        root.add_widget(Label(
            text='[b]文件共享 - 启动错误[/b]',
            font_size=20,
            markup=True,
            size_hint_y=0.2
        ))
        root.add_widget(Label(
            text=f'错误信息:\n{error_msg}',
            size_hint_y=0.4,
            text_size=(400, None),
            halign='center'
        ))
        btn = Button(text='重试', size_hint_y=0.1)
        btn.bind(on_press=lambda x: self._retry())
        root.add_widget(btn)
        return root

    def _retry(self):
        """重试初始化"""
        self.root.clear_widgets()
        new_root = self._build_ui()
        self.root.add_widget(new_root)
        Clock.schedule_once(self._delayed_init, 0.5)

    def _delayed_init(self, dt):
        """延迟初始化 - UI显示后再执行"""
        try:
            self._init_device_info()
            self._init_upload_dir()
            self._start_udp_service()
            self.status_text = '初始化完成，点击扫描设备'
            Logger.info("FileShare: 初始化成功")
        except Exception as e:
            Logger.error(f"FileShare: 初始化失败: {e}")
            Logger.error(traceback.format_exc())
            self.status_text = f'初始化部分失败: {e}'

    def _init_device_info(self):
        """初始化设备信息"""
        try:
            self.device_id = self._get_device_id()
            self.device_name = f"Android-{self._get_device_name()}"
            self.local_ip = self._get_local_ip()
            Logger.info(f"FileShare: 设备 {self.device_name}, IP: {self.local_ip}")
        except Exception as e:
            Logger.warning(f"FileShare: 设备信息获取失败: {e}")

    def _init_upload_dir(self):
        """初始化上传目录"""
        try:
            if platform == 'android':
                from android.storage import app_storage_path
                base = app_storage_path()
            else:
                base = os.getcwd()
            self.upload_dir = Path(base) / "downloads"
            self.upload_dir.mkdir(parents=True, exist_ok=True)
            Logger.info(f"FileShare: 上传目录 {self.upload_dir}")
        except Exception as e:
            Logger.warning(f"FileShare: 创建上传目录失败: {e}")
            self.upload_dir = Path("downloads")
            self.upload_dir.mkdir(exist_ok=True)

    def _get_device_id(self) -> str:
        if platform == 'android':
            try:
                from jnius import autoclass
                Settings = autoclass('android.provider.Settings$Secure')
                context = autoclass('org.kivy.android.PythonActivity').mActivity
                return Settings.getString(context.getContentResolver(), Settings.ANDROID_ID)
            except Exception as e:
                Logger.warning(f"FileShare: 获取设备ID失败: {e}")
        return f"android-{int(time.time())}"

    def _get_device_name(self) -> str:
        if platform == 'android':
            try:
                from jnius import autoclass
                Build = autoclass('android.os.Build')
                return Build.MODEL
            except Exception as e:
                Logger.warning(f"FileShare: 获取设备名失败: {e}")
        return "Android Device"

    def _get_local_ip(self) -> str:
        """获取局域网IP（优先WiFi，排除VPN）"""
        if platform == 'android':
            try:
                from jnius import autoclass
                WifiManager = autoclass('android.net.wifi.WifiManager')
                context = autoclass('org.kivy.android.PythonActivity').mActivity
                wm = context.getSystemService(context.WIFI_SERVICE)
                if wm and wm.isWifiEnabled():
                    info = wm.getConnectionInfo()
                    ip = info.getIpAddress()
                    if ip != 0:
                        return f'{ip & 0xff}.{(ip >> 8) & 0xff}.{(ip >> 16) & 0xff}.{(ip >> 24) & 0xff}'
            except Exception as e:
                Logger.warning(f'FileShare: WiFi IP获取失败: {e}')

        # 后备: 通过socket获取（可能选到VPN）
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            Logger.warning(f'FileShare: 获取IP失败: {e}')
            return '0.0.0.0'

    def _start_udp_service(self):
        """启动UDP广播服务"""
        self.udp_running = True

        def udp_service():
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.settimeout(1.0)
                try:
                    sock.bind(('', UDP_BROADCAST_PORT))
                    Logger.info(f"FileShare: UDP绑定端口 {UDP_BROADCAST_PORT}")
                except Exception as e:
                    Logger.warning(f"FileShare: UDP端口绑定失败: {e}")
                    # 尝试其他端口
                    try:
                        sock.bind(('', 0))
                        Logger.info("FileShare: UDP绑定随机端口")
                    except:
                        return

                last_broadcast = time.time()
                while self.udp_running:
                    try:
                        if time.time() - last_broadcast >= 10:
                            self._broadcast_device()
                            last_broadcast = time.time()
                        try:
                            data, addr = sock.recvfrom(1024)
                            self._handle_udp_message(data)
                        except socket.timeout:
                            continue
                    except Exception as e:
                        Logger.warning(f"FileShare: UDP循环错误: {e}")
                        time.sleep(1)
            except Exception as e:
                Logger.error(f"FileShare: UDP服务启动失败: {e}")
            finally:
                if sock:
                    try:
                        sock.close()
                    except:
                        pass

        self.udp_thread = threading.Thread(target=udp_service, daemon=True)
        self.udp_thread.start()

    def _get_broadcast_addr(self) -> str:
        """获取局域网广播地址"""
        if self.local_ip and self.local_ip != '0.0.0.0':
            # 从IP推算广播地址（假设/24）
            parts = self.local_ip.split('.')
            if len(parts) == 4:
                return f'{parts[0]}.{parts[1]}.{parts[2]}.255'
        return '<broadcast>'

    def _broadcast_device(self):
        """广播设备信息"""
        try:
            import json
            message = {
                'version': '1.0',
                'type': 'announce',
                'data': {
                    'device_id': self.device_id,
                    'name': self.device_name,
                    'ip': self.local_ip,
                    'port': HTTP_PORT,
                    'platform': 'Android'
                },
                'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S')
            }
            bcast_addr = self._get_broadcast_addr()
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(json.dumps(message).encode('utf-8'), (bcast_addr, UDP_BROADCAST_PORT))
            sock.close()
        except Exception as e:
            Logger.warning(f'FileShare: 广播失败: {e}')

    def _handle_udp_message(self, data):
        """处理UDP消息"""
        try:
            import json
            msg = json.loads(data.decode('utf-8'))
            if msg.get('type') == 'announce':
                dev = msg.get('data', {})
                if dev.get('device_id') != self.device_id:
                    Clock.schedule_once(lambda dt: self._add_device(dev), 0)
        except Exception as e:
            Logger.warning(f"FileShare: UDP消息处理失败: {e}")

    def _add_device(self, device):
        """添加设备到列表"""
        try:
            for i, dev in enumerate(self.devices):
                if dev.get('device_id') == device.get('device_id'):
                    self.devices[i] = device
                    return
            self.devices.append(device)
            self.status_text = f'发现设备: {device.get("name", "未知")}'
        except Exception as e:
            Logger.warning(f"FileShare: 添加设备失败: {e}")

    def _update_status(self, *args):
        """更新状态栏"""
        if hasattr(self, 'status_label'):
            self.status_label.text = self.status_text

    def _update_device_ui(self, *args):
        """更新设备列表UI"""
        if not hasattr(self, 'device_box'):
            return
        self.device_box.clear_widgets()
        if not self.devices:
            self.device_box.add_widget(Label(
                text='暂无设备，请点击扫描',
                size_hint_y=None,
                height=40
            ))
            return
        for dev in self.devices:
            name = dev.get('name', '未知设备')
            ip = dev.get('ip', '未知IP')
            btn = Button(
                text=f"{name} ({ip})",
                size_hint_y=None,
                height=45
            )
            btn.bind(on_press=lambda b, d=dev: self._connect_to_device(d))
            self.device_box.add_widget(btn)

    def _connect_to_device(self, device):
        """连接到设备"""
        self.current_device = device
        self.status_text = f'已连接: {device.get("name", "未知")}，正在获取文件...'
        self._refresh_files()

    def _refresh_files(self):
        """刷新文件列表"""
        if not self.current_device:
            self.status_text = '请先选择一个设备'
            return

        if not requests:
            self.status_text = 'requests 库未安装'
            return

        def fetch():
            try:
                ip = self.current_device.get('ip', '')
                port = self.current_device.get('port', HTTP_PORT)
                url = f"http://{ip}:{port}/api/files"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('status') == 'success':
                        file_list = data.get('data', {}).get('files', [])
                        Clock.schedule_once(lambda dt: self._set_files(file_list), 0)
                    else:
                        Clock.schedule_once(lambda dt: self._set_status('获取文件失败'), 0)
                else:
                    Clock.schedule_once(lambda dt: self._set_status(f'服务器返回 {resp.status_code}'), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._set_status(f'连接失败: {e}'), 0)

        threading.Thread(target=fetch, daemon=True).start()

    def _set_files(self, file_list):
        """设置文件列表"""
        self.files = file_list
        self._update_file_ui()
        self.status_text = f'已连接: {self.current_device.get("name", "未知")}，共 {len(file_list)} 个文件'

    def _set_status(self, text):
        """设置状态文本"""
        self.status_text = text

    def _update_file_ui(self, *args):
        """更新文件列表UI"""
        if not hasattr(self, 'file_box'):
            return
        self.file_box.clear_widgets()
        if not self.files:
            self.file_box.add_widget(Label(
                text='暂无文件',
                size_hint_y=None,
                height=40
            ))
            return
        for f in self.files:
            name = f.get('name', '未知')
            size = f.get('size', 0)
            size_kb = size / 1024
            btn = Button(
                text=f"{name} ({size_kb:.1f}KB)",
                size_hint_y=None,
                height=45
            )
            btn.bind(on_press=lambda b, n=name: self._download_file(n))
            self.file_box.add_widget(btn)

    def _scan_devices(self, *args):
        """扫描设备"""
        self.status_text = '正在扫描...'
        self._broadcast_device()
        Clock.schedule_once(lambda dt: self._set_status('扫描已发送，等待设备响应...'), 0)

    def _refresh_files_btn(self, *args):
        """刷新文件按钮"""
        self._refresh_files()

    def _manual_connect(self, *args):
        """手动连接"""
        addr = self.ip_input.text.strip()
        if not addr:
            self.status_text = '请输入IP地址'
            return

        # 解析 IP:端口
        if ':' in addr:
            ip, port = addr.rsplit(':', 1)
            try:
                port = int(port)
            except:
                port = HTTP_PORT
        else:
            ip = addr
            port = HTTP_PORT

        device = {
            'device_id': f'manual-{ip}',
            'name': f'手动设备 ({ip})',
            'ip': ip,
            'port': port,
            'platform': 'Unknown'
        }
        self._connect_to_device(device)

    def _download_file(self, filename):
        """下载文件"""
        if not self.current_device:
            return

        if not requests:
            self.status_text = 'requests 库未安装'
            return

        def do_download():
            try:
                ip = self.current_device.get('ip', '')
                port = self.current_device.get('port', HTTP_PORT)
                url = f"http://{ip}:{port}/api/files/{filename}"
                resp = requests.get(url, timeout=30, stream=True)
                if resp.status_code == 200:
                    path = self.upload_dir / filename
                    with open(path, 'wb') as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
                    Clock.schedule_once(lambda dt: self._set_status(f'下载完成: {filename}'), 0)
                else:
                    Clock.schedule_once(lambda dt: self._set_status(f'下载失败: {resp.status_code}'), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._set_status(f'下载错误: {e}'), 0)

        self.status_text = f'正在下载: {filename}...'
        threading.Thread(target=do_download, daemon=True).start()

    def _upload_file_btn(self, *args):
        """上传文件按钮"""
        if not self.current_device:
            self.status_text = '请先选择一个设备'
            return

        if not self.upload_dir:
            self.status_text = '上传目录未初始化'
            return

        files = list(self.upload_dir.iterdir()) if self.upload_dir.exists() else []
        if not files:
            self.status_text = '没有可上传的文件'
            return

        if not requests:
            self.status_text = 'requests 库未安装'
            return

        def do_upload(file_path):
            try:
                ip = self.current_device.get('ip', '')
                port = self.current_device.get('port', HTTP_PORT)
                url = f"http://{ip}:{port}/api/files"
                with open(file_path, 'rb') as f:
                    resp = requests.post(url, files={'file': (file_path.name, f)}, timeout=30)
                if resp.status_code == 201:
                    Clock.schedule_once(lambda dt: self._set_status(f'上传成功: {file_path.name}'), 0)
                    self._refresh_files()
                else:
                    Clock.schedule_once(lambda dt: self._set_status(f'上传失败: {resp.status_code}'), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._set_status(f'上传错误: {e}'), 0)

        self.status_text = f'正在上传: {files[0].name}...'
        threading.Thread(target=do_upload, args=(files[0],), daemon=True).start()

    def on_stop(self):
        """应用停止时清理"""
        self.udp_running = False
        if self.udp_thread and self.udp_thread.is_alive():
            self.udp_thread.join(timeout=2)


if __name__ == '__main__':
    try:
        FileShareApp().run()
    except Exception as e:
        Logger.error(f"FileShare: 应用崩溃: {e}")
        Logger.error(traceback.format_exc())
        # 尝试显示错误
        print(f"FATAL ERROR: {e}")
        print(traceback.format_exc())
