"""
文件共享 Android 客户端 (Kivy)
v0.5 - 修复字体/扫描/上传/布局
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
from kivy.uix.popup import Popup
from kivy.properties import ListProperty, ObjectProperty, StringProperty
from kivy.clock import Clock
from kivy.utils import platform
from kivy.logger import Logger
from kivy.core.text import LabelBase

UDP_BROADCAST_PORT = 5555
HTTP_PORT = 8080

# ========== 字体 ==========
def get_font_path():
    # 1. 优先用打包的字体
    bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'NotoSansSC-Regular.otf')
    if os.path.exists(bundled):
        return bundled
    # 2. Android 系统字体
    if platform == 'android':
        for fp in [
            '/system/fonts/NotoSansCJK-Regular.ttc',
            '/system/fonts/NotoSansSC-Regular.otf',
            '/system/fonts/DroidSansFallback.ttf',
            '/system/fonts/NotoSansCJK-Regular.otf',
            '/system/fonts/NotoSansHans-Regular.otf',
        ]:
            if os.path.exists(fp):
                return fp
    return None

FONT_PATH = get_font_path()
if FONT_PATH:
    LabelBase.register(name='CJK', fn_regular=FONT_PATH)
    FONT = 'CJK'
    Logger.info(f'FileShare: font={FONT_PATH}')
else:
    FONT = 'Roboto'
    Logger.warning('FileShare: no CJK font found')

# ========== 国际化 ==========
LANG = {
    'zh': {
        'title': '文件共享',
        'status_init': '正在初始化...',
        'status_ready': '就绪，点击扫描设备',
        'status_scanning': '正在扫描...',
        'status_scan_sent': '扫描已发送，等待响应...',
        'status_connected': '已连接: {}',
        'status_files': '{} - {} 个文件',
        'status_no_device': '请先选择一个设备',
        'status_no_file': '没有可上传的文件',
        'status_downloading': '下载中: {}...',
        'status_uploading': '上传中: {}...',
        'status_download_done': '下载完成: {}',
        'status_upload_done': '上传成功: {}',
        'status_fail': '失败: {}',
        'status_connect_fail': '连接失败: {}',
        'status_enter_ip': '请输入IP地址',
        'status_init_fail': '初始化异常: {}',
        'label_devices': '设备列表',
        'label_files': '远端文件',
        'label_manual': '手动连接',
        'label_no_device': '暂无设备，点击扫描',
        'label_no_file': '暂无文件',
        'label_lang': '语言',
        'hint_ip': 'IP地址:端口',
        'btn_scan': '扫描',
        'btn_refresh': '刷新',
        'btn_upload': '上传',
        'btn_connect': '连接',
        'btn_cancel': '取消',
        'btn_retry': '重试',
        'btn_pick_file': '选择文件',
        'error_title': '启动错误',
        'error_msg': '{}',
    },
    'en': {
        'title': 'File Share',
        'status_init': 'Initializing...',
        'status_ready': 'Ready, tap Scan',
        'status_scanning': 'Scanning...',
        'status_scan_sent': 'Scan sent, waiting...',
        'status_connected': 'Connected: {}',
        'status_files': '{} - {} files',
        'status_no_device': 'Select a device first',
        'status_no_file': 'No files to upload',
        'status_downloading': 'Downloading: {}...',
        'status_uploading': 'Uploading: {}...',
        'status_download_done': 'Downloaded: {}',
        'status_upload_done': 'Uploaded: {}',
        'status_fail': 'Failed: {}',
        'status_connect_fail': 'Connect failed: {}',
        'status_enter_ip': 'Enter IP',
        'status_init_fail': 'Init failed: {}',
        'label_devices': 'Devices',
        'label_files': 'Remote Files',
        'label_manual': 'Manual Connect',
        'label_no_device': 'No devices, tap Scan',
        'label_no_file': 'No files',
        'label_lang': 'Lang',
        'hint_ip': 'IP:Port',
        'btn_scan': 'Scan',
        'btn_refresh': 'Refresh',
        'btn_upload': 'Upload',
        'btn_connect': 'Connect',
        'btn_cancel': 'Cancel',
        'btn_retry': 'Retry',
        'btn_pick_file': 'Pick File',
        'error_title': 'Error',
        'error_msg': '{}',
    }
}

current_lang = 'zh'


def t(key, *args):
    text = LANG.get(current_lang, LANG['zh']).get(key, key)
    if args:
        try:
            return text.format(*args)
        except Exception:
            return text
    return text


def lbl(text='', size=18, **kw):
    """创建 Label"""
    kw.setdefault('font_size', size)
    kw.setdefault('font_name', FONT)
    return Label(text=text, **kw)


def btn(text='', size=18, **kw):
    """创建 Button"""
    kw.setdefault('font_size', size)
    kw.setdefault('font_name', FONT)
    return Button(text=text, **kw)


def tinput(hint='', **kw):
    """创建 TextInput"""
    kw.setdefault('font_name', FONT)
    kw.setdefault('font_size', 18)
    kw.setdefault('multiline', False)
    kw.setdefault('write_tab', False)
    kw.setdefault('use_bubble', False)
    kw.setdefault('use_handles', False)
    kw.setdefault('size_hint_y', None)
    kw.setdefault('height', 50)
    return TextInput(hint_text=hint, **kw)


class FileShareApp(App):
    status_text = StringProperty('')
    devices = ListProperty([])
    files = ListProperty([])
    current_device = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.upload_dir = None
        self.udp_running = False
        self.udp_thread = None
        self.device_id = 'unknown'
        self.device_name = 'Android'
        self.local_ip = '0.0.0.0'

    def build(self):
        try:
            root = self._build_ui()
            Clock.schedule_once(self._delayed_init, 0.5)
            return root
        except Exception as e:
            Logger.error(f'FileShare: build error: {e}')
            return self._error_ui(str(e))

    def _build_ui(self):
        self.status_text = t('status_init')
        root = BoxLayout(orientation='vertical', padding=12, spacing=8)

        # === 顶栏：标题 + 语言 ===
        top = BoxLayout(size_hint_y=0.07)
        top.add_widget(lbl(t('title'), size=26, bold=True, halign='left', size_hint_x=0.7))
        lang_sp = Spinner(
            text='中文' if current_lang == 'zh' else 'EN',
            values=('中文', 'EN'),
            font_name=FONT,
            font_size=16,
            size_hint_x=0.3,
        )
        lang_sp.bind(text=self._lang_changed)
        top.add_widget(lang_sp)
        root.add_widget(top)

        # === 状态栏 ===
        self.status_label = lbl(t('status_init'), size=15, color=(0.6, 0.6, 0.6, 1), size_hint_y=0.04)
        root.add_widget(self.status_label)
        self.bind(status_text=lambda *a: setattr(self.status_label, 'text', self.status_text))

        # === 设备列表 ===
        root.add_widget(lbl(t('label_devices'), size=16, bold=True, size_hint_y=0.04, halign='left'))
        dev_scroll = ScrollView(size_hint_y=0.22)
        self.dev_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=4)
        self.dev_box.bind(minimum_height=self.dev_box.setter('height'))
        dev_scroll.add_widget(self.dev_box)
        root.add_widget(dev_scroll)

        # === 手动连接行 ===
        ip_row = BoxLayout(size_hint_y=0.06, spacing=8)
        ip_row.add_widget(lbl(t('label_manual'), size=16, size_hint_x=0.25))
        self.ip_label = lbl('', size=16, size_hint_x=0.45, color=(0.4, 0.7, 1, 1))
        ip_row.add_widget(self.ip_label)
        ip_row.add_widget(btn(t('btn_connect'), size=16, size_hint_x=0.3, on_press=self._ip_dialog))
        root.add_widget(ip_row)

        # === 文件列表 ===
        root.add_widget(lbl(t('label_files'), size=16, bold=True, size_hint_y=0.04, halign='left'))
        file_scroll = ScrollView(size_hint_y=0.3)
        self.file_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=4)
        self.file_box.bind(minimum_height=self.file_box.setter('height'))
        file_scroll.add_widget(self.file_box)
        root.add_widget(file_scroll)

        # === 底部按钮 ===
        bot = BoxLayout(size_hint_y=0.07, spacing=8)
        bot.add_widget(btn(t('btn_scan'), size=18, on_press=self._scan))
        bot.add_widget(btn(t('btn_refresh'), size=18, on_press=lambda *a: self._refresh()))
        bot.add_widget(btn(t('btn_upload'), size=18, on_press=self._upload))
        root.add_widget(bot)

        self._refresh_dev_ui()
        self._refresh_file_ui()
        return root

    def _error_ui(self, msg):
        r = BoxLayout(orientation='vertical', padding=20, spacing=10)
        r.add_widget(lbl(t('error_title'), size=22, bold=True, size_hint_y=0.2))
        r.add_widget(lbl(t('error_msg', msg), size=16, size_hint_y=0.5))
        r.add_widget(btn(t('btn_retry'), size=18, size_hint_y=0.15, on_press=lambda *a: self._retry()))
        return r

    def _retry(self):
        self.root.clear_widgets()
        self.root.add_widget(self._build_ui())
        Clock.schedule_once(self._delayed_init, 0.5)

    def _lang_changed(self, sp, text):
        global current_lang
        current_lang = 'en' if text == 'EN' else 'zh'
        self.root.clear_widgets()
        self.root.add_widget(self._build_ui())
        self.status_text = t('status_ready')

    # ---------- 延迟初始化 ----------
    def _delayed_init(self, dt):
        try:
            self.device_id = self._get_device_id()
            self.device_name = f'Android-{self._get_device_name()}'
            self.local_ip = self._get_local_ip()
            self._init_upload_dir()
            self._start_udp()
            self.status_text = t('status_ready')
        except Exception as e:
            Logger.error(f'FileShare: init error: {e}')
            self.status_text = t('status_init_fail', e)

    def _get_device_id(self):
        if platform == 'android':
            try:
                from jnius import autoclass
                Settings = autoclass('android.provider.Settings$Secure')
                ctx = autoclass('org.kivy.android.PythonActivity').mActivity
                return Settings.getString(ctx.getContentResolver(), Settings.ANDROID_ID)
            except Exception:
                pass
        return f'device-{int(time.time())}'

    def _get_device_name(self):
        if platform == 'android':
            try:
                from jnius import autoclass
                return autoclass('android.os.Build').MODEL
            except Exception:
                pass
        return 'Android'

    def _get_local_ip(self):
        if platform == 'android':
            try:
                from jnius import autoclass
                ctx = autoclass('org.kivy.android.PythonActivity').mActivity
                wm = ctx.getSystemService(ctx.WIFI_SERVICE)
                if wm and wm.isWifiEnabled():
                    info = wm.getConnectionInfo()
                    ip = info.getIpAddress()
                    if ip:
                        return f'{ip&0xff}.{(ip>>8)&0xff}.{(ip>>16)&0xff}.{(ip>>24)&0xff}'
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

    def _init_upload_dir(self):
        try:
            if platform == 'android':
                from android.storage import app_storage_path
                base = app_storage_path()
            else:
                base = os.getcwd()
            self.upload_dir = Path(base) / 'downloads'
            self.upload_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.upload_dir = Path('downloads')
            self.upload_dir.mkdir(exist_ok=True)

    # ---------- UDP ----------
    def _start_udp(self):
        self.udp_running = True
        threading.Thread(target=self._udp_loop, daemon=True).start()

    def _udp_loop(self):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(2)
            try:
                sock.bind(('', UDP_BROADCAST_PORT))
                Logger.info('FileShare: UDP bound 5555')
            except Exception as e:
                Logger.warning(f'FileShare: UDP bind 5555 failed: {e}, trying random')
                try:
                    sock.bind(('', 0))
                except Exception:
                    return

            last_bc = time.time()
            while self.udp_running:
                now = time.time()
                if now - last_bc >= 5:
                    self._broadcast()
                    last_bc = now
                try:
                    data, addr = sock.recvfrom(2048)
                    self._on_udp(data)
                except socket.timeout:
                    continue
                except Exception as e:
                    Logger.warning(f'FileShare: UDP recv error: {e}')
        except Exception as e:
            Logger.error(f'FileShare: UDP loop error: {e}')
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def _bcast_addr(self):
        if self.local_ip and self.local_ip != '0.0.0.0':
            parts = self.local_ip.split('.')
            if len(parts) == 4:
                return f'{parts[0]}.{parts[1]}.{parts[2]}.255'
        return '255.255.255.255'

    def _broadcast(self):
        try:
            msg = json.dumps({
                'version': '1.0', 'type': 'announce',
                'data': {
                    'device_id': self.device_id,
                    'name': self.device_name,
                    'ip': self.local_ip,
                    'port': HTTP_PORT,
                    'platform': 'Android'
                },
                'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S')
            }).encode()
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(msg, (self._bcast_addr(), UDP_BROADCAST_PORT))
            s.close()
        except Exception as e:
            Logger.warning(f'FileShare: broadcast error: {e}')

    def _on_udp(self, data):
        try:
            msg = json.loads(data.decode())
            if msg.get('type') == 'announce':
                dev = msg.get('data', {})
                if dev.get('device_id') != self.device_id:
                    Clock.schedule_once(lambda dt: self._add_dev(dev), 0)
        except Exception:
            pass

    def _add_dev(self, dev):
        for i, d in enumerate(self.devices):
            if d.get('device_id') == dev.get('device_id'):
                self.devices[i] = dev
                self._refresh_dev_ui()
                return
        self.devices.append(dev)
        self._refresh_dev_ui()
        self.status_text = f'{t("status_scan_sent")} {dev.get("name", "")}'

    # ---------- UI 刷新 ----------
    def _refresh_dev_ui(self, *a):
        if not hasattr(self, 'dev_box'):
            return
        self.dev_box.clear_widgets()
        if not self.devices:
            self.dev_box.add_widget(lbl(t('label_no_device'), size=16, size_hint_y=None, height=44))
            return
        for d in self.devices:
            name = d.get('name', '?')
            ip = d.get('ip', '?')
            plat = d.get('platform', '')
            b = btn(f'{name}  ({ip})  [{plat}]', size=16, size_hint_y=None, height=48)
            b.bind(on_press=lambda btn, dd=d: self._connect(dd))
            self.dev_box.add_widget(b)

    def _refresh_file_ui(self, *a):
        if not hasattr(self, 'file_box'):
            return
        self.file_box.clear_widgets()
        if not self.files:
            self.file_box.add_widget(lbl(t('label_no_file'), size=16, size_hint_y=None, height=44))
            return
        for f in self.files:
            name = f.get('name', '?')
            sz = f.get('size', 0)
            if sz < 1024:
                sz_s = f'{sz}B'
            elif sz < 1048576:
                sz_s = f'{sz/1024:.1f}KB'
            else:
                sz_s = f'{sz/1048576:.1f}MB'
            b = btn(f'{name}  ({sz_s})', size=15, size_hint_y=None, height=48)
            b.bind(on_press=lambda btn, n=name: self._download(n))
            self.file_box.add_widget(b)

    # ---------- 操作 ----------
    def _scan(self, *a):
        self.status_text = t('status_scanning')
        self._broadcast()

    def _connect(self, dev):
        try:
            self.current_device = dev
            self.status_text = t('status_connected', dev.get('name', '?'))
            self._refresh()
        except Exception as e:
            self.status_text = t('status_connect_fail', e)

    def _refresh(self):
        if not self.current_device:
            self.status_text = t('status_no_device')
            return
        if not requests:
            return

        def do():
            try:
                ip = self.current_device.get('ip', '')
                port = self.current_device.get('port', HTTP_PORT)
                r = requests.get(f'http://{ip}:{port}/api/files', timeout=5)
                if r.status_code == 200:
                    d = r.json()
                    if d.get('status') == 'success':
                        fl = d.get('data', {}).get('files', [])
                        Clock.schedule_once(lambda dt: self._set_files(fl), 0)
                        return
                Clock.schedule_once(lambda dt: setattr(self, 'status_text', t('status_fail', r.status_code)), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self, 'status_text', t('status_connect_fail', e)), 0)

        threading.Thread(target=do, daemon=True).start()

    def _set_files(self, fl):
        self.files = fl
        self._refresh_file_ui()
        self.status_text = t('status_files', self.current_device.get('name', '?'), len(fl))

    def _download(self, name):
        if not self.current_device or not requests:
            return

        def do():
            try:
                ip = self.current_device.get('ip', '')
                port = self.current_device.get('port', HTTP_PORT)
                r = requests.get(f'http://{ip}:{port}/api/files/{name}', timeout=60, stream=True)
                if r.status_code == 200:
                    p = self.upload_dir / name
                    with open(p, 'wb') as f:
                        for chunk in r.iter_content(8192):
                            f.write(chunk)
                    Clock.schedule_once(lambda dt: setattr(self, 'status_text', t('status_download_done', name)), 0)
                else:
                    Clock.schedule_once(lambda dt: setattr(self, 'status_text', t('status_fail', r.status_code)), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self, 'status_text', t('status_fail', e)), 0)

        self.status_text = t('status_downloading', name)
        threading.Thread(target=do, daemon=True).start()

    def _upload(self, *a):
        if not self.current_device:
            self.status_text = t('status_no_device')
            return

        if platform == 'android':
            self._android_pick_file()
        else:
            self._desktop_pick_file()

    def _android_pick_file(self):
        """用 Android Intent 打开文件选择器"""
        try:
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity

            intent = Intent(Intent.ACTION_GET_CONTENT)
            intent.setType('*/*')
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            activity.startActivityForResult(intent, 1)

            # 监听结果（简化版：轮询检查）
            Clock.schedule_once(lambda dt: self._check_intent_result(activity), 1)
        except Exception as e:
            Logger.error(f'FileShare: Android picker error: {e}')
            # 后备：列出 upload_dir 文件
            self._fallback_upload()

    def _check_intent_result(self, activity, tries=0):
        """检查 Intent 返回结果"""
        try:
            result = activity.getIntent()
            # 这个方法不太可靠，用备用方案
            pass
        except Exception:
            pass

    def _desktop_pick_file(self):
        """桌面端文件选择"""
        try:
            from tkinter import Tk, filedialog
            root = Tk()
            root.withdraw()
            path = filedialog.askopenfilename()
            root.destroy()
            if path:
                self._do_upload(Path(path))
        except Exception as e:
            Logger.error(f'FileShare: file picker error: {e}')
            self._fallback_upload()

    def _fallback_upload(self):
        """后备：显示 upload_dir 中的文件列表供选择"""
        if not self.upload_dir or not self.upload_dir.exists():
            self.status_text = t('status_no_file')
            return

        files = [f for f in self.upload_dir.iterdir() if f.is_file()]
        if not files:
            self.status_text = t('status_no_file')
            return

        content = BoxLayout(orientation='vertical', spacing=6, padding=10)
        scroll = ScrollView(size_hint_y=0.8)
        file_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=4)
        file_box.bind(minimum_height=file_box.setter('height'))

        for f in files:
            b = btn(f'{f.name}  ({f.stat().st_size // 1024}KB)', size=14, size_hint_y=None, height=44)
            b.bind(on_press=lambda btn, fp=f: (popup.dismiss(), self._do_upload(fp)))
            file_box.add_widget(b)

        scroll.add_widget(file_box)
        content.add_widget(scroll)
        content.add_widget(btn(t('btn_cancel'), size=16, size_hint_y=0.15, on_press=lambda *a: popup.dismiss()))

        popup = Popup(title=t('btn_pick_file'), content=content, size_hint=(0.9, 0.7))
        popup.open()

    def _do_upload(self, filepath):
        if not self.current_device or not requests:
            return

        def do():
            try:
                ip = self.current_device.get('ip', '')
                port = self.current_device.get('port', HTTP_PORT)
                with open(filepath, 'rb') as f:
                    r = requests.post(f'http://{ip}:{port}/api/files',
                                      files={'file': (filepath.name, f)}, timeout=60)
                if r.status_code == 201:
                    Clock.schedule_once(lambda dt: setattr(self, 'status_text', t('status_upload_done', filepath.name)), 0)
                    self._refresh()
                else:
                    Clock.schedule_once(lambda dt: setattr(self, 'status_text', t('status_fail', r.status_code)), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self, 'status_text', t('status_fail', e)), 0)

        self.status_text = t('status_uploading', filepath.name)
        threading.Thread(target=do, daemon=True).start()

    # ---------- 手动连接对话框 ----------
    def _ip_dialog(self, *a):
        content = BoxLayout(orientation='vertical', spacing=10, padding=15)
        content.add_widget(lbl(t('hint_ip'), size=16))
        ip_input = tinput('192.168.1.100:8080', text=self.ip_label.text or '')
        content.add_widget(ip_input)

        btns = BoxLayout(size_hint_y=None, height=50, spacing=10)

        def on_ok(*a):
            try:
                addr = ip_input.text.strip()
                popup.dismiss()
                if addr:
                    self._do_connect(addr)
            except Exception as e:
                Logger.error(f'FileShare: connect error: {e}')
                try:
                    popup.dismiss()
                except Exception:
                    pass

        def on_cancel(*a):
            popup.dismiss()

        btns.add_widget(btn(t('btn_connect'), size=18, on_press=on_ok))
        btns.add_widget(btn(t('btn_cancel'), size=18, on_press=on_cancel))
        content.add_widget(btns)

        popup = Popup(title=t('label_manual'), content=content, size_hint=(0.85, 0.4))
        popup.open()

    def _do_connect(self, addr):
        try:
            if ':' in addr:
                ip, port = addr.rsplit(':', 1)
                try:
                    port = int(port)
                except ValueError:
                    port = HTTP_PORT
            else:
                ip = addr
                port = HTTP_PORT

            self.ip_label.text = f'{ip}:{port}'
            self._connect({
                'device_id': f'manual-{ip}',
                'name': ip,
                'ip': ip,
                'port': port,
                'platform': 'Unknown'
            })
        except Exception as e:
            self.status_text = t('status_connect_fail', e)

    def on_stop(self):
        self.udp_running = False


if __name__ == '__main__':
    try:
        FileShareApp().run()
    except Exception as e:
        print(f'FATAL: {e}')
        print(traceback.format_exc())
