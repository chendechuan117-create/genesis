#!/usr/bin/env python3
"""
情感视频增强版 - 解决AI审美不足问题
通过视觉叙事和动态设计提升视频审美质量
"""

import subprocess
import json
import os
from pathlib import Path

def create_enhanced_video():
    """创建增强版情感视频"""
    
    # 1. 创建输出目录
    output_dir = Path("output_enhanced")
    output_dir.mkdir(exist_ok=True)
    
    # 2. 脚本内容（爱情主题）
    script_lines = [
        {"text": "还记得第一次心动是什么感觉吗？", "duration": 3.0},
        {"text": "那种心跳加速，手心冒汗的瞬间", "duration": 3.0},
        {"text": "好像全世界都安静了", "duration": 3.0},
        {"text": "只剩下你和那个人的存在", "duration": 3.0},
        {"text": "爱，就是愿意为一个人变得更好", "duration": 3.0}
    ]
    
    # 3. 创建动态渐变背景（使用FFmpeg生成）
    print("🎨 创建动态渐变背景...")
    
    # 生成15秒的动态渐变背景视频
    bg_video = output_dir / "dynamic_background.mp4"
    bg_command = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x1a2a6c:size=1080x1920:d=15,gradient=0x1a2a6c:0xb21f1f:0xfdbb2d,zoompan=z='min(zoom+0.002,1.3)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(bg_video)
    ]
    
    subprocess.run(bg_command, check=True)
    
    # 4. 为每行文字创建单独的视频片段
    video_segments = []
    
    for i, line in enumerate(script_lines):
        print(f"📝 处理第{i+1}句: {line['text']}")
        
        segment_file = output_dir / f"segment_{i+1}.mp4"
        
        # 根据内容选择不同的视觉风格
        if "心动" in line['text']:
            # 心跳效果：红色渐变 + 缩放
            filter_complex = f"""
            color=c=0xff6b6b:size=1080x1920:d={line['duration']},
            gradient=0xff6b6b:0xffd166,
            zoompan=z='if(between(t,0,{line['duration']-0.5}),1+0.1*sin(2*PI*t),1)':d=1,
            drawtext=text='{line['text']}':
            fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc:
            fontcolor=0xFFFFFF:
            fontsize=70:
            shadowcolor=0x000000:
            shadowx=3:
            shadowy=3:
            x=(w-text_w)/2:
            y=(h-text_h)/2:
            enable='between(t,0,{line['duration']})'
            """
        elif "心跳加速" in line['text']:
            # 动态效果：脉动动画
            filter_complex = f"""
            color=c=0x4ecdc4:size=1080x1920:d={line['duration']},
            gradient=0x4ecdc4:0x44a08d,
            drawtext=text='{line['text']}':
            fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc:
            fontcolor=0xFFFFFF:
            fontsize=75:
            borderw=2:
            bordercolor=0x000000AA:
            x=(w-text_w)/2:
            y=(h-text_h)/2:
            enable='between(t,0,{line['duration']})',
            fade=in:0:10,
            fade=out:{int(line['duration']*25)-10}:10
            """
        elif "安静" in line['text']:
            # 宁静效果：蓝色渐变 + 缓慢移动
            filter_complex = f"""
            color=c=0x87CEEB:size=1080x1920:d={line['duration']},
            gradient=0x87CEEB:0x4682B4,
            zoompan=z='1+0.05*sin(0.5*PI*t)':d=1,
            drawtext=text='{line['text']}':
            fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Light.ttc:
            fontcolor=0xFFFFFF:
            fontsize=65:
            x=(w-text_w)/2:
            y=(h-text_h)/2:
            enable='between(t,0,{line['duration']})'
            """
        elif "存在" in line['text']:
            # 温暖效果：橙色渐变
            filter_complex = f"""
            color=c=0xffb347:size=1080x1920:d={line['duration']},
            gradient=0xffb347:0xffcc33,
            drawtext=text='{line['text']}':
            fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Medium.ttc:
            fontcolor=0xFFFFFF:
            fontsize=72:
            shadowcolor=0x000000:
            shadowx=4:
            shadowy=4:
            x=(w-text_w)/2:
            y=(h-text_h)/2:
            enable='between(t,0,{line['duration']})'
            """
        else:  # 爱，变得更好
            # 成长效果：绿色渐变 + 向上移动
            filter_complex = f"""
            color=c=0x90be6d:size=1080x1920:d={line['duration']},
            gradient=0x90be6d:0x43aa8b,
            drawtext=text='{line['text']}':
            fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc:
            fontcolor=0xFFFFFF:
            fontsize=80:
            borderw=3:
            bordercolor=0x00000055:
            x=(w-text_w)/2:
            y='h-100-20*t':
            enable='between(t,0,{line['duration']})',
            fade=in:0:15,
            fade=out:{int(line['duration']*25)-15}:15
            """
        
        # 创建视频片段
        segment_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x00000000:size=1080x1920:d={line['duration']},format=rgba",
            "-filter_complex", filter_complex.replace("\n", ""),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(segment_file)
        ]
        
        subprocess.run(segment_cmd, check=True)
        video_segments.append(segment_file)
    
    # 5. 合并所有片段
    print("🔗 合并视频片段...")
    
    # 创建文件列表
    concat_list = output_dir / "concat_list.txt"
    with open(concat_list, "w") as f:
        for segment in video_segments:
            f.write(f"file '{segment.absolute()}'\n")
    
    # 合并视频
    merged_video = output_dir / "merged_video.mp4"
    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(merged_video)
    ]
    
    subprocess.run(concat_cmd, check=True)
    
    # 6. 添加背景音乐
    print("🎵 添加背景音乐...")
    
    # 生成简单的背景音乐（440Hz正弦波）
    bgm_audio = output_dir / "bgm.wav"
    bgm_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=440:duration=15",
        "-ac", "2",
        str(bgm_audio)
    ]
    
    subprocess.run(bgm_cmd, check=True)
    
    # 7. 最终合成
    print("🎬 最终合成...")
    
    final_video = output_dir / "第一次心动_情感增强版.mp4"
    final_cmd = [
        "ffmpeg", "-y",
        "-i", str(merged_video),
        "-i", str(bgm_audio),
        "-filter_complex",
        "[0:v]scale=1080x1920,format=yuv420p[v];"
        "[1:a]volume=0.3,afade=in:0:1,afade=out:14:1[a]",
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-b:v", "800k",
        "-maxrate", "1M",
        "-bufsize", "2M",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        str(final_video)
    ]
    
    subprocess.run(final_cmd, check=True)
    
    # 8. 清理临时文件
    print("🧹 清理临时文件...")
    for segment in video_segments:
        segment.unlink(missing_ok=True)
    bg_video.unlink(missing_ok=True)
    merged_video.unlink(missing_ok=True)
    bgm_audio.unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)
    
    print(f"✅ 视频生成完成: {final_video}")
    
    # 9. 分析生成视频的质量
    print("\n📊 视频质量分析:")
    analyze_cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(final_video)
    ]
    
    result = subprocess.run(analyze_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        data = json.loads(result.stdout)
        bitrate = int(data['format']['bit_rate']) / 1000
        duration = float(data['format']['duration'])
        print(f"   码率: {bitrate:.1f} kbps")
        print(f"   时长: {duration:.2f} 秒")
        print(f"   文件大小: {os.path.getsize(final_video) / 1024:.1f} KB")
        
        if bitrate > 500:
            print("   ✅ 码率达标 (>500kbps)")
        else:
            print("   ⚠️ 码率偏低")
    
    return str(final_video)

if __name__ == "__main__":
    try:
        video_path = create_enhanced_video()
        print(f"\n🎉 增强版视频已生成: {video_path}")
        print("   使用命令播放: ffplay", video_path)
    except Exception as e:
        print(f"❌ 视频生成失败: {e}")
        import traceback
        traceback.print_exc()