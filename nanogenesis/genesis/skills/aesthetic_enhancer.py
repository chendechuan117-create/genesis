import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class AestheticEnhancer(Tool):
    @property
    def name(self) -> str:
        return "aesthetic_enhancer"
        
    @property
    def description(self) -> str:
        return "分析AI生成视频的美学质量，并提供基于多维度评估的具体优化建议。旨在解决‘AI审美不足’问题。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "video_path": {"type": "string", "description": "待分析视频文件的路径"},
                "analysis_mode": {"type": "string", "enum": ["full", "quick"], "description": "分析模式：full(详细分析)，quick(快速评估)", "default": "full"}
            },
            "required": ["video_path"]
        }
        
    async def execute(self, video_path: str, analysis_mode: str = "full") -> str:
        import subprocess
        import json
        import os
        
        if not os.path.exists(video_path):
            return f"错误：视频文件 '{video_path}' 不存在。"
        
        # 1. 使用FFprobe获取基础技术元数据
        try:
            probe_cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', video_path
            ]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
            metadata = json.loads(probe_result.stdout)
        except Exception as e:
            return f"获取视频元数据失败: {e}"
        
        # 2. 提取关键帧进行“伪视觉分析”（基于元数据推断）
        video_stream = next((s for s in metadata.get('streams', []) if s['codec_type'] == 'video'), {})
        format_info = metadata.get('format', {})
        
        # 美学评估维度 (基于启发式规则)
        assessment = {
            "technical_quality": {
                "resolution": f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}",
                "aspect_ratio": video_stream.get('display_aspect_ratio', 'N/A'),
                "bitrate": int(int(format_info.get('bit_rate', 0)) / 1000) if format_info.get('bit_rate') else 0,
                "codec": video_stream.get('codec_name', 'N/A'),
                "score": 0
            },
            "composition_inference": {
                "inferred_style": "竖屏短视频" if video_stream.get('height', 0) > video_stream.get('width', 0) else "横屏",
                "potential_issues": [],
                "suggestions": []
            },
            "color_and_lighting": {
                "inferred_from_codec": video_stream.get('pix_fmt', 'N/A'),
                "notes": "高像素格式（如yuvj420p）通常能保留更多色彩信息。",
                "suggestions": []
            },
            "pacing_and_rhythm": {
                "duration_seconds": float(format_info.get('duration', 0)),
                "frames_per_second": eval(video_stream.get('avg_frame_rate', '0/1')) if video_stream.get('avg_frame_rate') else 0,
                "suitability_for_platform": "适合抖音（短时长）" if float(format_info.get('duration', 0)) < 60 else "时长偏长",
                "suggestions": []
            },
            "emotional_conveyance": {
                "notes": "此维度需结合音频和内容分析。当前仅基于时长和节奏推断。",
                "suggestions": []
            }
        }
        
        # 3. 应用启发式评分与建议生成
        tech_score = 0
        if assessment["technical_quality"]["bitrate"] > 500:
            tech_score += 2
        elif assessment["technical_quality"]["bitrate"] > 200:
            tech_score += 1
        if assessment["technical_quality"]["codec"] in ['h264', 'hevc']:
            tech_score += 1
        assessment["technical_quality"]["score"] = min(tech_score, 3)
        
        if assessment["composition_inference"]["inferred_style"] == "竖屏短视频":
            assessment["composition_inference"]["suggestions"].append("符合移动端观看习惯。")
        else:
            assessment["composition_inference"]["suggestions"].append("考虑裁剪为9:16竖屏以适应抖音。")
        
        if assessment["pacing_and_rhythm"]["duration_seconds"] > 45:
            assessment["pacing_and_rhythm"]["suggestions"].append("视频时长超过45秒，考虑加速或剪辑关键片段以维持观众注意力。")
        if assessment["pacing_and_rhythm"]["frames_per_second"] < 24:
            assessment["pacing_and_rhythm"]["suggestions"].append("帧率较低，可能导致卡顿。建议输出时确保帧率>=24fps。")
        
        assessment["emotional_conveyance"]["suggestions"].extend([
            "确保背景音乐节奏与画面切换点对齐。",
            "考虑添加细微的缩放或平移动效以增强代入感。",
            "字幕出现时机应与台词重音同步。"
        ])
        
        # 4. 生成优化指令
        optimization_commands = []
        if assessment["technical_quality"]["bitrate"] < 800:
            optimization_commands.append(f"# 提升视频码率至800k以上\nffmpeg -i {video_path} -b:v 800k -maxrate 1M -bufsize 2M output_enhanced.mp4")
        if assessment["pacing_and_rhythm"]["suggestions"]:
            optimization_commands.append("# 使用以下命令进行智能加速（1.2倍）\nffmpeg -i {video_path} -filter:v \"setpts=0.833*PTS\" -filter:a \"atempo=1.2\" output_fast.mp4")
        
        # 5. 格式化报告
        report = f"""
# 🎨 AI视频美学增强分析报告

## 📊 基础技术分析
- **文件**: {os.path.basename(video_path)}
- **分辨率**: {assessment['technical_quality']['resolution']} ({assessment['composition_inference']['inferred_style']})
- **时长**: {assessment['pacing_and_rhythm']['duration_seconds']:.2f}秒
- **码率**: {assessment['technical_quality']['bitrate']} kbps
- **编码**: {assessment['technical_quality']['codec']}
- **技术质量评分**: {assessment['technical_quality']['score']}/3

## 🔍 美学维度评估与建议
### 1. 构图与画面
- **推断**: {assessment['composition_inference']['inferred_style']}
- **建议**: {' '.join(assessment['composition_inference']['suggestions'])}

### 2. 色彩与光影
- **像素格式**: {assessment['color_and_lighting']['inferred_from_codec']}
- **说明**: {assessment['color_and_lighting']['notes']}
- **建议**: 考虑使用LUT调色或增加对比度滤镜。

### 3. 节奏与剪辑
- **帧率**: {assessment['pacing_and_rhythm']['frames_per_second']:.2f} fps
- **平台适配**: {assessment['pacing_and_rhythm']['suitability_for_platform']}
- **建议**: {' '.join(assessment['pacing_and_rhythm']['suggestions'])}

### 4. 情感传达
- **说明**: {assessment['emotional_conveyance']['notes']}
- **建议**: 
{chr(10).join('- ' + s for s in assessment['emotional_conveyance']['suggestions'])}

## ⚙️ 可执行的优化命令
{chr(10).join(optimization_commands) if optimization_commands else '# 技术参数已达良好水平，建议从内容创意层面优化。'}

## 🧠 核心解决思路
“审美不足”本质是AI缺乏人类偏好先验。本工具将“审美”拆解为可量化的技术参数与可优化的启发式规则。
**下一步**: 运行上述优化命令，或基于此报告调整视频生成脚本的初始参数。
"""
        return report