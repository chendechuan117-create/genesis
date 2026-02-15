#!/bin/bash
# 修复网络超时问题的脚本

echo "=== 修复网络超时问题 ==="

# 1. 修复MTU设置
echo "1. 检查并修复MTU设置..."
CURRENT_MTU=$(ip link show eno1 | grep -o 'mtu [0-9]*' | awk '{print $2}')
if [ "$CURRENT_MTU" -lt 1400 ]; then
    echo "  当前MTU: $CURRENT_MTU (异常低)"
    sudo ip link set eno1 mtu 1500
    echo "  已修复MTU为1500"
else
    echo "  当前MTU: $CURRENT_MTU (正常)"
fi

# 2. 清除代理设置
echo "2. 清除代理设置..."
unset all_proxy http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
echo "  已清除所有代理环境变量"

# 3. 测试网络连接
echo "3. 测试网络连接..."
echo "  Ping测试:"
ping -c 3 8.8.8.8 | grep -E "(packet loss|time=|PING)"

# 4. 检查DNS
echo "4. DNS配置:"
cat /etc/resolv.conf | grep nameserver

# 5. 建议永久修复
echo ""
echo "=== 永久修复建议 ==="
echo "1. 编辑 ~/.bashrc 或 ~/.zshrc，移除代理设置"
echo "2. 检查NetworkManager配置，确保MTU设置正确"
echo "3. 考虑更换DNS服务器为 8.8.8.8 或 1.1.1.1"

echo ""
echo "修复完成！"