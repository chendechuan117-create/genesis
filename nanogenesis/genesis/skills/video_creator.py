import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class VideoCreatorTool(Tool):
    @property
    def name(self) -> str:
        return "video_creator"
        
    @property
    def description(self) -> str:
        return "创建抖音风格的短视频。可以生成脚本、处理素材、添加字幕和特效。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "视频主题（如：科技、美食、生活技巧）"},
                "duration": {"type": "integer", "description": "视频时长（秒），默认15秒", "default": 15},
                "style": {"type": "string", "description": "视频风格：fast_paced(快节奏)、educational(教育)、funny(搞笑)", "default": "fast_paced"},
                "output_format": {"type": "string", "description": "输出格式：script_only(仅脚本)、full_plan(完整方案)", "default": "full_plan"}
            },
            "required": ["topic"]
        }
        
    async def execute(self, topic: str, duration: int = 15, style: str = "fast_paced", output_format: str = "full_plan") -> str:
        # 根据主题生成视频脚本
        scripts = {
            "科技": [
                "0-3秒: 震撼开场 - '你知道吗？AI正在改变这些行业...'",
                "3-8秒: 核心内容 - 展示3个AI应用场景的快速切换",
                "8-12秒: 价值提供 - '关注我，每天分享一个科技小知识'",
                "12-15秒: 互动引导 - '评论区告诉我你想了解哪个领域？'"
            ],
            "美食": [
                "0-4秒: 视觉冲击 - 美食特写镜头，滋滋作响的声音",
                "4-10秒: 制作过程 - 快速剪辑关键步骤",
                "10-13秒: 成品展示 - 完美摆盘，诱人特写",
                "13-15秒: 配方分享 - '想要配方？评论区扣1'"
            ],
            "生活技巧": [
                "0-3秒: 问题展示 - '还在为XXX烦恼吗？'",
                "3-10秒: 解决方案 - 3个实用技巧快速演示",
                "10-13秒: 效果对比 - 使用前后的明显差异",
                "13-15秒: 收藏提醒 - '收藏起来，下次用得上'"
            ]
        }
        
        # 默认脚本模板
        default_script = [
            "0-3秒: 吸引注意力 - 提出有趣问题或展示惊人结果",
            "3-10秒: 核心价值 - 快速传递有用信息",
            "10-13秒: 情感共鸣 - 引发观众共鸣或好奇心",
            "13-15秒: 行动号召 - 引导点赞、评论、关注"
        ]
        
        # 选择脚本
        script = scripts.get(topic, default_script)
        
        # 根据风格调整
        style_tips = {
            "fast_paced": "🎬 快节奏：每2秒一个镜头切换，背景音乐节奏感强",
            "educational": "📚 教育类：清晰字幕，重点信息突出显示",
            "funny": "😂 搞笑类：加入音效和夸张表情包"
        }
        
        # 生成完整方案
        result = f"""
# 🎥 抖音视频创作方案

## 📋 基本信息
- **主题**: {topic}
- **时长**: {duration}秒
- **风格**: {style} {style_tips.get(style, '')}

## 📝 分镜脚本
{chr(10).join(f'{i+1}. {line}' for i, line in enumerate(script))}

## 🎵 建议配置
1. **背景音乐**: 抖音热门BGM，节奏匹配{style}
2. **字幕样式**: 白色黑边，大号字体，关键信息高亮
3. **转场效果**: 快速切换，保持视觉流畅
4. **标签建议**: #{topic} #生活小技巧 #实用干货

## ⚙️ 技术参数
- **分辨率**: 1080x1920 (9:16竖屏)
- **帧率**: 30fps
- **格式**: MP4 (H.264编码)
- **文件大小**: 约{15 * duration}MB

## 📊 发布策略
1. **最佳时间**: 晚上7-10点（用户活跃期）
2. **话题选择**: 3-5个相关热门话题
3. **互动引导**: 结尾明确要求点赞/评论
4. **发布时间**: 间隔2-3小时发布同类内容

## 🔧 我能自动化的部分
✅ 脚本生成 ✅ 技术参数设置 ✅ 发布策略规划
✅ 标签优化 ✅ 数据分析模板 ✅ 批量处理脚本

## 👤 需要您操作的部分
🔸 实际视频拍摄/素材准备
🔸 抖音APP内发布操作
🔸 账号登录和权限管理
🔸 最终内容审核确认

## 🚀 下一步行动
1. 您提供原始素材或确认脚本
2. 我生成完整的视频处理脚本
3. 您使用手机/电脑编辑软件处理
4. 您在抖音APP内发布
5. 我提供后续数据分析
"""
        
        if output_format == "script_only":
            return f"视频脚本：{chr(10).join(script)}"
        else:
            return result