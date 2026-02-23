import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class EmotionalVideoProcessor(Tool):
    @property
    def name(self) -> str:
        return "emotional_video_processor"
        
    @property
    def description(self) -> str:
        return "根据情感内容脚本生成FFmpeg视频处理命令和素材准备方案"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "script_json": {"type": "string", "description": "情感内容脚本的JSON字符串"},
                "output_path": {"type": "string", "description": "输出视频路径", "default": "./output/emotional_video.mp4"},
                "material_type": {"type": "string", "description": "素材类型：stock(素材库), record(录制), user(用户提供)", "default": "stock"}
            },
            "required": ["script_json"]
        }
        
    async def execute(self, script_json: str, output_path: str = "./output/emotional_video.mp4", material_type: str = "stock") -> str:
        import json
        import os
        
        try:
            script = json.loads(script_json)
        except:
            return "脚本JSON解析失败，请检查格式"
        
        # 解析脚本
        theme = script.get("视频主题", "")
        title = script.get("视频标题", "")
        duration = script.get("视频时长", "15秒")
        tags = script.get("推荐标签", [])
        
        # 根据素材类型生成方案
        material_plans = {
            "stock": {
                "描述": "使用素材库资源",
                "素材来源": [
                    "1. Pexels/Unsplash免费素材库",
                    "2. 本地情感素材库（需预先下载）",
                    "3. AI生成温暖场景图片"
                ],
                "准备步骤": [
                    "下载3-5个相关场景视频/图片",
                    "准备人物特写素材（可选）",
                    "收集温暖色调的过渡素材"
                ]
            },
            "record": {
                "描述": "现场录制",
                "设备需求": ["手机/相机", "三脚架", "补光灯（可选）"],
                "录制场景": ["室内温馨环境", "自然光线下", "简单背景墙"],
                "人物要求": ["自然表情", "温暖微笑", "舒适着装"]
            },
            "user": {
                "描述": "用户提供素材",
                "格式要求": ["MP4/MOV视频", "1080x1920分辨率", "30fps帧率"],
                "内容建议": ["温暖场景", "人物互动", "自然风光"],
                "数量要求": "至少3段素材，每段5-10秒"
            }
        }
        
        # 生成FFmpeg处理命令
        ffmpeg_commands = [
            "# 1. 素材预处理",
            "ffmpeg -i input1.mp4 -vf \"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2\" -c:v libx264 -preset fast -crf 23 -r 30 -c:a aac -b:a 128k processed1.mp4",
            "",
            "# 2. 添加字幕（假设有字幕文件subtitle.srt）",
            "ffmpeg -i processed1.mp4 -vf \"subtitles=subtitle.srt:force_style='FontName=Microsoft YaHei,FontSize=24,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BackColour=&H80000000,BorderStyle=3,Outline=1,Shadow=0'\" -c:v libx264 -c:a copy subtitled.mp4",
            "",
            "# 3. 添加背景音乐",
            "ffmpeg -i subtitled.mp4 -i bg_music.mp3 -filter_complex \"[0:a]volume=1.0[a0];[1:a]volume=0.3[a1];[a0][a1]amix=inputs=2:duration=first\" -c:v copy -c:a aac -b:a 192k final_output.mp4",
            "",
            "# 4. 添加片头片尾（可选）",
            "ffmpeg -i intro.mp4 -i final_output.mp4 -i outro.mp4 -filter_complex \"[0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1\" -c:v libx264 -c:a aac complete_video.mp4"
        ]
        
        # 生成完整方案
        plan = {
            "项目信息": {
                "主题": theme,
                "标题": title,
                "时长": duration,
                "目标标签": tags
            },
            "素材方案": material_plans.get(material_type, material_plans["stock"]),
            "技术参数": {
                "分辨率": "1080x1920 (9:16 竖屏)",
                "帧率": "30fps",
                "编码": "H.264 (libx264)",
                "音频": "AAC, 128-192kbps",
                "文件格式": "MP4"
            },
            "处理流程": [
                "1. 素材收集与预处理",
                "2. 字幕生成与添加",
                "3. 背景音乐合成",
                "4. 特效与过渡添加",
                "5. 最终导出与压缩"
            ],
            "FFmpeg命令示例": ffmpeg_commands,
            "输出文件": output_path,
            "预计处理时间": "10-30分钟（取决于素材复杂度）"
        }
        
        # 创建输出目录
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        
        return json.dumps(plan, ensure_ascii=False, indent=2)