"""
文件共享 Android 客户端 (Kivy)
v0.6 - 稳定版，不依赖外部字体
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

UDP_BROADCAST_PORT = 5555
HTTP_PORT = 8080

# ========== 字体 ==========
# 不注册自定义字体，用 Kivy 默认的 Roboto
# Roboto 支持基本中文，如果显示黑框是 Android 版本问题
FONT = 'Roboto'

# ========== 国际化 ==========
LANG = {
    'zh': {
        'title': 'FileShare',
        'init': '初始化中...',
        'ready': '就绪',
        'scanning': '扫描中...',
        'scan_ok': '扫描完成',
        'connected': '已连接: {}',
        'files': '{} - {} 文件',
        'no_dev': '无设备',
        'no_file': '无文件',
        'dl': '下载: {}...',
        'ul': '上传: {}...',
        'dl_ok': '下载: {}',
        'ul_ok': '上传: {}',
        'fail': '失败: {}',
        'conn_fail': '连接失败: {}',
        'devices': '设备',
        'files_label': '文件',
        'manual': '手动',
        'ip_hint': 'IP:端口',
        'scan': '扫描',
        'refresh': '刷新',
        'upload': '上传',
        'connect': '连接',
        'cancel': '取消',
        'pick': '选择文件',
        'error': '错误',
    },
    'en': {
        'title': 'FileShare',
        'init': 'Init...',
        'ready': 'Ready',
        'scanning': 'Scanning...',
        'scan_ok': 'Scan done',
        'connected': 'Connected: {}',
        'files': '{} - {} files',
        'no_dev': 'No devices',
        'no_file': 'No files',
        'dl': 'DL: {}...',
        'ul': 'UL: {}...',
        'dl_ok': 'DL: {}',
        'ul_ok': 'UL: {}',
        'fail': 'Fail: {}',
        'conn_fail': 'Conn fail: {}',
        'devices': 'Devices',
        'files_label': 'Files',
        'manual': 'Manual',
        'ip_hint': 'IP:port',
        'scan': 'Scan',
        'refresh': 'Refresh',
        'upload': 'Upload',
        'connect': 'Connect',
        'cancel': 'Cancel',
        'pick': 'Pick file',
        'error': 'Error',
    }
}

cur_lang = 'zh'

def t(k, *a):
    s = LANG.get(cur_lang, LANG['zh']).get(k, k)
    if a:
        try: return s.format(*a)
        except: return s
    return s

def mk_lbl(text='', size=18, **kw):
    kw.setdefault('font_size', size)
    return Label(text=text, **kw)

def mk_btn(text='', size=18, **kw):
    kw.setdefault('font_size', size)
    return Button(text=text, **kw)

def mk_input(hint='', **kw):
    kw.setdefault('font_size', 18)
    kw.setdefault('multiline', False)
    kw.setdefault('write_tab', False)
    kw.setdefault('use_bubble', False)
    kw.setdefault('use_handles', False)
    kw.setdefault('size_hint_y', None)
    kw.setdefault('height', 50)
    return TextInput(hint_text=hint, **kw)


class FileShareApp(App):
    status = StringProperty('')
    devs = ListProperty([])
    files = ListProperty([])
    cur_dev = ObjectProperty(None, allownone=True)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.upload_dir = None
        self.udp_on = False
        self.udp_t = None
        self.dev_id = '?'
        self.dev_name = 'Android'
        self.ip = '0.0.0.0'

    def build(self):
        try:
            r = self._ui()
            Clock.schedule_once(self._init, 0.5)
            return r
        except Exception as e:
            Logger.error(f'FS: build err: {e}')
            return self._err_ui(str(e))

    def _ui(self):
        self.status = t('init')
        r = BoxLayout(orientation='vertical', padding=12, spacing=8)

        # 顶栏
        top = BoxLayout(size_hint_y=0.07)
        top.add_widget(mk_lbl(t('title'), size=28, bold=True, size_hint_x=0.7))
        sp = Spinner(text='中文' if cur_lang=='zh' else 'EN', values=('中文','EN'), font_size=16, size_hint_x=0.3)
        sp.bind(text=self._lang_chg)
        top.add_widget(sp)
        r.add_widget(top)

        # 状态
        self.st_lbl = mk_lbl(t('init'), size=15, color=(.6,.6,.6,1), size_hint_y=0.04)
        r.add_widget(self.st_lbl)
        self.bind(status=lambda *a: setattr(self.st_lbl, 'text', self.status))

        # 设备
        r.add_widget(mk_lbl(t('devices'), size=16, bold=True, size_hint_y=0.04, halign='left'))
        ds = ScrollView(size_hint_y=0.22)
        self.d_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=4)
        self.d_box.bind(minimum_height=self.d_box.setter('height'))
        ds.add_widget(self.d_box)
        r.add_widget(ds)

        # 手动
        ip_r = BoxLayout(size_hint_y=0.06, spacing=8)
        ip_r.add_widget(mk_lbl(t('manual'), size=16, size_hint_x=0.25))
        self.ip_lbl = mk_lbl('', size=16, size_hint_x=0.45, color=(.4,.7,1,1))
        ip_r.add_widget(self.ip_lbl)
        ip_r.add_widget(mk_btn(t('connect'), size=16, size_hint_x=0.3, on_press=self._ip_dlg))
        r.add_widget(ip_r)

        # 文件
        r.add_widget(mk_lbl(t('files_label'), size=16, bold=True, size_hint_y=0.04, halign='left'))
        fs = ScrollView(size_hint_y=0.3)
        self.f_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=4)
        self.f_box.bind(minimum_height=self.f_box.setter('height'))
        fs.add_widget(self.f_box)
        r.add_widget(fs)

        # 底部
        bot = BoxLayout(size_hint_y=0.07, spacing=8)
        bot.add_widget(mk_btn(t('scan'), size=18, on_press=self._scan))
        bot.add_widget(mk_btn(t('refresh'), size=18, on_press=lambda *a: self._refresh()))
        bot.add_widget(mk_btn(t('upload'), size=18, on_press=self._upload))
        r.add_widget(bot)

        self._dev_ui()
        self._file_ui()
        return r

    def _err_ui(self, msg):
        r = BoxLayout(orientation='vertical', padding=20, spacing=10)
        r.add_widget(mk_lbl(t('error'), size=22, bold=True, size_hint_y=0.2))
        r.add_widget(mk_lbl(msg, size=16, size_hint_y=0.5))
        r.add_widget(mk_btn('Retry', size=18, size_hint_y=0.15, on_press=lambda *a: self._retry()))
        return r

    def _retry(self):
        self.root.clear_widgets()
        self.root.add_widget(self._ui())
        Clock.schedule_once(self._init, 0.5)

    def _lang_chg(self, sp, txt):
        global cur_lang
        cur_lang = 'en' if txt=='EN' else 'zh'
        self.root.clear_widgets()
        self.root.add_widget(self._ui())
        self.status = t('ready')

    def _init(self, dt):
        try:
            self.dev_id = self._get_id()
            self.dev_name = f'Android-{self._get_model()}'
            self.ip = self._get_ip()
            self._mk_dir()
            self._start_udp()
            self.status = t('ready')
            Logger.info(f'FS: ok ip={self.ip}')
        except Exception as e:
            Logger.error(f'FS: init err: {e}')
            self.status = t('fail', e)

    def _get_id(self):
        if platform=='android':
            try:
                from jnius import autoclass
                S = autoclass('android.provider.Settings$Secure')
                c = autoclass('org.kivy.android.PythonActivity').mActivity
                return S.getString(c.getContentResolver(), S.ANDROID_ID)
            except: pass
        return f'd-{int(time.time())}'

    def _get_model(self):
        if platform=='android':
            try:
                from jnius import autoclass
                return autoclass('android.os.Build').MODEL
            except: pass
        return 'Device'

    def _get_ip(self):
        if platform=='android':
            try:
                from jnius import autoclass
                c = autoclass('org.kivy.android.PythonActivity').mActivity
                wm = c.getSystemService(c.WIFI_SERVICE)
                if wm and wm.isWifiEnabled():
                    i = wm.getConnectionInfo()
                    ip = i.getIpAddress()
                    if ip:
                        return f'{ip&0xff}.{(ip>>8)&0xff}.{(ip>>16)&0xff}.{(ip>>24)&0xff}'
            except: pass
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return '0.0.0.0'

    def _mk_dir(self):
        try:
            if platform=='android':
                from android.storage import app_storage_path
                base = app_storage_path()
            else:
                base = os.getcwd()
            self.upload_dir = Path(base)/'downloads'
            self.upload_dir.mkdir(parents=True, exist_ok=True)
        except:
            self.upload_dir = Path('downloads')
            self.upload_dir.mkdir(exist_ok=True)

    # --- UDP ---
    def _start_udp(self):
        self.udp_on = True
        self.udp_t = threading.Thread(target=self._udp_loop, daemon=True)
        self.udp_t.start()

    def _udp_loop(self):
        sk = None
        try:
            sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sk.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sk.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sk.settimeout(2)
            try:
                sk.bind(('', UDP_BROADCAST_PORT))
            except:
                try: sk.bind(('', 0))
                except: return
            last = time.time()
            while self.udp_on:
                if time.time()-last >= 5:
                    self._bc()
                    last = time.time()
                try:
                    d, a = sk.recvfrom(2048)
                    self._on_udp(d)
                except socket.timeout:
                    continue
        except Exception as e:
            Logger.error(f'FS: udp err: {e}')
        finally:
            if sk:
                try: sk.close()
                except: pass

    def _bc_addr(self):
        if self.ip and self.ip!='0.0.0.0':
            p = self.ip.split('.')
            if len(p)==4:
                return f'{p[0]}.{p[1]}.{p[2]}.255'
        return '255.255.255.255'

    def _bc(self):
        try:
            m = json.dumps({'version':'1.0','type':'announce','data':{
                'device_id':self.dev_id,'name':self.dev_name,
                'ip':self.ip,'port':HTTP_PORT,'platform':'Android'
            },'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S')}).encode()
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(m, (self._bc_addr(), UDP_BROADCAST_PORT))
            s.close()
        except Exception as e:
            Logger.warning(f'FS: bc err: {e}')

    def _on_udp(self, d):
        try:
            m = json.loads(d.decode())
            if m.get('type')=='announce':
                dv = m.get('data',{})
                if dv.get('device_id')!=self.dev_id:
                    Clock.schedule_once(lambda dt: self._add_dev(dv), 0)
        except: pass

    def _add_dev(self, dv):
        for i,d in enumerate(self.devs):
            if d.get('device_id')==dv.get('device_id'):
                self.devs[i] = dv
                self._dev_ui()
                return
        self.devs.append(dv)
        self._dev_ui()

    # --- UI ---
    def _dev_ui(self, *a):
        if not hasattr(self, 'd_box'): return
        self.d_box.clear_widgets()
        if not self.devs:
            self.d_box.add_widget(mk_lbl(t('no_dev'), size=16, size_hint_y=None, height=44))
            return
        for d in self.devs:
            b = mk_btn(f'{d.get("name","?")} ({d.get("ip","?")})', size=16, size_hint_y=None, height=48)
            b.bind(on_press=lambda x,dd=d: self._connect(dd))
            self.d_box.add_widget(b)

    def _file_ui(self, *a):
        if not hasattr(self, 'f_box'): return
        self.f_box.clear_widgets()
        if not self.files:
            self.f_box.add_widget(mk_lbl(t('no_file'), size=16, size_hint_y=None, height=44))
            return
        for f in self.files:
            n = f.get('name','?')
            sz = f.get('size',0)
            if sz<1024: s=f'{sz}B'
            elif sz<1048576: s=f'{sz/1024:.0f}KB'
            else: s=f'{sz/1048576:.1f}MB'
            b = mk_btn(f'{n} ({s})', size=15, size_hint_y=None, height=48)
            b.bind(on_press=lambda x,n=n: self._dl(n))
            self.f_box.add_widget(b)

    def _scan(self, *a):
        self.status = t('scanning')
        self._bc()
        Clock.schedule_once(lambda dt: setattr(self,'status',t('scan_ok')), 2)

    def _connect(self, d):
        try:
            self.cur_dev = d
            self.status = t('connected', d.get('name','?'))
            self._refresh()
        except Exception as e:
            self.status = t('conn_fail', e)

    def _refresh(self):
        if not self.cur_dev:
            self.status = t('no_dev')
            return
        if not requests: return
        def do():
            try:
                ip = self.cur_dev.get('ip','')
                pt = self.cur_dev.get('port', HTTP_PORT)
                r = requests.get(f'http://{ip}:{pt}/api/files', timeout=5)
                if r.status_code==200:
                    d = r.json()
                    if d.get('status')=='success':
                        fl = d.get('data',{}).get('files',[])
                        Clock.schedule_once(lambda dt: self._set_files(fl), 0)
                        return
                Clock.schedule_once(lambda dt: setattr(self,'status',t('fail',r.status_code)), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self,'status',t('conn_fail',e)), 0)
        threading.Thread(target=do, daemon=True).start()

    def _set_files(self, fl):
        self.files = fl
        self._file_ui()
        self.status = t('files', self.cur_dev.get('name','?'), len(fl))

    def _dl(self, name):
        if not self.cur_dev or not requests: return
        def do():
            try:
                ip = self.cur_dev.get('ip','')
                pt = self.cur_dev.get('port', HTTP_PORT)
                r = requests.get(f'http://{ip}:{pt}/api/files/{name}', timeout=60, stream=True)
                if r.status_code==200:
                    p = self.upload_dir/name
                    with open(p,'wb') as f:
                        for c in r.iter_content(8192): f.write(c)
                    Clock.schedule_once(lambda dt: setattr(self,'status',t('dl_ok',name)), 0)
                else:
                    Clock.schedule_once(lambda dt: setattr(self,'status',t('fail',r.status_code)), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self,'status',t('fail',e)), 0)
        self.status = t('dl', name)
        threading.Thread(target=do, daemon=True).start()

    def _upload(self, *a):
        if not self.cur_dev:
            self.status = t('no_dev')
            return
        if not self.upload_dir or not self.upload_dir.exists():
            self.status = t('no_file')
            return
        fls = [f for f in self.upload_dir.iterdir() if f.is_file()]
        if not fls:
            self.status = t('no_file')
            return

        content = BoxLayout(orientation='vertical', spacing=6, padding=10)
        scroll = ScrollView(size_hint_y=0.8)
        fb = BoxLayout(orientation='vertical', size_hint_y=None, spacing=4)
        fb.bind(minimum_height=fb.setter('height'))
        for f in fls:
            b = mk_btn(f'{f.name} ({f.stat().st_size//1024}KB)', size=14, size_hint_y=None, height=44)
            b.bind(on_press=lambda x,fp=f: (pop.dismiss(), self._do_ul(fp)))
            fb.add_widget(b)
        scroll.add_widget(fb)
        content.add_widget(scroll)
        content.add_widget(mk_btn(t('cancel'), size=16, size_hint_y=0.15, on_press=lambda *a: pop.dismiss()))
        pop = Popup(title=t('pick'), content=content, size_hint=(0.9,0.7))
        pop.open()

    def _do_ul(self, fp):
        if not self.cur_dev or not requests: return
        def do():
            try:
                ip = self.cur_dev.get('ip','')
                pt = self.cur_dev.get('port', HTTP_PORT)
                with open(fp,'rb') as f:
                    r = requests.post(f'http://{ip}:{pt}/api/files', files={'file':(fp.name,f)}, timeout=60)
                if r.status_code==201:
                    Clock.schedule_once(lambda dt: setattr(self,'status',t('ul_ok',fp.name)), 0)
                    self._refresh()
                else:
                    Clock.schedule_once(lambda dt: setattr(self,'status',t('fail',r.status_code)), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self,'status',t('fail',e)), 0)
        self.status = t('ul', fp.name)
        threading.Thread(target=do, daemon=True).start()

    def _ip_dlg(self, *a):
        content = BoxLayout(orientation='vertical', spacing=10, padding=15)
        content.add_widget(mk_lbl(t('ip_hint'), size=16))
        inp = mk_input('192.168.1.100:8080', text=self.ip_lbl.text or '')
        content.add_widget(inp)
        btns = BoxLayout(size_hint_y=None, height=50, spacing=10)
        def ok(*a):
            try:
                addr = inp.text.strip()
                pop.dismiss()
                if addr: self._do_conn(addr)
            except: 
                try: pop.dismiss()
                except: pass
        def cancel(*a): pop.dismiss()
        btns.add_widget(mk_btn(t('connect'), size=18, on_press=ok))
        btns.add_widget(mk_btn(t('cancel'), size=18, on_press=cancel))
        content.add_widget(btns)
        pop = Popup(title=t('manual'), content=content, size_hint=(0.85,0.4))
        pop.open()

    def _do_conn(self, addr):
        try:
            if ':' in addr:
                ip, pt = addr.rsplit(':',1)
                try: pt = int(pt)
                except: pt = HTTP_PORT
            else:
                ip, pt = addr, HTTP_PORT
            self.ip_lbl.text = f'{ip}:{pt}'
            self._connect({'device_id':f'm-{ip}','name':ip,'ip':ip,'port':pt,'platform':'?'})
        except Exception as e:
            self.status = t('conn_fail', e)

    def on_stop(self):
        self.udp_on = False


if __name__ == '__main__':
    try:
        FileShareApp().run()
    except Exception as e:
        print(f'FATAL: {e}')
        print(traceback.format_exc())
