# 文件共享系统 (FileShare)

局域网内 Android/Linux/Windows/Mac 设备之间的文件共享工具。

## 功能

- UDP 广播自动发现设备
- HTTP 文件上传/下载/删除/搜索
- 支持多设备同时连接
- Android 客户端 (Kivy)
- Linux 客户端 (Tkinter GUI + 命令行)
- 跨平台互通

## 快速开始

### Linux 安装 (一键安装)

```bash
# 下载安装脚本
curl -sSL https://raw.githubusercontent.com/asecevb-web/share-system/main/install.sh | bash

# 启动图形界面
fileshare

# 或命令行模式
fileshare --cli --scan
```

### Linux 手动安装

```bash
# 安装依赖
pip install requests
# Ubuntu/Debian 还需要: sudo apt install python3-tk

# 下载文件
git clone https://github.com/asecevb-web/share-system.git
cd share-system

# 启动客户端 (GUI)
python3 client.py

# 启动客户端 (命令行)
python3 client.py --cli --scan
python3 client.py --cli --list 192.168.1.100
python3 client.py --cli --download 192.168.1.100 file.txt
python3 client.py --cli --upload 192.168.1.100 ./myfile.txt

# 启动服务端
python3 server.py -p 8080 -d ./shared_files

# 同时启动客户端和服务端
python3 client.py --server
```

### Android 安装

从 GitHub Actions 下载最新 APK:
1. 打开 [Actions 页面](https://github.com/asecevb-web/share-system/actions)
2. 点击最新的构建
3. 下载 `fileshare-apk-16kb` 中的 APK
4. 安装到手机

## 使用场景

### 场景 1: Linux ↔ Android 互传文件

1. Linux 端启动服务端:
   ```bash
   fileshare-server -p 8080 -d ~/共享文件
   ```

2. Android 端扫描设备，选择 Linux 设备

3. 在 Android 端浏览、下载、上传文件

### 场景景 2: Linux ↔ Linux 互传

1. 两台 Linux 都运行:
   ```bash
   fileshare --server
   ```

2. 自动发现对方，互相传文件

### 场景 3: 命令行快速传输

```bash
# 扫描网络中的设备
fileshare --cli --scan

# 从指定设备下载文件
fileshare --cli --download 192.168.1.100 document.pdf

# 上传文件到指定设备
fileshare --cli --upload 192.168.1.100 ./photo.jpg
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/device | GET | 获取设备信息 |
| /api/devices | GET | 获取所有发现设备 |
| /api/files | GET | 列出文件 |
| /api/files | POST | 上传文件 |
| /api/files/<name> | GET | 下载文件 |
| /api/files/<name> | DELETE | 删除文件 |
| /api/search?q=xxx | GET | 搜索文件 |

## 协议说明

### UDP 广播 (端口 5555)

设备通过 UDP 广播自动发现，消息格式:
```json
{
    "version": "1.0",
    "type": "announce",
    "data": {
        "device_id": "unique-id",
        "name": "设备名",
        "ip": "192.168.1.100",
        "port": 8080,
        "platform": "Linux/Android/Windows/Mac"
    },
    "timestamp": "2026-05-01T12:00:00"
}
```

### HTTP API (端口 8080)

所有 API 返回统一格式:
```json
{
    "status": "success/error",
    "data": {...},
    "message": "",
    "timestamp": "2026-05-01T12:00:00"
}
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `client.py` | Linux 客户端 (GUI + 命令行) |
| `server.py` | 桌面服务端 (Windows/Mac/Linux) |
| `main.py` | Android 客户端 (Kivy) |
| `protocol.py` | 统一协议定义 |
| `buildozer.spec` | APK 打包配置 |
| `install.sh` | Linux 安装脚本 |
| `uninstall.sh` | Linux 卸载脚本 |
| `.github/workflows/build.yml` | GitHub Actions 自动构建 |

## 卸载

```bash
# Linux
curl -sSL https://raw.githubusercontent.com/asecevb-web/share-system/main/uninstall.sh | bash

# 或手动
~/.local/share/fileshare/uninstall.sh
```

## 许可证

MIT License
