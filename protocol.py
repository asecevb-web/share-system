"""
文件共享系统统一协议
"""

import json
import socket
import struct
from datetime import datetime
from typing import Dict, List, Optional

# 协议常量
PROTOCOL_VERSION = "1.0"
UDP_BROADCAST_PORT = 5555
HTTP_PORT = 8080
BROADCAST_INTERVAL = 30  # 广播间隔(秒)

class MessageType:
    DEVICE_ANNOUNCE = "announce"
    DEVICE_REQUEST = "request"
    DEVICE_RESPONSE = "response"
    FILE_LIST = "file_list"
    FILE_UPLOAD = "upload"
    FILE_DOWNLOAD = "download"

class DeviceInfo:
    def __init__(self, device_id: str, name: str, ip: str, port: int = HTTP_PORT):
        self.device_id = device_id
        self.name = name
        self.ip = ip
        self.port = port
        self.last_seen = datetime.now()
        self.platform = "unknown"

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "ip": self.ip,
            "port": self.port,
            "platform": self.platform,
            "last_seen": self.last_seen.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DeviceInfo':
        info = cls(
            device_id=data.get("device_id", ""),
            name=data.get("name", ""),
            ip=data.get("ip", ""),
            port=data.get("port", HTTP_PORT)
        )
        info.platform = data.get("platform", "unknown")
        if "last_seen" in data:
            try:
                info.last_seen = datetime.fromisoformat(data["last_seen"])
            except ValueError:
                info.last_seen = datetime.now()
        return info

class UDPProtocol:
    @staticmethod
    def create_broadcast_message(device_info: DeviceInfo, message_type: str) -> bytes:
        """创建UDP广播消息"""
        message = {
            "version": PROTOCOL_VERSION,
            "type": message_type,
            "data": device_info.to_dict(),
            "timestamp": datetime.now().isoformat()
        }
        return json.dumps(message).encode('utf-8')

    @staticmethod
    def parse_message(data: bytes) -> Optional[Dict]:
        """解析UDP消息"""
        try:
            return json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    @staticmethod
    def broadcast(message: bytes, port: int = UDP_BROADCAST_PORT):
        """广播消息"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.sendto(message, ('', port))
        finally:
            sock.close()

class HTTPProtocol:
    @staticmethod
    def create_api_response(status: str, data: any = None, message: str = "") -> dict:
        """创建API响应"""
        return {
            "status": status,
            "data": data,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def create_file_list(files: List[Dict]) -> dict:
        """创建文件列表响应"""
        return HTTPProtocol.create_api_response(
            "success",
            {
                "files": files,
                "count": len(files)
            }
        )

    @staticmethod
    def create_upload_response(filename: str, size: int) -> dict:
        """创建上传响应"""
        return HTTPProtocol.create_api_response(
            "success",
            {
                "filename": filename,
                "size": size
            }
        )
