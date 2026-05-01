#!/bin/bash
# 文件共享系统 - Linux 安装脚本
# 用法: curl -sSL https://raw.githubusercontent.com/asecevb-web/share-system/main/install.sh | bash

set -e

REPO="asecevb-web/share-system"
INSTALL_DIR="$HOME/.local/share/fileshare"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

echo "=========================================="
echo "  文件共享系统 - Linux 安装程序"
echo "=========================================="
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 Python3，请先安装:"
    echo "   Ubuntu/Debian: sudo apt install python3 python3-pip python3-tk"
    echo "   Fedora:        sudo dnf install python3 python3-pip python3-tkinter"
    echo "   Arch:          sudo pacman -S python python-pip tk"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo "✅ Python: $PYTHON_VERSION"

# 检查 Tkinter
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "⚠️  Tkinter 未安装，GUI 模式将不可用"
    echo "   安装命令:"
    echo "   Ubuntu/Debian: sudo apt install python3-tk"
    echo "   Fedora:        sudo dnf install python3-tkinter"
    echo "   Arch:          sudo pacman -S tk"
    echo ""
    echo "   命令行模式仍可使用，继续安装..."
    HAS_GUI=false
else
    echo "✅ Tkinter 已安装"
    HAS_GUI=true
fi

# 安装 requests (可选)
echo ""
echo "正在安装依赖..."
pip3 install --user requests 2>/dev/null || pip install --user requests 2>/dev/null || {
    echo "⚠️  requests 安装失败，将使用 urllib 作为后备"
}

# 创建安装目录
echo ""
echo "正在安装到 $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$DESKTOP_DIR"
mkdir -p "$HOME/Downloads/FileShare"

# 下载文件
echo "正在下载文件..."
cd /tmp

if command -v git &> /dev/null; then
    # 用 git clone
    rm -rf share-system-tmp
    git clone --depth 1 "https://github.com/$REPO.git" share-system-tmp 2>/dev/null || {
        echo "❌ 下载失败，请检查网络连接"
        exit 1
    }
    cp share-system-tmp/client.py "$INSTALL_DIR/"
    cp share-system-tmp/server.py "$INSTALL_DIR/"
    cp share-system-tmp/protocol.py "$INSTALL_DIR/"
    rm -rf share-system-tmp
else
    # 用 curl/wget
    if command -v curl &> /dev/null; then
        curl -sSL "https://raw.githubusercontent.com/$REPO/main/client.py" -o "$INSTALL_DIR/client.py"
        curl -sSL "https://raw.githubusercontent.com/$REPO/main/server.py" -o "$INSTALL_DIR/server.py"
        curl -sSL "https://raw.githubusercontent.com/$REPO/main/protocol.py" -o "$INSTALL_DIR/protocol.py"
    elif command -v wget &> /dev/null; then
        wget -q "https://raw.githubusercontent.com/$REPO/main/client.py" -O "$INSTALL_DIR/client.py"
        wget -q "https://raw.githubusercontent.com/$REPO/main/server.py" -O "$INSTALL_DIR/server.py"
        wget -q "https://raw.githubusercontent.com/$REPO/main/protocol.py" -O "$INSTALL_DIR/protocol.py"
    else
        echo "❌ 需要 git、curl 或 wget 中的一个"
        exit 1
    fi
fi

echo "✅ 文件已下载"

# 创建启动脚本
cat > "$BIN_DIR/fileshare" << 'LAUNCHER'
#!/bin/bash
cd "$HOME/.local/share/fileshare"
python3 client.py "$@"
LAUNCHER
chmod +x "$BIN_DIR/fileshare"

# 创建服务端启动脚本
cat > "$BIN_DIR/fileshare-server" << 'LAUNCHER'
#!/bin/bash
cd "$HOME/.local/share/fileshare"
python3 server.py "$@"
LAUNCHER
chmod +x "$BIN_DIR/fileshare-server"

echo "✅ 启动脚本已创建"

# 创建桌面文件
cat > "$DESKTOP_DIR/fileshare.desktop" << DESKTOP
[Desktop Entry]
Name=文件共享
Comment=局域网文件共享工具
Exec=$BIN_DIR/fileshare
Icon=folder-network
Terminal=false
Type=Application
Categories=Network;FileTransfer;
Keywords=file;share;transfer;lan;
DESKTOP

# 更新桌面数据库
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo "✅ 桌面快捷方式已创建"

# 检查 PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "⚠️  $BIN_DIR 不在 PATH 中"
    echo "   请将以下内容添加到 ~/.bashrc 或 ~/.zshrc:"
    echo ""
    echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""

    # 自动添加到常见 shell 配置
    for rc in ~/.bashrc ~/.zshrc; do
        if [ -f "$rc" ]; then
            if ! grep -q '.local/bin' "$rc"; then
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
                echo "   已添加到 $rc"
            fi
        fi
    done
fi

echo ""
echo "=========================================="
echo "  ✅ 安装完成！"
echo "=========================================="
echo ""
echo "使用方法:"
echo ""
echo "  图形界面 (GUI):"
echo "    fileshare"
echo ""
echo "  命令行模式:"
echo "    fileshare --cli --scan          # 扫描设备"
echo "    fileshare --cli --list <IP>     # 列出文件"
echo "    fileshare --cli --download <IP> <文件名>  # 下载"
echo "    fileshare --cli --upload <IP> <文件路径>   # 上传"
echo ""
echo "  启动服务端:"
echo "    fileshare-server -p 8080 -d ./shared_files"
echo ""
echo "  GUI + 服务端同时启动:"
echo "    fileshare --server"
echo ""
echo "  下载目录: ~/Downloads/FileShare"
echo ""
