"""
文件共享服务器
"""

import os
import sys
import uuid
import json
import socket
import platform
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS

from protocol import (
    DeviceInfo, UDPProtocol, HTTPProtocol,
    MessageType, UDP_BROADCAST_PORT, HTTP_PORT, BROADCAST_INTERVAL
)

class FileShareServer:
    def __init__(self, host: str = '0.0.0.0', port: int = HTTP_PORT):
        self.app = Flask(__name__)
        CORS(self.app)

        # 服务器配置
        self.host = host
        self.port = port
        self.device_id = str(uuid.uuid4())
        self.device_name = f"{platform.system()}-Device"

        # 文件存储目录
        self.upload_dir = Path("shared_files")
        self.upload_dir.mkdir(exist_ok=True)

        # 设备信息
        self.device_info = DeviceInfo(
            device_id=self.device_id,
            name=self.device_name,
            ip=self._get_local_ip(),
            port=self.port
        )
        self.device_info.platform = platform.system()

        # 发现的设备
        self.discovered_devices: Dict[str, DeviceInfo] = {}

        # 设置路由
        self._setup_routes()

        # 启动UDP广播和监听
        self.udp_running = True
        self.udp_thread = threading.Thread(target=self._udp_service, daemon=True)

    def _get_local_ip(self) -> str:
        """获取本机IP地址"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

    def _setup_routes(self):
        """设置HTTP路由"""

        @self.app.route('/api/device', methods=['GET'])
        def get_device_info():
            """获取设备信息"""
            return jsonify(HTTPProtocol.create_api_response(
                "success",
                self.device_info.to_dict()
            ))

        @self.app.route('/api/devices', methods=['GET'])
        def get_devices():
            """获取所有发现的设备"""
            devices = [d.to_dict() for d in self.discovered_devices.values()]
            return jsonify(HTTPProtocol.create_api_response(
                "success",
                devices
            ))

        @self.app.route('/api/files', methods=['GET'])
        def list_files():
            """列出文件"""
            try:
                files = []
                for file_path in self.upload_dir.iterdir():
                    if file_path.is_file():
                        stat = file_path.stat()
                        files.append({
                            "name": file_path.name,
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "type": file_path.suffix.lower()
                        })
                return jsonify(HTTPProtocol.create_file_list(files))
            except Exception as e:
                return jsonify(HTTPProtocol.create_api_response(
                    "error",
                    message=str(e)
                )), 500

        @self.app.route('/api/files/<filename>', methods=['GET'])
        def download_file(filename: str):
            """下载文件"""
            try:
                file_path = self.upload_dir / filename
                if not file_path.exists():
                    abort(404)
                return send_file(
                    file_path,
                    as_attachment=True,
                    download_name=filename
                )
            except Exception as e:
                abort(500)

        @self.app.route('/api/files', methods=['POST'])
        def upload_file():
            """上传文件"""
            try:
                if 'file' not in request.files:
                    return jsonify(HTTPProtocol.create_api_response(
                        "error",
                        message="No file provided"
                    )), 400

                file = request.files['file']
                if file.filename == '':
                    return jsonify(HTTPProtocol.create_api_response(
                        "error",
                        message="No file selected"
                    )), 400

                # 安全文件名
                filename = self._secure_filename(file.filename)
                file_path = self.upload_dir / filename
                file.save(file_path)

                return jsonify(HTTPProtocol.create_upload_response(
                    filename,
                    file_path.stat().st_size
                )), 201
            except Exception as e:
                return jsonify(HTTPProtocol.create_api_response(
                    "error",
                    message=str(e)
                )), 500

        @self.app.route('/api/files/<filename>', methods=['DELETE'])
        def delete_file(filename: str):
            """删除文件"""
            try:
                file_path = self.upload_dir / filename
                if not file_path.exists():
                    abort(404)

                file_path.unlink()
                return jsonify(HTTPProtocol.create_api_response(
                    "success",
                    message="File deleted"
                ))
            except Exception as e:
                return jsonify(HTTPProtocol.create_api_response(
                    "error",
                    message=str(e)
                )), 500

        @self.app.route('/api/search', methods=['GET'])
        def search_files():
            """搜索文件"""
            query = request.args.get('q', '').lower()
            if not query:
                return jsonify(HTTPProtocol.create_api_response(
                    "error",
                    message="Query required"
                )), 400

            try:
                files = []
                for file_path in self.upload_dir.iterdir():
                    if file_path.is_file() and query in file_path.name.lower():
                        stat = file_path.stat()
                        files.append({
                            "name": file_path.name,
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "type": file_path.suffix.lower()
                        })
                return jsonify(HTTPProtocol.create_file_list(files))
            except Exception as e:
                return jsonify(HTTPProtocol.create_api_response(
                    "error",
                    message=str(e)
                )), 500

    def _secure_filename(self, filename: str) -> str:
        """生成安全文件名"""
        import re
        filename = re.sub(r'[^\w\s.-]', '', filename)
        filename = re.sub(r'[-\s]+', '-', filename).strip('-_')
        if not filename:
            filename = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return filename

    def _udp_service(self):
        """UDP广播和监听服务"""
        import time

        # 创建广播套接字
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1.0)

        # 绑定到广播端口
        try:
            sock.bind(('', UDP_BROADCAST_PORT))
        except socket.error:
            print(f"Warning: Could not bind to port {UDP_BROADCAST_PORT}")
            return

        last_broadcast = datetime.min

        while self.udp_running:
            try:
                # 发送广播
                now = datetime.now()
                if (now - last_broadcast).seconds >= BROADCAST_INTERVAL:
                    message = UDPProtocol.create_broadcast_message(
                        self.device_info,
                        MessageType.DEVICE_ANNOUNCE
                    )
                    UDPProtocol.broadcast(message)
                    last_broadcast = now

                # 接收广播
                try:
                    data, addr = sock.recvfrom(1024)
                    message = UDPProtocol.parse_message(data)

                    if message and message.get('type') == MessageType.DEVICE_ANNOUNCE:
                        device_data = message.get('data', {})
                        device_info = DeviceInfo.from_dict(device_data)

                        # 不添加自己
                        if device_info.device_id != self.device_id:
                            self.discovered_devices[device_info.device_id] = device_info
                            print(f"Discovered device: {device_info.name} ({device_info.ip})")
                except socket.timeout:
                    continue

            except Exception as e:
                print(f"UDP service error: {e}")
                time.sleep(1)

        sock.close()

    def start(self):
        """启动服务器"""
        print(f"Starting FileShare Server...")
        print(f"Device: {self.device_name}")
        print(f"IP: {self.device_info.ip}:{self.port}")
        print(f"Shared directory: {self.upload_dir.absolute()}")

        # 启动UDP服务
        self.udp_thread.start()

        # 启动HTTP服务器
        self.app.run(
            host=self.host,
            port=self.port,
            debug=False,
            use_reloader=False
        )

    def stop(self):
        """停止服务器"""
        self.udp_running = False
        if self.udp_thread.is_alive():
            self.udp_thread.join(timeout=2)

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='File Share Server')
    parser.add_argument('-p', '--port', type=int, default=HTTP_PORT,
                        help=f'HTTP port (default: {HTTP_PORT})')
    parser.add_argument('-d', '--directory', type=str, default='shared_files',
                        help='Shared directory')

    args = parser.parse_args()

    server = FileShareServer(port=args.port)
    server.upload_dir = Path(args.directory)
    server.upload_dir.mkdir(exist_ok=True)

    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.stop()

if __name__ == '__main__':
    main()
