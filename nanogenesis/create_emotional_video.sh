#!/bin/bash

# 女性情感视频创建脚本
# 主题：女孩如何建立自信
# 时长：30秒

echo "🎬 开始创建女性情感视频..."
echo "主题：女孩如何建立自信"
echo "时长：30秒"

# 检查FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ 错误：FFmpeg未安装"
    echo "请安装FFmpeg：sudo apt install ffmpeg 或 brew install ffmpeg"
    exit 1
fi

echo "✅ FFmpeg已安装：$(ffmpeg -version | head -n1)"

# 创建临时目录
mkdir -p temp_video
mkdir -p output

# 步骤1：创建测试视频（使用颜色源）
echo "📹 步骤1：创建测试视频素材..."
ffmpeg -f lavfi -i color=c=0x87CEEB:s=1080x1920:d=10 -f lavfi -i anullsrc=r=44100:cl=stereo -t 10 -c:v libx264 -c:a aac temp_video/part1.mp4 -y
ffmpeg -f lavfi -i color=c=0xFFB6C1:s=1080x1920:d=10 -f lavfi -i anullsrc=r=44100:cl=stereo -t 10 -c:v libx264 -c:a aac temp_video/part2.mp4 -y
ffmpeg -f lavfi -i color=c=0x98FB98:s=1080x1920:d=10 -f lavfi -i anullsrc=r=44100:cl=stereo -t 10 -c:v libx264 -c:a aac temp_video/part3.mp4 -y

# 步骤2：合并视频
echo "🔗 步骤2：合并视频片段..."
ffmpeg -i temp_video/part1.mp4 -i temp_video/part2.mp4 -i temp_video/part3.mp4 -filter_complex "[0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1" -c:v libx264 -c:a aac temp_video/merged.mp4 -y

# 步骤3：添加字幕
echo "📝 步骤3：添加字幕..."
ffmpeg -i temp_video/merged.mp4 -vf "subtitles=女性情感_自信成长.srt:force_style='FontName=Microsoft YaHei,FontSize=48,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BackColour=&H80000000,BorderStyle=3,Outline=2,Shadow=1'" -c:v libx264 -c:a copy output/女性情感_自信成长_带字幕.mp4 -y

# 步骤4：添加背景音乐（创建简单音乐）
echo "🎵 步骤4：添加背景音乐..."
# 创建简单的背景音乐（正弦波）
ffmpeg -f lavfi -i "sine=frequency=440:duration=30" -c:a aac temp_video/bg_music.aac -y

# 混合音频
ffmpeg -i output/女性情感_自信成长_带字幕.mp4 -i temp_video/bg_music.aac -filter_complex "[0:a]volume=0.7[a0];[1:a]volume=0.3[a1];[a0][a1]amix=inputs=2:duration=first" -c:v copy -c:a aac -b:a 192k output/女性情感_自信成长_最终版.mp4 -y

# 步骤5：添加片头片尾
echo "🎬 步骤5：添加片头片尾..."
# 创建片头
ffmpeg -f lavfi -i color=c=0x000000:s=1080x1920:d=2 -f lavfi -i anullsrc=r=44100:cl=stereo -t 2 -c:v libx264 -c:a aac temp_video/intro.mp4 -y
# 创建片尾
ffmpeg -f lavfi -i color=c=0x000000:s=1080x1920:d=2 -f lavfi -i anullsrc=r=44100:cl=stereo -t 2 -c:v libx264 -c:a aac temp_video/outro.mp4 -y

# 最终合并
ffmpeg -i temp_video/intro.mp4 -i output/女性情感_自信成长_最终版.mp4 -i temp_video/outro.mp4 -filter_complex "[0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1" -c:v libx264 -c:a aac output/女性情感_自信成长_完整版.mp4 -y

# 清理临时文件
rm -rf temp_video

echo ""
echo "✅ 视频创建完成！"
echo "📁 输出文件："
ls -lh output/
echo ""
echo "🎬 视频信息："
ffmpeg -i output/女性情感_自信成长_完整版.mp4 2>&1 | grep -E "Duration|Stream|bitrate"
echo ""
echo "🚀 视频已准备好：output/女性情感_自信成长_完整版.mp4"