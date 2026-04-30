# 文件共享系统 (FileShare)

局域网内 Android/Windows/Mac/Linux 设备之间的文件共享工具。

## 功能
- UDP 广播自动发现设备
- HTTP 文件上传/下载/删除/搜索
- 支持多设备同时连接

## 使用方法

### 1. 桌面端 (Windows/Mac/Linux)
```bash
pip install flask flask-cors
python server.py -p 8080 -d ./shared_files
```

### 2. Android 端
构建 APK 后安装到手机：
- 推送本仓库到 GitHub
- GitHub Actions 自动构建 APK
- 从 Actions Artifacts 下载安装

## 文件说明
- `protocol.py` - 统一协议定义
- `server.py` - 桌面服务端（Windows/Mac/Linux 共用）
- `main.py` - Kivy Android 客户端
- `buildozer.spec` - APK 打包配置
- `.github/workflows/build.yml` - GitHub Actions 自动构建

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
