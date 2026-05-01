"""
文件共享 Android 客户端 (Kivy)
v0.4 - 修复字体/闪退/添加语言选择
"""

import os
import sys
import json
import socket
import threading
import time
import traceback
from pathlib import Path

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
from kivy.uix.spinner import Spinner
from kivy.properties import ListProperty, ObjectProperty, StringProperty
from kivy.clock import Clock
from kivy.utils import platform
from kivy.logger import Logger
from kivy.core.text import LabelBase

UDP_BROADCAST_PORT = 5555
HTTP_PORT = 8080

# ========== 国际化 ==========
LANG = {
    'zh': {
        'title': '文件共享',
        'status_init': '正在初始化...',
        'status_ready': '初始化完成，点击扫描设备',
        'status_scanning': '正在扫描...',
        'status_scan_sent': '扫描已发送，等待设备响应...',
        'status_connected': '已连接: {}，正在获取文件...',
        'status_files': '已连接: {}，共 {} 个文件',
        'status_no_device': '请先选择一个设备',
        'status_no_file': '没有可上传的文件',
        'status_downloading': '正在下载: {}...',
        'status_uploading': '正在上传: {}...',
        'status_download_done': '下载完成: {}',
        'status_upload_done': '上传成功: {}',
        'status_download_fail': '下载失败: {}',
        'status_upload_fail': '上传失败: {}',
        'status_connect_fail': '连接失败: {}',
        'status_enter_ip': '请输入IP地址',
        'status_init_fail': '初始化部分失败: {}',
        'label_devices': '发现的设备:',
        'label_files': '远端文件:',
        'label_manual': '手动连接:',
        'label_no_device': '暂无设备，请点击扫描',
        'label_no_file': '暂无文件',
        'label_lang': '语言:',
        'hint_ip': 'IP地址:端口',
        'btn_scan': '扫描设备',
        'btn_refresh': '刷新文件',
        'btn_upload': '上传文件',
        'btn_connect': '连接',
        'btn_retry': '重试',
        'error_title': '文件共享 - 启动错误',
        'error_msg': '错误信息:\n{}',
    },
    'en': {
        'title': 'File Share',
        'status_init': 'Initializing...',
        'status_ready': 'Ready, tap Scan to find devices',
        'status_scanning': 'Scanning...',
        'status_scan_sent': 'Scan sent, waiting for devices...',
        'status_connected': 'Connected: {}, loading files...',
        'status_files': 'Connected: {}, {} files',
        'status_no_device': 'Select a device first',
        'status_no_file': 'No files to upload',
        'status_downloading': 'Downloading: {}...',
        'status_uploading': 'Uploading: {}...',
        'status_download_done': 'Downloaded: {}',
        'status_upload_done': 'Uploaded: {}',
        'status_download_fail': 'Download failed: {}',
        'status_upload_fail': 'Upload failed: {}',
        'status_connect_fail': 'Connection failed: {}',
        'status_enter_ip': 'Enter IP address',
        'status_init_fail': 'Init partially failed: {}',
        'label_devices': 'Devices Found:',
        'label_files': 'Remote Files:',
        'label_manual': 'Manual Connect:',
        'label_no_device': 'No devices, tap Scan',
        'label_no_file': 'No files',
        'label_lang': 'Lang:',
        'hint_ip': 'IP:Port',
        'btn_scan': 'Scan',
        'btn_refresh': 'Refresh',
        'btn_upload': 'Upload',
        'btn_connect': 'Connect',
        'btn_retry': 'Retry',
        'error_title': 'File Share - Error',
        'error_msg': 'Error:\n{}',
    }
}

current_lang = 'zh'


def t(key, *args):
    """翻译函数"""
    text = LANG.get(current_lang, LANG['zh']).get(key, key)
    if args:
        return text.format(*args)
    return text


def get_font_name():
    """获取支持中文的字体名称"""
    if platform == 'android':
        # Android 系统中文字体
        font_paths = [
            '/system/fonts/NotoSansCJK-Regular.ttc',
            '/system/fonts/NotoSansSC-Regular.otf',
            '/system/fonts/DroidSansFallback.ttf',
            '/system/fonts/NotoSansCJK-Regular.otf',
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                return fp
    return None


def register_fonts():
    """注册中文字体"""
    font_path = get_font_name()
    if font_path:
        try:
            LabelBase.register(name='CJK', fn_regular=font_path)
            Logger.info(f'FileShare: 注册字体 {font_path}')
            return 'CJK'
        except Exception as e:
            Logger.warning(f'FileShare: 字体注册失败: {e}')
    return None


# 全局字体
FONT_NAME = register_fonts()


def make_label(text='', font_size=16, **kwargs):
    """创建支持中文的 Label"""
    kw = {'text': text, 'font_size': font_size}
    if FONT_NAME:
        kw['font_name'] = FONT_NAME
    kw.update(kwargs)
    return Label(**kw)


def make_button(text='', font_size=16, **kwargs):
    """创建支持中文的 Button"""
    kw = {'text': text, 'font_size': font_size}
    if FONT_NAME:
        kw['font_name'] = FONT_NAME
    kw.update(kwargs)
    return Button(**kw)


def make_textinput(hint_text='', multiline=False, **kwargs):
    """创建 TextInput（Android 兼容）"""
    kw = {
        'hint_text': hint_text,
        'multiline': multiline,
        'write_tab': False,
    }
    if FONT_NAME:
        kw['font_name'] = FONT_NAME
    kw.update(kwargs)
    return TextInput(**kw)


class FileShareApp(App):
    title = t('title')
    status_text = StringProperty(t('status_init'))
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
        self.lang_spinner = None

    def build(self):
        try:
            root = self._build_ui()
            Clock.schedule_once(self._delayed_init, 0.5)
            return root
        except Exception as e:
            Logger.error(f'FileShare: build() failed: {e}')
            Logger.error(traceback.format_exc())
            return self._build_error_ui(str(e))

    def _build_ui(self):
        root = BoxLayout(orientation='vertical', padding=10, spacing=8)

        # 标题栏 + 语言选择
        top_bar = BoxLayout(size_hint_y=0.08)
        top_bar.add_widget(make_label(text=t('title'), font_size=24, bold=True))

        # 语言选择
        lang_box = BoxLayout(size_hint_x=0.25, spacing=2)
        lang_box.add_widget(make_label(text=t('label_lang'), font_size=12, size_hint_x=0.4))
        self.lang_spinner = Spinner(
            text='中文' if current_lang == 'zh' else 'English',
            values=('中文', 'English'),
            size_hint_x=0.6,
            font_name=FONT_NAME if FONT_NAME else 'Roboto',
            font_size=14,
        )
        self.lang_spinner.bind(text=self._on_lang_change)
        lang_box.add_widget(self.lang_spinner)
        top_bar.add_widget(lang_box)
        root.add_widget(top_bar)

        # 状态栏
        self.status_label = make_label(
            text=self.status_text,
            font_size=14,
            size_hint_y=0.05,
            color=(0.7, 0.7, 0.7, 1)
        )
        root.add_widget(self.status_label)
        self.bind(status_text=self._update_status)

        # 设备列表
        root.add_widget(make_label(text=t('label_devices'), font_size=14, size_hint_y=0.05, bold=True))
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

        # 手动输入IP（用按钮弹出对话框代替直接输入，避免键盘闪退）
        ip_box = BoxLayout(size_hint_y=0.06, spacing=5)
        ip_box.add_widget(make_label(text=t('label_manual'), font_size=14, size_hint_x=0.3))
        self.ip_display = make_label(
            text='',
            font_size=14,
            size_hint_x=0.5,
            color=(0.5, 0.8, 1, 1)
        )
        ip_box.add_widget(self.ip_display)
        btn_connect = make_button(text=t('btn_connect'), font_size=14, size_hint_x=0.2)
        btn_connect.bind(on_press=self._show_ip_dialog)
        ip_box.add_widget(btn_connect)
        root.add_widget(ip_box)

        # 文件列表
        root.add_widget(make_label(text=t('label_files'), font_size=14, size_hint_y=0.05, bold=True))
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
        btn_box.add_widget(make_button(text=t('btn_scan'), font_size=14, on_press=self._scan_devices))
        btn_box.add_widget(make_button(text=t('btn_refresh'), font_size=14, on_press=self._refresh_files_btn))
        btn_box.add_widget(make_button(text=t('btn_upload'), font_size=14, on_press=self._upload_file_btn))
        root.add_widget(btn_box)

        self._update_device_ui()
        return root

    def _build_error_ui(self, error_msg):
        root = BoxLayout(orientation='vertical', padding=20, spacing=10)
        root.add_widget(make_label(text=t('error_title'), font_size=20, bold=True, size_hint_y=0.2))
        root.add_widget(make_label(text=t('error_msg', error_msg), font_size=14, size_hint_y=0.4))
        root.add_widget(make_button(text=t('btn_retry'), font_size=16, size_hint_y=0.1, on_press=lambda x: self._retry()))
        return root

    def _retry(self):
        self.root.clear_widgets()
        self.root.add_widget(self._build_ui())
        Clock.schedule_once(self._delayed_init, 0.5)

    def _on_lang_change(self, spinner, text):
        global current_lang
        current_lang = 'zh' if text == '中文' else 'en'
        # 重建 UI
        self.root.clear_widgets()
        self.root.add_widget(self._build_ui())
        Clock.schedule_once(lambda dt: setattr(self, 'status_text', t('status_ready')), 0)

    def _show_ip_dialog(self, *args):
        """弹出 IP 输入对话框（避免直接 TextInput 导致闪退）"""
        from kivy.uix.popup import Popup

        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        content.add_widget(make_label(text=t('hint_ip'), font_size=14))

        # 预填之前的 IP
        prefill = self.ip_display.text or ''
        ip_input = make_textinput(
            hint_text='192.168.1.100:8080',
            text=prefill,
            size_hint_y=0.4,
        )
        content.add_widget(ip_input)

        btn_box = BoxLayout(size_hint_y=0.4, spacing=10)

        def on_ok(btn):
            addr = ip_input.text.strip()
            popup.dismiss()
            if addr:
                self._do_manual_connect(addr)

        def on_cancel(btn):
            popup.dismiss()

        btn_box.add_widget(make_button(text=t('btn_connect'), font_size=14, on_press=on_ok))
        btn_box.add_widget(make_button(text='X', font_size=14, on_press=on_cancel))
        content.add_widget(btn_box)

        popup = Popup(
            title=t('label_manual'),
            content=content,
            size_hint=(0.8, 0.4),
            auto_dismiss=True,
        )
        popup.open()

    def _do_manual_connect(self, addr):
        """执行手动连接"""
        if ':' in addr:
            ip, port = addr.rsplit(':', 1)
            try:
                port = int(port)
            except ValueError:
                port = HTTP_PORT
        else:
            ip = addr
            port = HTTP_PORT

        self.ip_display.text = f'{ip}:{port}'
        device = {
            'device_id': f'manual-{ip}',
            'name': f'{ip}',
            'ip': ip,
            'port': port,
            'platform': 'Unknown'
        }
        self._connect_to_device(device)

    def _delayed_init(self, dt):
        try:
            self._init_device_info()
            self._init_upload_dir()
            self._start_udp_service()
            self.status_text = t('status_ready')
            Logger.info('FileShare: 初始化成功')
        except Exception as e:
            Logger.error(f'FileShare: 初始化失败: {e}')
            self.status_text = t('status_init_fail', e)

    def _init_device_info(self):
        try:
            self.device_id = self._get_device_id()
            self.device_name = f'Android-{self._get_device_name()}'
            self.local_ip = self._get_local_ip()
        except Exception as e:
            Logger.warning(f'FileShare: 设备信息获取失败: {e}')

    def _init_upload_dir(self):
        try:
            if platform == 'android':
                from android.storage import app_storage_path
                base = app_storage_path()
            else:
                base = os.getcwd()
            self.upload_dir = Path(base) / 'downloads'
            self.upload_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            Logger.warning(f'FileShare: 创建上传目录失败: {e}')
            self.upload_dir = Path('downloads')
            self.upload_dir.mkdir(exist_ok=True)

    def _get_device_id(self):
        if platform == 'android':
            try:
                from jnius import autoclass
                Settings = autoclass('android.provider.Settings$Secure')
                context = autoclass('org.kivy.android.PythonActivity').mActivity
                return Settings.getString(context.getContentResolver(), Settings.ANDROID_ID)
            except Exception:
                pass
        return f'android-{int(time.time())}'

    def _get_device_name(self):
        if platform == 'android':
            try:
                from jnius import autoclass
                Build = autoclass('android.os.Build')
                return Build.MODEL
            except Exception:
                pass
        return 'Android Device'

    def _get_local_ip(self):
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
            except Exception:
                pass
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return '0.0.0.0'

    def _start_udp_service(self):
        self.udp_running = True

        def udp_service():
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.settimeout(1.0)
                try:
                    sock.bind(('', UDP_BROADCAST_PORT))
                except Exception:
                    try:
                        sock.bind(('', 0))
                    except Exception:
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
                    except Exception:
                        time.sleep(1)
            except Exception as e:
                Logger.error(f'FileShare: UDP失败: {e}')
            finally:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass

        self.udp_thread = threading.Thread(target=udp_service, daemon=True)
        self.udp_thread.start()

    def _get_broadcast_addr(self):
        if self.local_ip and self.local_ip != '0.0.0.0':
            parts = self.local_ip.split('.')
            if len(parts) == 4:
                return f'{parts[0]}.{parts[1]}.{parts[2]}.255'
        return '<broadcast>'

    def _broadcast_device(self):
        try:
            msg = json.dumps({
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
            }).encode('utf-8')
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(msg, (self._get_broadcast_addr(), UDP_BROADCAST_PORT))
            sock.close()
        except Exception as e:
            Logger.warning(f'FileShare: 广播失败: {e}')

    def _handle_udp_message(self, data):
        try:
            msg = json.loads(data.decode('utf-8'))
            if msg.get('type') == 'announce':
                dev = msg.get('data', {})
                if dev.get('device_id') != self.device_id:
                    Clock.schedule_once(lambda dt: self._add_device(dev), 0)
        except Exception:
            pass

    def _add_device(self, device):
        try:
            for i, dev in enumerate(self.devices):
                if dev.get('device_id') == device.get('device_id'):
                    self.devices[i] = device
                    return
            self.devices.append(device)
            self.status_text = f'{t("status_scan_sent")} {device.get("name", "")}'
        except Exception:
            pass

    def _update_status(self, *args):
        if hasattr(self, 'status_label'):
            self.status_label.text = self.status_text

    def _update_device_ui(self, *args):
        if not hasattr(self, 'device_box'):
            return
        self.device_box.clear_widgets()
        if not self.devices:
            self.device_box.add_widget(make_label(text=t('label_no_device'), font_size=14, size_hint_y=None, height=40))
            return
        for dev in self.devices:
            name = dev.get('name', '?')
            ip = dev.get('ip', '?')
            btn = make_button(text=f'{name} ({ip})', font_size=14, size_hint_y=None, height=45)
            btn.bind(on_press=lambda b, d=dev: self._connect_to_device(d))
            self.device_box.add_widget(btn)

    def _connect_to_device(self, device):
        self.current_device = device
        self.status_text = t('status_connected', device.get('name', '?'))
        self._refresh_files()

    def _refresh_files(self):
        if not self.current_device:
            self.status_text = t('status_no_device')
            return
        if not requests:
            return

        def fetch():
            try:
                ip = self.current_device.get('ip', '')
                port = self.current_device.get('port', HTTP_PORT)
                resp = requests.get(f'http://{ip}:{port}/api/files', timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('status') == 'success':
                        fl = data.get('data', {}).get('files', [])
                        Clock.schedule_once(lambda dt: self._set_files(fl), 0)
                        return
                Clock.schedule_once(lambda dt: self._set_status(f'HTTP {resp.status_code}'), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._set_status(t('status_connect_fail', e)), 0)

        threading.Thread(target=fetch, daemon=True).start()

    def _set_files(self, fl):
        self.files = fl
        self._update_file_ui()
        self.status_text = t('status_files', self.current_device.get('name', '?'), len(fl))

    def _set_status(self, text):
        self.status_text = text

    def _update_file_ui(self, *args):
        if not hasattr(self, 'file_box'):
            return
        self.file_box.clear_widgets()
        if not self.files:
            self.file_box.add_widget(make_label(text=t('label_no_file'), font_size=14, size_hint_y=None, height=40))
            return
        for f in self.files:
            name = f.get('name', '?')
            size_kb = f.get('size', 0) / 1024
            btn = make_button(text=f'{name} ({size_kb:.1f}KB)', font_size=13, size_hint_y=None, height=45)
            btn.bind(on_press=lambda b, n=name: self._download_file(n))
            self.file_box.add_widget(btn)

    def _scan_devices(self, *args):
        self.status_text = t('status_scanning')
        self._broadcast_device()
        Clock.schedule_once(lambda dt: self._set_status(t('status_scan_sent')), 0)

    def _refresh_files_btn(self, *args):
        self._refresh_files()

    def _download_file(self, filename):
        if not self.current_device or not requests:
            return

        def do_dl():
            try:
                ip = self.current_device.get('ip', '')
                port = self.current_device.get('port', HTTP_PORT)
                resp = requests.get(f'http://{ip}:{port}/api/files/{filename}', timeout=30, stream=True)
                if resp.status_code == 200:
                    path = self.upload_dir / filename
                    with open(path, 'wb') as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
                    Clock.schedule_once(lambda dt: self._set_status(t('status_download_done', filename)), 0)
                else:
                    Clock.schedule_once(lambda dt: self._set_status(t('status_download_fail', resp.status_code)), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._set_status(t('status_download_fail', e)), 0)

        self.status_text = t('status_downloading', filename)
        threading.Thread(target=do_dl, daemon=True).start()

    def _upload_file_btn(self, *args):
        if not self.current_device:
            self.status_text = t('status_no_device')
            return
        if not self.upload_dir:
            return
        files = list(self.upload_dir.iterdir()) if self.upload_dir.exists() else []
        if not files:
            self.status_text = t('status_no_file')
            return
        if not requests:
            return

        def do_up(fp):
            try:
                ip = self.current_device.get('ip', '')
                port = self.current_device.get('port', HTTP_PORT)
                with open(fp, 'rb') as f:
                    resp = requests.post(f'http://{ip}:{port}/api/files', files={'file': (fp.name, f)}, timeout=30)
                if resp.status_code == 201:
                    Clock.schedule_once(lambda dt: self._set_status(t('status_upload_done', fp.name)), 0)
                    self._refresh_files()
                else:
                    Clock.schedule_once(lambda dt: self._set_status(t('status_upload_fail', resp.status_code)), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._set_status(t('status_upload_fail', e)), 0)

        self.status_text = t('status_uploading', files[0].name)
        threading.Thread(target=do_up, args=(files[0],), daemon=True).start()

    def on_stop(self):
        self.udp_running = False
        if self.udp_thread and self.udp_thread.is_alive():
            self.udp_thread.join(timeout=2)


if __name__ == '__main__':
    try:
        FileShareApp().run()
    except Exception as e:
        Logger.error(f'FileShare: 崩溃: {e}')
        print(f'FATAL: {e}')
        print(traceback.format_exc())
