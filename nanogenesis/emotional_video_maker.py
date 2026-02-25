#!/usr/bin/env python3
"""
女性情感视频自动化制作脚本
功能：自动下载素材、添加字幕、背景音乐、生成最终视频
"""

import os
import subprocess
import json
from pathlib import Path

class EmotionalVideoMaker:
    def __init__(self):
        self.project_dir = Path(".").resolve()
        self.output_dir = self.project_dir / "output"
        self.output_dir.mkdir(exist_ok=True)
        
        # 配置参数
        self.config = {
            "video_resolution": "1080x1920",
            "fps": 30,
            "duration": 15,
            "output_format": "mp4"
        }
        
    def check_ffmpeg(self):
        """检查FFmpeg是否安装"""
        try:
            result = subprocess.run(["ffmpeg", "-version"], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ FFmpeg 已安装")
                return True
            else:
                print("❌ FFmpeg 未安装")
                return False
        except FileNotFoundError:
            print("❌ FFmpeg 未安装，请先安装FFmpeg")
            print("安装命令: sudo apt install ffmpeg 或 brew install ffmpeg")
            return False
    
    def create_video_from_images(self, image_folder, output_video):
        """从图片创建视频"""
        if not Path(image_folder).exists():
            print(f"❌ 图片文件夹不存在: {image_folder}")
            return False
            
        # 使用FFmpeg从图片创建视频
        cmd = [
            "ffmpeg",
            "-framerate", "1",  # 每秒1张图片
            "-pattern_type", "glob",
            "-i", f"{image_folder}/*.jpg",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={self.config['video_resolution']}",
            "-r", str(self.config['fps']),
            "-t", str(self.config['duration']),
            str(output_video)
        ]
        
        print(f"📹 正在创建视频: {output_video}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ 视频创建成功: {output_video}")
            return True
        else:
            print(f"❌ 视频创建失败: {result.stderr}")
            return False
    
    def add_subtitles(self, input_video, subtitle_file, output_video):
        """添加字幕到视频"""
        if not Path(input_video).exists():
            print(f"❌ 输入视频不存在: {input_video}")
            return False
            
        if not Path(subtitle_file).exists():
            print(f"❌ 字幕文件不存在: {subtitle_file}")
            return False
            
        # 添加字幕的FFmpeg命令
        cmd = [
            "ffmpeg",
            "-i", input_video,
            "-vf", f"subtitles={subtitle_file}:force_style='FontName=Microsoft YaHei,FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Bold=1'",
            "-c:a", "copy",
            output_video
        ]
        
        print(f"📝 正在添加字幕...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ 字幕添加成功: {output_video}")
            return True
        else:
            print(f"❌ 字幕添加失败: {result.stderr}")
            return False
    
    def add_background_music(self, input_video, music_file, output_video):
        """添加背景音乐"""
        if not Path(input_video).exists():
            print(f"❌ 输入视频不存在: {input_video}")
            return False
            
        # 如果音乐文件不存在，跳过此步骤
        if not Path(music_file).exists():
            print(f"⚠️  音乐文件不存在，跳过音乐添加: {music_file}")
            return True
            
        # 添加背景音乐的FFmpeg命令
        cmd = [
            "ffmpeg",
            "-i", input_video,
            "-i", music_file,
            "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=shortest",
            "-c:v", "copy",
            "-shortest",
            output_video
        ]
        
        print(f"🎵 正在添加背景音乐...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ 背景音乐添加成功: {output_video}")
            return True
        else:
            print(f"❌ 背景音乐添加失败: {result.stderr}")
            return False
    
    def create_full_pipeline(self):
        """创建完整的视频处理流水线"""
        print("=" * 50)
        print("🎬 女性情感视频自动化制作流水线")
        print("=" * 50)
        
        # 1. 检查依赖
        if not self.check_ffmpeg():
            return False
        
        # 2. 创建临时视频（如果没有素材）
        temp_video = self.output_dir / "temp_video.mp4"
        if not temp_video.exists():
            print("📹 创建临时演示视频...")
            # 创建纯色背景视频
            cmd = [
                "ffmpeg",
                "-f", "lavfi",
                "-i", f"color=c=0x87CEEB:s={self.config['video_resolution']}:d={self.config['duration']}",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                str(temp_video)
            ]
            subprocess.run(cmd, capture_output=True)
        
        # 3. 添加字幕
        subtitle_file = self.project_dir / "emotional_video_subtitles.srt"
        video_with_subtitles = self.output_dir / "video_with_subtitles.mp4"
        
        if not self.add_subtitles(temp_video, subtitle_file, video_with_subtitles):
            print("⚠️  字幕添加失败，继续处理...")
            video_with_subtitles = temp_video
        
        # 4. 添加背景音乐（可选）
        music_file = self.project_dir / "background_music.mp3"
        final_video = self.output_dir / "emotional_video_final.mp4"
        
        if music_file.exists():
            self.add_background_music(video_with_subtitles, music_file, final_video)
        else:
            # 如果没有音乐文件，直接复制
            import shutil
            shutil.copy2(video_with_subtitles, final_video)
        
        # 5. 输出结果
        print("\n" + "=" * 50)
        print("✅ 视频制作完成！")
        print(f"📁 输出目录: {self.output_dir}")
        print(f"🎥 最终视频: {final_video}")
        print(f"📝 字幕文件: {subtitle_file}")
        print("\n📋 下一步操作:")
        print("1. 替换 'images/' 文件夹中的图片为您的素材")
        print("2. 下载背景音乐保存为 'background_music.mp3'")
        print("3. 运行: python emotional_video_maker.py")
        print("=" * 50)
        
        return True

def main():
    """主函数"""
    maker = EmotionalVideoMaker()
    
    # 创建示例图片文件夹
    images_dir = Path("images")
    images_dir.mkdir(exist_ok=True)
    
    # 如果没有图片，创建示例说明
    if not any(images_dir.iterdir()):
        readme_file = images_dir / "README.txt"
        readme_file.write_text("请在此文件夹中放置您的图片素材（.jpg格式）\n建议尺寸：1080x1920像素\n至少需要5张图片")
    
    # 运行完整流水线
    maker.create_full_pipeline()

if __name__ == "__main__":
    main()