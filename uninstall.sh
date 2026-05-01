#!/bin/bash
# 文件共享系统 - Linux 卸载脚本

set -e

INSTALL_DIR="$HOME/.local/share/fileshare"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

echo "正在卸载文件共享系统..."

# 删除安装目录
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "✅ 已删除 $INSTALL_DIR"
fi

# 删除启动脚本
for f in "$BIN_DIR/fileshare" "$BIN_DIR/fileshare-server"; do
    if [ -f "$f" ]; then
        rm -f "$f"
        echo "✅ 已删除 $f"
    fi
done

# 删除桌面文件
if [ -f "$DESKTOP_DIR/fileshare.desktop" ]; then
    rm -f "$DESKTOP_DIR/fileshare.desktop"
    echo "✅ 已删除桌面快捷方式"
fi

# 更新桌面数据库
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo ""
echo "✅ 卸载完成！"
echo "注意: ~/Downloads/FileShare 目录未删除（保留已下载的文件）"
