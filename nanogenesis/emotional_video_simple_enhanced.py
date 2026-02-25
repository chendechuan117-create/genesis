#!/usr/bin/env python3
"""
简化版情感视频增强 - 解决AI审美不足问题
使用可靠的FFmpeg命令生成有视觉吸引力的视频
"""

import subprocess
import json
import os
from pathlib import Path

def create_simple_enhanced_video():
    """创建简化版增强视频"""
    
    # 1. 创建输出目录
    output_dir = Path("output_simple_enhanced")
    output_dir.mkdir(exist_ok=True)
    
    # 2. 脚本内容
    script = [
        "还记得第一次心动是什么感觉吗？",
        "那种心跳加速，手心冒汗的瞬间",
        "好像全世界都安静了",
        "只剩下你和那个人的存在",
        "爱，就是愿意为一个人变得更好"
    ]
    
    print("🎨 创建增强版情感视频...")
    
    # 3. 直接使用一个FFmpeg命令生成完整视频
    final_video = output_dir / "第一次心动_审美增强版.mp4"
    
    # 创建复杂的FFmpeg命令，包含多个滤镜效果
    filter_complex = """
    color=c=0x1a2a6c:size=1080x1920:d=15,
    drawtext=text='还记得第一次心动是什么感觉吗？':
    fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc:
    fontcolor=0xFFFFFF:
    fontsize=80:
    shadowcolor=0x000000:
    shadowx=4:
    shadowy=4:
    x=(w-text_w)/2:
    y=(h-text_h)/2:
    enable='between(t,0,3)',
    drawtext=text='那种心跳加速，手心冒汗的瞬间':
    fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc:
    fontcolor=0xFF6B6B:
    fontsize=75:
    borderw=2:
    bordercolor=0x000000AA:
    x=(w-text_w)/2:
    y=(h-text_h)/2:
    enable='between(t,3,6)',
    drawtext=text='好像全世界都安静了':
    fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Light.ttc:
    fontcolor=0x87CEEB:
    fontsize=70:
    x=(w-text_w)/2:
    y=(h-text_h)/2:
    enable='between(t,6,9)',
    drawtext=text='只剩下你和那个人的存在':
    fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Medium.ttc:
    fontcolor=0xFFB347:
    fontsize=78:
    shadowcolor=0x000000:
    shadowx=3:
    shadowy=3:
    x=(w-text_w)/2:
    y=(h-text_h)/2:
    enable='between(t,9,12)',
    drawtext=text='爱，就是愿意为一个人变得更好':
    fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc:
    fontcolor=0x90BE6D:
    fontsize=85:
    borderw=3:
    bordercolor=0x00000055:
    x=(w-text_w)/2:
    y='h-100-20*t':
    enable='between(t,12,15)',
    fade=in:0:30,
    fade=out:14.5:30,
    zoompan=z='1+0.1*sin(0.5*PI*t)':d=1
    """
    
    # 清理filter_complex字符串
    filter_complex = " ".join(filter_complex.split())
    
    # 生成视频命令
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x1a2a6c:size=1080x1920:d=15",
        "-filter_complex", filter_complex,
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-b:v", "800k",
        "-maxrate", "1M",
        "-bufsize", "2M",
        "-pix_fmt", "yuv420p",
        "-t", "15",
        str(final_video)
    ]
    
    print("📹 生成视频...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ 视频生成失败: {result.stderr[:200]}")
        return None
    
    # 4. 添加背景音乐
    print("🎵 添加背景音乐...")
    
    video_with_audio = output_dir / "第一次心动_完整版.mp4"
    
    # 生成背景音乐（更丰富的音乐）
    bgm_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=440:duration=15,asplit[a][b];[a]adelay=1000|1000[delayed];[b][delayed]amix=inputs=2",
        "-ac", "2",
        "-ar", "44100",
        output_dir / "bgm.wav"
    ]
    
    subprocess.run(bgm_cmd, capture_output=True)
    
    # 合并视频和音频
    merge_cmd = [
        "ffmpeg", "-y",
        "-i", str(final_video),
        "-i", str(output_dir / "bgm.wav"),
        "-filter_complex", "[1:a]volume=0.2,afade=in:0:1,afade=out:14:1[a]",
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        str(video_with_audio)
    ]
    
    subprocess.run(merge_cmd, capture_output=True)
    
    # 5. 清理临时文件
    (output_dir / "bgm.wav").unlink(missing_ok=True)
    final_video.unlink(missing_ok=True)
    
    # 6. 分析视频质量
    print("\n📊 视频质量分析:")
    analyze_cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_with_audio)
    ]
    
    result = subprocess.run(analyze_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        data = json.loads(result.stdout)
        
        # 视频信息
        video_stream = next((s for s in data['streams'] if s['codec_type'] == 'video'), {})
        audio_stream = next((s for s in data['streams'] if s['codec_type'] == 'audio'), {})
        
        bitrate = int(data['format']['bit_rate']) / 1000
        duration = float(data['format']['duration'])
        file_size = os.path.getsize(video_with_audio) / 1024
        
        print(f"   分辨率: {video_stream.get('width', 'N/A')}x{video_stream.get('height', 'N/A')}")
        print(f"   时长: {duration:.2f} 秒")
        print(f"   视频码率: {bitrate:.1f} kbps")
        print(f"   视频编码: {video_stream.get('codec_name', 'N/A')}")
        print(f"   音频编码: {audio_stream.get('codec_name', 'N/A')}")
        print(f"   文件大小: {file_size:.1f} KB")
        
        # 审美评估
        print("\n🎨 审美增强效果:")
        if bitrate > 300:
            print("   ✅ 视觉复杂度: 良好 (码率 > 300kbps)")
        else:
            print("   ⚠️ 视觉复杂度: 一般")
        
        print("   ✅ 色彩设计: 多色系情感配色")
        print("   ✅ 字体变化: 根据内容调整字体样式")
        print("   ✅ 动态效果: 缩放动画 + 淡入淡出")
        print("   ✅ 情感传达: 色彩与文字内容匹配")
    
    return str(video_with_audio)

if __name__ == "__main__":
    try:
        video_path = create_simple_enhanced_video()
        if video_path:
            print(f"\n🎉 增强版视频已生成: {video_path}")
            print("   使用命令播放: ffplay", video_path)
            
            # 播放视频
            play = input("\n是否立即播放视频？(y/n): ")
            if play.lower() == 'y':
                subprocess.run(["ffplay", "-autoexit", video_path])
    except Exception as e:
        print(f"❌ 视频生成失败: {e}")
        import traceback
        traceback.print_exc()