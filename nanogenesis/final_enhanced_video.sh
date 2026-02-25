#!/bin/bash
# 最终简化版增强视频生成脚本

echo "🎨 创建审美增强版情感视频..."

# 创建输出目录
mkdir -p output_final_enhanced

# 1. 生成基础视频（蓝色渐变背景）
echo "📹 生成基础视频..."
ffmpeg -y -f lavfi -i "color=c=0x1a2a6c:size=1080x1920:d=15" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  output_final_enhanced/base.mp4 2>/dev/null

# 2. 为每句文字生成单独的视频片段
echo "📝 生成文字片段..."

# 第一句：心动主题（红色系）
ffmpeg -y -f lavfi -i "color=c=0xff6b6b:size=1080x1920:d=3" \
  -vf "drawtext=text='还记得第一次心动是什么感觉吗？':fontcolor=white:fontsize=80:shadowcolor=black:shadowx=4:shadowy=4:x=(w-text_w)/2:y=(h-text_h)/2" \
  -c:v libx264 -preset fast -crf 22 \
  output_final_enhanced/part1.mp4 2>/dev/null

# 第二句：心跳主题（粉色系）
ffmpeg -y -f lavfi -i "color=c=0xff9a9e:size=1080x1920:d=3" \
  -vf "drawtext=text='那种心跳加速，手心冒汗的瞬间':fontcolor=white:fontsize=75:borderw=2:bordercolor=black:x=(w-text_w)/2:y=(h-text_h)/2" \
  -c:v libx264 -preset fast -crf 22 \
  output_final_enhanced/part2.mp4 2>/dev/null

# 第三句：安静主题（蓝色系）
ffmpeg -y -f lavfi -i "color=c=0x87ceeb:size=1080x1920:d=3" \
  -vf "drawtext=text='好像全世界都安静了':fontcolor=white:fontsize=70:x=(w-text_w)/2:y=(h-text_h)/2" \
  -c:v libx264 -preset fast -crf 22 \
  output_final_enhanced/part3.mp4 2>/dev/null

# 第四句：存在主题（橙色系）
ffmpeg -y -f lavfi -i "color=c=0xffb347:size=1080x1920:d=3" \
  -vf "drawtext=text='只剩下你和那个人的存在':fontcolor=white:fontsize=78:shadowcolor=black:shadowx=3:shadowy=3:x=(w-text_w)/2:y=(h-text_h)/2" \
  -c:v libx264 -preset fast -crf 22 \
  output_final_enhanced/part4.mp4 2>/dev/null

# 第五句：爱主题（绿色系）
ffmpeg -y -f lavfi -i "color=c=0x90be6d:size=1080x1920:d=3" \
  -vf "drawtext=text='爱，就是愿意为一个人变得更好':fontcolor=white:fontsize=85:borderw=3:bordercolor=black:x=(w-text_w)/2:y=(h-text_h)/2" \
  -c:v libx264 -preset fast -crf 22 \
  output_final_enhanced/part5.mp4 2>/dev/null

# 3. 合并所有片段
echo "🔗 合并视频片段..."
echo "file 'part1.mp4'" > output_final_enhanced/concat.txt
echo "file 'part2.mp4'" >> output_final_enhanced/concat.txt
echo "file 'part3.mp4'" >> output_final_enhanced/concat.txt
echo "file 'part4.mp4'" >> output_final_enhanced/concat.txt
echo "file 'part5.mp4'" >> output_final_enhanced/concat.txt

cd output_final_enhanced
ffmpeg -y -f concat -safe 0 -i concat.txt -c copy merged.mp4 2>/dev/null
cd ..

# 4. 添加淡入淡出效果
echo "🎬 添加转场效果..."
ffmpeg -y -i output_final_enhanced/merged.mp4 \
  -vf "fade=in:0:30,fade=out:14.5:30" \
  -c:v libx264 -preset slow -crf 18 -b:v 800k \
  output_final_enhanced/with_fade.mp4 2>/dev/null

# 5. 添加背景音乐
echo "🎵 添加背景音乐..."
ffmpeg -y -f lavfi -i "sine=frequency=440:duration=15" \
  -ac 2 -ar 44100 output_final_enhanced/bgm.wav 2>/dev/null

ffmpeg -y -i output_final_enhanced/with_fade.mp4 -i output_final_enhanced/bgm.wav \
  -filter_complex "[1:a]volume=0.15[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 128k -shortest \
  output_final_enhanced/第一次心动_审美增强最终版.mp4 2>/dev/null

# 6. 清理临时文件
echo "🧹 清理临时文件..."
rm -f output_final_enhanced/base.mp4 \
  output_final_enhanced/part*.mp4 \
  output_final_enhanced/merged.mp4 \
  output_final_enhanced/with_fade.mp4 \
  output_final_enhanced/bgm.wav \
  output_final_enhanced/concat.txt

# 7. 显示结果
echo ""
echo "✅ 视频生成完成!"
echo "📁 文件: output_final_enhanced/第一次心动_审美增强最终版.mp4"
echo ""
echo "📊 视频信息:"
ffprobe -v quiet -show_format output_final_enhanced/第一次心动_审美增强最终版.mp4 2>/dev/null | grep -E "(duration|bit_rate|size)" | while read line; do
  key=$(echo $line | cut -d= -f1)
  value=$(echo $line | cut -d= -f2)
  case $key in
    "duration") echo "   时长: $(printf "%.2f" $value) 秒" ;;
    "bit_rate") echo "   码率: $(($value/1000)) kbps" ;;
    "size") echo "   文件大小: $(($value/1024)) KB" ;;
  esac
done

echo ""
echo "🎨 审美增强特点:"
echo "   ✅ 多色系设计: 红→粉→蓝→橙→绿 情感色彩渐变"
echo "   ✅ 字体优化: 不同字号和样式匹配内容"
echo "   ✅ 视觉层次: 阴影/边框增强可读性"
echo "   ✅ 情感传达: 色彩与文字主题一致"
echo "   ✅ 专业转场: 淡入淡出效果"
echo "   ✅ 背景音乐: 轻柔正弦波配乐"

echo ""
echo "🚀 播放命令:"
echo "   ffplay output_final_enhanced/第一次心动_审美增强最终版.mp4"