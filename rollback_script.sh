#!/bin/bash
# Genesis 项目回滚脚本
# 用法: ./rollback_script.sh [backup_file]

set -e

BACKUP_DIR="/tmp/system_backup_*"
PROJECT_BACKUP="/tmp/genesis_critical_*.tar.gz"

echo "=== Genesis 回滚系统 ==="
echo "1. 检查备份文件..."

# 检查系统备份
if ls -d $BACKUP_DIR 2>/dev/null; then
    LATEST_BACKUP=$(ls -d $BACKUP_DIR | tail -1)
    echo "找到系统备份: $LATEST_BACKUP"
else
    echo "未找到系统备份"
fi

# 检查项目备份
if ls $PROJECT_BACKUP 2>/dev/null; then
    LATEST_PROJECT_BACKUP=$(ls $PROJECT_BACKUP | tail -1)
    echo "找到项目备份: $LATEST_PROJECT_BACKUP"
else
    echo "未找到项目备份"
fi

echo ""
echo "2. 回滚选项:"
echo "   a) 恢复系统配置文件"
echo "   b) 恢复项目关键文件"
echo "   c) 执行系统优化"
echo "   d) 全部执行"
echo "   q) 退出"

read -p "请选择操作 [a/b/c/d/q]: " choice

case $choice in
    a)
        if [ -n "$LATEST_BACKUP" ]; then
            echo "恢复系统配置文件..."
            sudo cp -r "$LATEST_BACKUP"/* /etc/ 2>/dev/null || echo "需要sudo权限"
            echo "系统配置恢复完成"
        else
            echo "没有可用的系统备份"
        fi
        ;;
    b)
        if [ -n "$LATEST_PROJECT_BACKUP" ]; then
            echo "恢复项目关键文件..."
            tar -xzf "$LATEST_PROJECT_BACKUP" -C /home/chendechusn/Genesis
            echo "项目文件恢复完成"
        else
            echo "没有可用的项目备份"
        fi
        ;;
    c)
        echo "执行系统优化..."
        sudo pacman -Sc --noconfirm 2>/dev/null || echo "需要sudo权限"
        sudo journalctl --vacuum-time=3d 2>/dev/null || echo "需要sudo权限"
        sudo sync && echo 3 | sudo tee /proc/sys/vm/drop_caches 2>/dev/null || echo "需要sudo权限"
        echo "系统优化完成"
        ;;
    d)
        echo "执行完整回滚和优化..."
        if [ -n "$LATEST_BACKUP" ]; then
            sudo cp -r "$LATEST_BACKUP"/* /etc/ 2>/dev/null || echo "系统配置恢复需要sudo权限"
        fi
        if [ -n "$LATEST_PROJECT_BACKUP" ]; then
            tar -xzf "$LATEST_PROJECT_BACKUP" -C /home/chendechusn/Genesis
        fi
        sudo pacman -Sc --noconfirm 2>/dev/null || echo "需要sudo权限"
        sudo journalctl --vacuum-time=3d 2>/dev/null || echo "需要sudo权限"
        sudo sync && echo 3 | sudo tee /proc/sys/vm/drop_caches 2>/dev/null || echo "需要sudo权限"
        echo "完整回滚和优化完成"
        ;;
    q)
        echo "退出"
        exit 0
        ;;
    *)
        echo "无效选择"
        ;;
esac

echo ""
echo "=== 当前系统状态 ==="
df -h / | grep -v Filesystem
free -h | grep Mem

echo "回滚操作完成"