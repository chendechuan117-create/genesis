#!/bin/bash

# 女性情感视频一键制作脚本
echo "🎬 启动女性情感视频制作系统"
echo "================================"

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装，请先安装Python3"
    exit 1
fi

# 检查FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  FFmpeg 未安装，尝试安装..."
    
    # 检测系统类型
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt update && sudo apt install -y ffmpeg
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install ffmpeg
    else
        echo "❌ 不支持的系统，请手动安装FFmpeg"
        exit 1
    fi
fi

# 创建必要的目录
mkdir -p images output

# 检查素材
echo "📁 检查素材准备情况..."
if [ ! -d "images" ] || [ -z "$(ls -A images/*.jpg 2>/dev/null)" ]; then
    echo "⚠️  图片素材文件夹为空"
    echo "请下载5-10张竖屏图片到 'images/' 文件夹"
    echo "推荐尺寸: 1080x1920像素"
    echo ""
    echo "💡 快速获取素材:"
    echo "1. 访问 https://www.pexels.com/zh-cn/"
    echo "2. 搜索: 'love romantic couple'"
    echo "3. 选择竖屏图片下载到 images/ 文件夹"
    echo ""
    read -p "是否继续？(y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
fi

# 检查字幕文件
if [ ! -f "emotional_video_subtitles.srt" ]; then
    echo "❌ 字幕文件不存在，正在生成..."
    cat > emotional_video_subtitles.srt << 'EOF'
1
00:00:00,000 --> 00:00:03,000
还记得第一次心动是什么感觉吗？

2
00:00:03,001 --> 00:00:06,000
那种心跳加速，手心冒汗的瞬间

3
00:00:06,001 --> 00:00:09,000
好像全世界都安静了

4
00:00:09,001 --> 00:00:12,000
只剩下你和那个人的存在

5
00:00:12,001 --> 00:00:15,000
爱，就是愿意为一个人变得更好
EOF
    echo "✅ 字幕文件已生成"
fi

# 运行视频制作脚本
echo "🚀 开始制作视频..."
python3 emotional_video_maker.py

# 检查输出
if [ -f "output/emotional_video_final.mp4" ]; then
    echo ""
    echo "🎉 视频制作完成！"
    echo "📁 输出文件: output/emotional_video_final.mp4"
    echo ""
    echo "📋 下一步建议:"
    echo "1. 预览视频: vlc output/emotional_video_final.mp4"
    echo "2. 上传到抖音/小红书"
    echo "3. 使用标签: #爱情观 #情感共鸣 #女性成长"
else
    echo "❌ 视频制作失败，请检查错误信息"
fi