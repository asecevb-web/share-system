#!/usr/bin/env python3
"""
文件共享 Linux 客户端
使用 Tkinter GUI，与 Android 端互通
"""

import os
import sys
import json
import socket
import struct
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from datetime import datetime

# 协议常量（与 Android 端一致）
PROTOCOL_VERSION = "1.0"
UDP_BROADCAST_PORT = 5555
HTTP_PORT = 8080
BROADCAST_INTERVAL = 30

# HTTP 支持
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    # 使用 urllib 作为后备
    import urllib.request
    import urllib.parse
    import urllib.error


class DeviceInfo:
    """设备信息"""
    def __init__(self, device_id, name, ip, port=HTTP_PORT, platform="Unknown"):
        self.device_id = device_id
        self.name = name
        self.ip = ip
        self.port = port
        self.platform = platform
        self.last_seen = time.time()

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "name": self.name,
            "ip": self.ip,
            "port": self.port,
            "platform": self.platform,
            "last_seen": datetime.now().isoformat()
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            device_id=data.get("device_id", ""),
            name=data.get("name", ""),
            ip=data.get("ip", ""),
            port=data.get("port", HTTP_PORT),
            platform=data.get("platform", "Unknown")
        )


class FileShareClient:
    """文件共享客户端核心"""

    def __init__(self):
        self.device_id = f"linux-{socket.gethostname()}-{int(time.time())}"
        self.device_name = socket.gethostname()
        self.local_ip = self._get_local_ip()
        self.devices = {}  # device_id -> DeviceInfo
        self.udp_running = False
        self.udp_thread = None
        self.on_device_found = None  # 回调
        self.on_status_change = None

    def _get_local_ip(self):
        """获取局域网IP（优先WiFi/以太网，排除VPN/隧道）"""
        # 方法1: 查找 wlan/eth 开头的接口
        try:
            import subprocess
            result = subprocess.run(
                ['ip', '-4', 'addr', 'show'],
                capture_output=True, text=True, timeout=5
            )
            current_iface = None
            for line in result.stdout.split('\n'):
                if line and not line.startswith(' '):
                    current_iface = line.split()[1].rstrip(':')
                elif 'inet ' in line and current_iface:
                    # 优先 wlan/eth/rmnet (排除 lo/tun/wg/ppp)
                    if any(current_iface.startswith(p) for p in ('wlan', 'eth', 'rmnet', 'en')):
                        ip = line.strip().split()[1].split('/')[0]
                        return ip
        except Exception:
            pass

        # 方法2: 通过 socket 连接（可能选到VPN）
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return '127.0.0.1'

    def start_udp(self):
        """启动 UDP 广播服务"""
        self.udp_running = True
        self.udp_thread = threading.Thread(target=self._udp_loop, daemon=True)
        self.udp_thread.start()

    def stop_udp(self):
        self.udp_running = False
        if self.udp_thread:
            self.udp_thread.join(timeout=2)

    def _udp_loop(self):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(1.0)
            try:
                sock.bind(('', UDP_BROADCAST_PORT))
            except OSError:
                # 端口被占用，尝试只发送不接收
                sock.close()
                sock = None

            last_broadcast = time.time()
            while self.udp_running:
                # 发送广播
                if time.time() - last_broadcast >= 10:
                    self._broadcast()
                    last_broadcast = time.time()

                # 接收广播
                if sock:
                    try:
                        data, addr = sock.recvfrom(1024)
                        self._handle_udp(data)
                    except socket.timeout:
                        continue
                    except Exception:
                        pass
                else:
                    time.sleep(1)
        except Exception as e:
            print(f"UDP 错误: {e}")
        finally:
            if sock:
                sock.close()

    def _get_broadcast_addr(self):
        """获取局域网广播地址"""
        try:
            import subprocess
            result = subprocess.run(
                ['ip', '-4', 'addr', 'show'],
                capture_output=True, text=True, timeout=5
            )
            current_iface = None
            for line in result.stdout.split('\n'):
                if line and not line.startswith(' '):
                    current_iface = line.split()[1].rstrip(':')
                elif 'inet ' in line and current_iface:
                    if any(current_iface.startswith(p) for p in ('wlan', 'eth', 'rmnet', 'en')):
                        parts = line.strip().split()
                        addr = parts[1]  # e.g. 192.168.1.14/24
                        ip = addr.split('/')[0]
                        prefix = int(addr.split('/')[1]) if '/' in addr else 24
                        # 计算广播地址
                        ip_int = struct.unpack('!I', socket.inet_aton(ip))[0]
                        mask = (0xffffffff << (32 - prefix)) & 0xffffffff
                        bcast_int = ip_int | (~mask & 0xffffffff)
                        return socket.inet_ntoa(struct.pack('!I', bcast_int))
        except Exception:
            pass
        return '<broadcast>'

    def _broadcast(self):
        msg = json.dumps({
            "version": PROTOCOL_VERSION,
            "type": "announce",
            "data": {
                "device_id": self.device_id,
                "name": self.device_name,
                "ip": self.local_ip,
                "port": HTTP_PORT,
                "platform": "Linux"
            },
            "timestamp": datetime.now().isoformat()
        }).encode('utf-8')
        bcast_addr = self._get_broadcast_addr()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(msg, (bcast_addr, UDP_BROADCAST_PORT))
            s.close()
        except Exception as e:
            print(f'广播失败: {e}')

    def _handle_udp(self, data):
        try:
            msg = json.loads(data.decode('utf-8'))
            if msg.get('type') == 'announce':
                dev_data = msg.get('data', {})
                if dev_data.get('device_id') != self.device_id:
                    dev = DeviceInfo.from_dict(dev_data)
                    self.devices[dev.device_id] = dev
                    if self.on_device_found:
                        self.on_device_found(dev)
        except:
            pass

    def scan(self):
        """主动扫描"""
        self._broadcast()

    def get_files(self, device):
        """获取远程文件列表"""
        url = f"http://{device.ip}:{device.port}/api/files"
        try:
            if HAS_REQUESTS:
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('status') == 'success':
                        return data.get('data', {}).get('files', [])
            else:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    if data.get('status') == 'success':
                        return data.get('data', {}).get('files', [])
        except Exception as e:
            raise Exception(f"获取文件列表失败: {e}")
        return []

    def download_file(self, device, filename, save_path):
        """下载文件"""
        url = f"http://{device.ip}:{device.port}/api/files/{filename}"
        try:
            if HAS_REQUESTS:
                resp = requests.get(url, timeout=60, stream=True)
                resp.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
            else:
                urllib.request.urlretrieve(url, save_path)
            return True
        except Exception as e:
            raise Exception(f"下载失败: {e}")

    def upload_file(self, device, file_path):
        """上传文件"""
        url = f"http://{device.ip}:{device.port}/api/files"
        filename = os.path.basename(file_path)
        try:
            if HAS_REQUESTS:
                with open(file_path, 'rb') as f:
                    resp = requests.post(url, files={'file': (filename, f)}, timeout=60)
                    resp.raise_for_status()
                    return resp.json()
            else:
                # multipart/form-data 手动构造
                boundary = f'----WebKitFormBoundary{int(time.time())}'
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                body = (
                    f'--{boundary}\r\n'
                    f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                    f'Content-Type: application/octet-stream\r\n\r\n'
                ).encode() + file_data + f'\r\n--{boundary}--\r\n'.encode()

                req = urllib.request.Request(url, data=body, method='POST')
                req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode())
        except Exception as e:
            raise Exception(f"上传失败: {e}")

    def delete_file(self, device, filename):
        """删除文件"""
        url = f"http://{device.ip}:{device.port}/api/files/{filename}"
        try:
            if HAS_REQUESTS:
                resp = requests.delete(url, timeout=10)
                resp.raise_for_status()
                return resp.json()
            else:
                req = urllib.request.Request(url, method='DELETE')
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode())
        except Exception as e:
            raise Exception(f"删除失败: {e}")

    def search_files(self, device, query):
        """搜索文件"""
        url = f"http://{device.ip}:{device.port}/api/search?q={urllib.parse.quote(query)}"
        try:
            if HAS_REQUESTS:
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('status') == 'success':
                        return data.get('data', {}).get('files', [])
            else:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    if data.get('status') == 'success':
                        return data.get('data', {}).get('files', [])
        except Exception as e:
            raise Exception(f"搜索失败: {e}")
        return []


class FileShareGUI:
    """Tkinter 图形界面"""

    def __init__(self):
        self.client = FileShareClient()
        self.client.on_device_found = self._on_device_found
        self.current_device = None
        self.download_dir = Path.home() / "Downloads" / "FileShare"
        self.download_dir.mkdir(parents=True, exist_ok=True)

        self._build_ui()
        self.client.start_udp()

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("文件共享")
        self.root.geometry("800x600")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 主框架
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # 状态栏
        self.status_var = tk.StringVar(value="正在初始化...")
        status_bar = ttk.Label(main, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(0, 10))

        # 上半部分：设备列表
        device_frame = ttk.LabelFrame(main, text="发现的设备", padding=5)
        device_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        # 设备列表 + 按钮
        device_top = ttk.Frame(device_frame)
        device_top.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(device_top, text="扫描设备", command=self._scan).pack(side=tk.LEFT, padx=2)
        ttk.Button(device_top, text="手动连接", command=self._manual_connect_dialog).pack(side=tk.LEFT, padx=2)

        self.device_tree = ttk.Treeview(device_frame, columns=('name', 'ip', 'platform'), show='headings', height=5)
        self.device_tree.heading('name', text='设备名')
        self.device_tree.heading('ip', text='IP 地址')
        self.device_tree.heading('platform', text='平台')
        self.device_tree.column('name', width=200)
        self.device_tree.column('ip', width=150)
        self.device_tree.column('platform', width=100)
        self.device_tree.bind('<<TreeviewSelect>>', self._on_device_select)

        scrollbar = ttk.Scrollbar(device_frame, orient=tk.VERTICAL, command=self.device_tree.yview)
        self.device_tree.configure(yscrollcommand=scrollbar.set)
        self.device_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 下半部分：文件列表
        file_frame = ttk.LabelFrame(main, text="远端文件", padding=5)
        file_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        # 文件操作按钮
        file_btn_frame = ttk.Frame(file_frame)
        file_btn_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(file_btn_frame, text="刷新文件", command=self._refresh_files).pack(side=tk.LEFT, padx=2)
        ttk.Button(file_btn_frame, text="下载选中", command=self._download_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(file_btn_frame, text="上传文件", command=self._upload_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(file_btn_frame, text="删除选中", command=self._delete_selected).pack(side=tk.LEFT, padx=2)

        # 搜索框
        ttk.Label(file_btn_frame, text="搜索:").pack(side=tk.LEFT, padx=(20, 2))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(file_btn_frame, textvariable=self.search_var, width=20)
        search_entry.pack(side=tk.LEFT, padx=2)
        search_entry.bind('<Return>', lambda e: self._search())
        ttk.Button(file_btn_frame, text="搜索", command=self._search).pack(side=tk.LEFT, padx=2)

        # 文件列表
        self.file_tree = ttk.Treeview(file_frame, columns=('name', 'size', 'modified'), show='headings', height=10)
        self.file_tree.heading('name', text='文件名')
        self.file_tree.heading('size', text='大小')
        self.file_tree.heading('modified', text='修改时间')
        self.file_tree.column('name', width=300)
        self.file_tree.column('size', width=100)
        self.file_tree.column('modified', width=200)

        file_scrollbar = ttk.Scrollbar(file_frame, orient=tk.VERTICAL, command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=file_scrollbar.set)
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        file_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 下载目录提示
        ttk.Label(main, text=f"下载目录: {self.download_dir}", foreground='gray').pack(anchor=tk.W, pady=(5, 0))

    def _on_device_found(self, device):
        """发现设备回调"""
        self.root.after(0, self._update_device_list)

    def _update_device_list(self):
        """更新设备列表"""
        # 保存当前选中
        selected = self.device_tree.selection()

        # 清空并重建
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)

        for dev in self.client.devices.values():
            self.device_tree.insert('', tk.END, iid=dev.device_id,
                                     values=(dev.name, dev.ip, dev.platform))

        # 恢复选中
        if selected:
            try:
                self.device_tree.selection_set(selected)
            except:
                pass

    def _on_device_select(self, event):
        """设备选中"""
        selection = self.device_tree.selection()
        if selection:
            dev_id = selection[0]
            if dev_id in self.client.devices:
                self.current_device = self.client.devices[dev_id]
                self.status_var.set(f"已选中: {self.current_device.name}")
                self._refresh_files()

    def _scan(self):
        """扫描设备"""
        self.status_var.set("正在扫描...")
        self.client.scan()
        self.root.after(2000, lambda: self.status_var.set(
            f"扫描完成，发现 {len(self.client.devices)} 个设备"
        ))

    def _manual_connect_dialog(self):
        """手动连接对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("手动连接")
        dialog.geometry("300x120")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="IP地址:端口").pack(pady=5)
        entry = ttk.Entry(dialog, width=30)
        entry.pack(pady=5)
        entry.insert(0, f":{HTTP_PORT}")
        entry.focus_set()

        def connect():
            addr = entry.get().strip()
            if ':' in addr:
                ip, port = addr.rsplit(':', 1)
                try:
                    port = int(port)
                except:
                    port = HTTP_PORT
            else:
                ip = addr
                port = HTTP_PORT

            dev = DeviceInfo(
                device_id=f"manual-{ip}",
                name=f"手动设备 ({ip})",
                ip=ip,
                port=port,
                platform="Unknown"
            )
            self.client.devices[dev.device_id] = dev
            self._update_device_list()
            self.current_device = dev
            dialog.destroy()
            self.status_var.set(f"已连接: {dev.name}")
            self._refresh_files()

        ttk.Button(dialog, text="连接", command=connect).pack(pady=10)

    def _refresh_files(self):
        """刷新文件列表"""
        if not self.current_device:
            self.status_var.set("请先选择一个设备")
            return

        def fetch():
            try:
                files = self.client.get_files(self.current_device)
                self.root.after(0, lambda: self._update_file_list(files))
                self.root.after(0, lambda: self.status_var.set(
                    f"已连接: {self.current_device.name}，共 {len(files)} 个文件"
                ))
            except Exception as e:
                self.root.after(0, lambda: self.status_var.set(f"错误: {e}"))

        self.status_var.set("正在获取文件列表...")
        threading.Thread(target=fetch, daemon=True).start()

    def _update_file_list(self, files):
        """更新文件列表"""
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)

        for f in files:
            name = f.get('name', '')
            size = f.get('size', 0)
            modified = f.get('modified', '')

            # 格式化大小
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size/1024:.1f} KB"
            else:
                size_str = f"{size/(1024*1024):.1f} MB"

            self.file_tree.insert('', tk.END, iid=name,
                                   values=(name, size_str, modified))

    def _download_selected(self):
        """下载选中文件"""
        selection = self.file_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要下载的文件")
            return

        if not self.current_device:
            messagebox.showwarning("提示", "请先选择一个设备")
            return

        for file_id in selection:
            self._do_download(file_id)

    def _do_download(self, filename):
        """执行下载"""
        def download():
            try:
                save_path = self.download_dir / filename
                self.client.download_file(self.current_device, filename, str(save_path))
                self.root.after(0, lambda: self.status_var.set(f"下载完成: {filename}"))
                self.root.after(0, lambda: messagebox.showinfo("下载完成",
                    f"文件已保存到:\n{save_path}"))
            except Exception as e:
                self.root.after(0, lambda: self.status_var.set(f"下载失败: {e}"))
                self.root.after(0, lambda: messagebox.showerror("下载失败", str(e)))

        self.status_var.set(f"正在下载: {filename}...")
        threading.Thread(target=download, daemon=True).start()

    def _upload_file(self):
        """上传文件"""
        if not self.current_device:
            messagebox.showwarning("提示", "请先选择一个设备")
            return

        filepaths = filedialog.askopenfilenames(title="选择要上传的文件")
        if not filepaths:
            return

        for filepath in filepaths:
            self._do_upload(filepath)

    def _do_upload(self, filepath):
        """执行上传"""
        def upload():
            try:
                result = self.client.upload_file(self.current_device, filepath)
                fname = os.path.basename(filepath)
                self.root.after(0, lambda: self.status_var.set(f"上传成功: {fname}"))
                self.root.after(0, self._refresh_files)
            except Exception as e:
                self.root.after(0, lambda: self.status_var.set(f"上传失败: {e}"))
                self.root.after(0, lambda: messagebox.showerror("上传失败", str(e)))

        fname = os.path.basename(filepath)
        self.status_var.set(f"正在上传: {fname}...")
        threading.Thread(target=upload, daemon=True).start()

    def _delete_selected(self):
        """删除选中文件"""
        selection = self.file_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要删除的文件")
            return

        if not self.current_device:
            messagebox.showwarning("提示", "请先选择一个设备")
            return

        if not messagebox.askyesno("确认删除", f"确定要删除 {len(selection)} 个文件吗？"):
            return

        for filename in selection:
            self._do_delete(filename)

    def _do_delete(self, filename):
        """执行删除"""
        def delete():
            try:
                self.client.delete_file(self.current_device, filename)
                self.root.after(0, lambda: self.status_var.set(f"已删除: {filename}"))
                self.root.after(0, self._refresh_files)
            except Exception as e:
                self.root.after(0, lambda: self.status_var.set(f"删除失败: {e}"))

        threading.Thread(target=delete, daemon=True).start()

    def _search(self):
        """搜索文件"""
        query = self.search_var.get().strip()
        if not query:
            self._refresh_files()
            return

        if not self.current_device:
            self.status_var.set("请先选择一个设备")
            return

        def do_search():
            try:
                files = self.client.search_files(self.current_device, query)
                self.root.after(0, lambda: self._update_file_list(files))
                self.root.after(0, lambda: self.status_var.set(
                    f"搜索 '{query}' 找到 {len(files)} 个文件"
                ))
            except Exception as e:
                self.root.after(0, lambda: self.status_var.set(f"搜索失败: {e}"))

        self.status_var.set(f"正在搜索: {query}...")
        threading.Thread(target=do_search, daemon=True).start()

    def _on_close(self):
        """关闭"""
        self.client.stop_udp()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description='文件共享客户端')
    parser.add_argument('--cli', action='store_true', help='命令行模式')
    parser.add_argument('--scan', action='store_true', help='扫描设备')
    parser.add_argument('--list', metavar='IP', help='列出设备上的文件')
    parser.add_argument('--download', nargs=2, metavar=('IP', 'FILENAME'), help='下载文件')
    parser.add_argument('--upload', nargs=2, metavar=('IP', 'FILEPATH'), help='上传文件')
    parser.add_argument('--server', action='store_true', help='同时启动服务端')
    parser.add_argument('-p', '--port', type=int, default=HTTP_PORT, help='HTTP端口')
    parser.add_argument('-d', '--directory', type=str, default='shared_files', help='共享目录')

    args = parser.parse_args()

    # 同时启动服务端
    if args.server:
        from server import FileShareServer
        server = FileShareServer(port=args.port)
        server.upload_dir = Path(args.directory)
        server.upload_dir.mkdir(exist_ok=True)
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        print(f"服务端已启动在端口 {args.port}")

    if args.cli or args.scan or args.list or args.download or args.upload:
        # 命令行模式
        client = FileShareClient()
        client.start_udp()

        if args.scan:
            print("正在扫描设备...")
            client.scan()
            time.sleep(3)
            print(f"\n发现 {len(client.devices)} 个设备:")
            for dev in client.devices.values():
                print(f"  {dev.name} ({dev.ip}) [{dev.platform}]")

        elif args.list:
            dev = DeviceInfo(device_id="manual", name="manual", ip=args.list)
            try:
                files = client.get_files(dev)
                print(f"\n{args.list} 上的文件:")
                for f in files:
                    size = f.get('size', 0)
                    print(f"  {f['name']} ({size} bytes)")
            except Exception as e:
                print(f"错误: {e}")

        elif args.download:
            ip, filename = args.download
            dev = DeviceInfo(device_id="manual", name="manual", ip=ip)
            save_path = Path.home() / "Downloads" / "FileShare" / filename
            save_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                client.download_file(dev, filename, str(save_path))
                print(f"下载完成: {save_path}")
            except Exception as e:
                print(f"错误: {e}")

        elif args.upload:
            ip, filepath = args.upload
            dev = DeviceInfo(device_id="manual", name="manual", ip=ip)
            try:
                result = client.upload_file(dev, filepath)
                print(f"上传成功: {os.path.basename(filepath)}")
            except Exception as e:
                print(f"错误: {e}")

        client.stop_udp()
    else:
        # GUI 模式
        app = FileShareGUI()
        app.run()


if __name__ == '__main__':
    main()
