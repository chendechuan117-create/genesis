#!/bin/bash

# 测试博客发布脚本

echo "=== 测试Genesis博客发布系统 ==="
echo ""

# 检查n8n服务
echo "1. 检查n8n服务状态..."
if docker ps | grep -q n8n-chinese; then
    echo "   ✓ n8n容器正在运行"
else
    echo "   ✗ n8n容器未运行"
    exit 1
fi

# 检查n8n Web界面
echo "2. 检查n8n Web界面..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:5679/")
if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✓ n8n Web界面可访问 (HTTP $HTTP_CODE)"
else
    echo "   ✗ n8n Web界面不可访问 (HTTP $HTTP_CODE)"
fi

# 检查工作流文件
echo "3. 检查工作流配置..."
if [ -f "/home/chendechusn/Genesis/Genesis/n8n-workflows/blog-publish-workflow.json" ]; then
    echo "   ✓ 工作流配置文件存在"
    # 检查JSON格式
    if python3 -m json.tool "/home/chendechusn/Genesis/Genesis/n8n-workflows/blog-publish-workflow.json" > /dev/null 2>&1; then
        echo "   ✓ 工作流JSON格式正确"
    else
        echo "   ✗ 工作流JSON格式错误"
    fi
else
    echo "   ✗ 工作流配置文件不存在"
fi

# 检查发布脚本
echo "4. 检查发布脚本..."
if [ -f "/home/chendechusn/Genesis/Genesis/scripts/publish-blog.sh" ]; then
    echo "   ✓ 发布脚本存在"
    if [ -x "/home/chendechusn/Genesis/Genesis/scripts/publish-blog.sh" ]; then
        echo "   ✓ 发布脚本可执行"
    else
        echo "   ✗ 发布脚本不可执行"
    fi
else
    echo "   ✗ 发布脚本不存在"
fi

# 检查博客文件
echo "5. 检查博客文件..."
BLOG_FILE="/home/chendechusn/Genesis/Genesis/blog/genesis-introduction.md"
if [ -f "$BLOG_FILE" ]; then
    echo "   ✓ 示例博客文件存在: $BLOG_FILE"
    FILE_SIZE=$(stat -c%s "$BLOG_FILE")
    echo "   ✓ 文件大小: $FILE_SIZE 字节"
else
    echo "   ✗ 示例博客文件不存在"
fi

# 检查工作流是否在n8n容器中
echo "6. 检查工作流是否已导入n8n..."
if docker exec n8n-chinese ls -la /home/node/workflows/blog-publish-workflow.json > /dev/null 2>&1; then
    echo "   ✓ 工作流已导入n8n容器"
else
    echo "   ✗ 工作流未导入n8n容器"
fi

echo ""
echo "=== 测试总结 ==="
echo ""
echo "下一步操作："
echo "1. 访问 http://localhost:5679 登录n8n (用户名: admin, 密码: admin123)"
echo "2. 在n8n界面中激活 'Genesis博客自动化发布工作流'"
echo "3. 运行测试命令："
echo "   ./scripts/publish-blog.sh /home/chendechusn/Genesis/Genesis/blog/genesis-introduction.md"
echo ""
echo "工作流配置详情："
echo "- Webhook路径: /webhook/blog-publish"
echo "- 输入参数: filePath (博客文件路径)"
echo "- 输出: 格式化后的内容，准备发布到各平台"
echo ""
echo "支持的平台："
echo "- 知乎"
echo "- 掘金" 
echo "- V2EX"