#!/bin/bash

echo "=========================================="
echo "🎬 女性情感视频制作系统 - 快速启动"
echo "=========================================="

# 给脚本执行权限
chmod +x emotional_video_maker.py

# 创建必要的目录
mkdir -p images output

echo ""
echo "📁 项目结构已创建:"
echo "├── emotional_video_maker.py    # 主处理脚本"
echo "├── emotional_video_subtitles.srt # 字幕文件"
echo "├── images/                     # 图片素材文件夹"
echo "├── output/                     # 输出文件夹"
echo "└── start_video_maker.sh       # 启动脚本"
echo ""

# 检查素材
echo "📸 素材准备检查:"
if [ -d "images" ] && [ "$(ls -A images/*.jpg 2>/dev/null)" ]; then
    echo "✅ 发现图片素材: $(ls images/*.jpg | wc -l) 张"
else
    echo "⚠️  图片素材文件夹为空"
    echo ""
    echo "💡 快速获取素材方法:"
    echo "1. 打开浏览器访问: https://www.pexels.com/zh-cn/search/romantic%20love/"
    echo "2. 筛选 '方向: 垂直'"
    echo "3. 下载5-10张图片到 'images/' 文件夹"
    echo ""
    echo "或者使用命令行下载示例素材:"
    echo "curl -o images/sample1.jpg https://images.pexels.com/photos/1234567/pexels-photo-1234567.jpeg"
    echo ""
fi

# 检查FFmpeg
echo ""
echo "🔧 系统依赖检查:"
if command -v ffmpeg &> /dev/null; then
    echo "✅ FFmpeg 已安装"
else
    echo "❌ FFmpeg 未安装"
    echo "请运行以下命令安装:"
    echo "  Ubuntu/Debian: sudo apt install ffmpeg"
    echo "  macOS: brew install ffmpeg"
    echo "  CentOS/RHEL: sudo yum install ffmpeg"
    exit 1
fi

# 检查Python
if command -v python3 &> /dev/null; then
    echo "✅ Python3 已安装"
else
    echo "❌ Python3 未安装"
    exit 1
fi

echo ""
echo "🚀 启动选项:"
echo "1. 立即制作视频 (使用现有素材)"
echo "2. 先下载示例素材"
echo "3. 查看详细教程"
echo "4. 退出"
echo ""

read -p "请选择 (1-4): " choice

case $choice in
    1)
        echo "开始制作视频..."
        python3 emotional_video_maker.py
        ;;
    2)
        echo "正在下载示例素材..."
        # 创建示例图片（纯色背景）
        for i in {1..5}; do
            ffmpeg -f lavfi -i "color=c=0x$((RANDOM%256))$((RANDOM%256))$((RANDOM%256)):s=1080x1920:d=1" \
                   -frames:v 1 "images/sample_$i.jpg" 2>/dev/null
        done
        echo "✅ 示例素材已创建到 images/ 文件夹"
        echo "现在可以运行选项1制作视频"
        ;;
    3)
        echo ""
        echo "📚 详细教程:"
        echo "1. 准备5-10张竖屏图片 (1080x1920) 放到 images/ 文件夹"
        echo "2. 可选: 下载背景音乐保存为 background_music.mp3"
        echo "3. 运行: python3 emotional_video_maker.py"
        echo "4. 视频将输出到 output/emotional_video_final.mp4"
        echo ""
        echo "🎯 发布建议:"
        echo "- 最佳时间: 晚上8-10点"
        echo "- 标签: #爱情观 #情感共鸣 #女性成长 #心动瞬间"
        echo "- 文案: '还记得第一次心动是什么感觉吗？'"
        ;;
    4)
        echo "退出系统"
        exit 0
        ;;
    *)
        echo "无效选择"
        ;;
esac

echo ""
echo "=========================================="
echo "🎉 系统准备就绪！"
echo "=========================================="