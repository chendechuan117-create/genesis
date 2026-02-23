import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class EmotionalContentGenerator(Tool):
    @property
    def name(self) -> str:
        return "emotional_content_generator"
        
    @property
    def description(self) -> str:
        return "生成抖音女性情感内容脚本，包括故事、文案、标签和发布建议"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "theme": {"type": "string", "description": "情感主题：love(爱情), friendship(友情), family(亲情), self_growth(自我成长), life_insight(生活感悟)"},
                "tone": {"type": "string", "description": "情感基调：warm(温暖), inspiring(励志), reflective(反思), comforting(安慰)", "default": "warm"},
                "duration": {"type": "integer", "description": "视频时长（秒）", "default": 15}
            },
            "required": ["theme"]
        }
        
    async def execute(self, theme: str, tone: str = "warm", duration: int = 15) -> str:
        # 情感主题映射
        themes = {
            "love": {
                "title": ["那个让你心动的小瞬间", "爱情里最珍贵的不是浪漫", "好的爱情是什么样子"],
                "tags": ["#爱情观", "#恋爱技巧", "#情感共鸣", "#女性成长"]
            },
            "friendship": {
                "title": ["真正的朋友是什么样的", "成年人的友情有多珍贵", "那些陪你走过低谷的人"],
                "tags": ["#友情", "#闺蜜", "#人际关系", "#女性友谊"]
            },
            "family": {
                "title": ["父母的爱藏在细节里", "家的温暖是什么感觉", "长大后才知道的亲情"],
                "tags": ["#亲情", "#家庭", "#父母", "#温暖的家"]
            },
            "self_growth": {
                "title": ["爱自己才是终身浪漫的开始", "女孩如何建立自信", "停止内耗的3个方法"],
                "tags": ["#自我成长", "#女性力量", "#自信", "#停止内耗"]
            },
            "life_insight": {
                "title": ["生活的小确幸", "平凡日子里的光", "简单生活的快乐"],
                "tags": ["#生活感悟", "#小确幸", "#治愈系", "#简单生活"]
            }
        }
        
        # 情感基调映射
        tones = {
            "warm": "温暖治愈，给人力量",
            "inspiring": "励志向上，激发行动",
            "reflective": "引人深思，促进反思",
            "comforting": "安慰人心，缓解焦虑"
        }
        
        import random
        import json
        
        if theme not in themes:
            return f"未知主题：{theme}，请选择：{list(themes.keys())}"
            
        theme_data = themes[theme]
        title = random.choice(theme_data["title"])
        tags = theme_data["tags"]
        
        # 生成脚本结构
        script = {
            "视频主题": f"女性情感 - {theme}",
            "视频标题": title,
            "情感基调": tones.get(tone, tone),
            "视频时长": f"{duration}秒",
            "分镜脚本": [
                {"时长": "0-3秒", "内容": "开场画面 + 核心观点抛出", "视觉": "人物特写或相关场景"},
                {"时长": "3-10秒", "内容": "情感故事讲述或观点阐述", "视觉": "场景切换 + 字幕重点"},
                {"时长": "10-15秒", "内容": "总结升华 + 互动引导", "视觉": "温暖画面 + 结束语"}
            ],
            "文案建议": [
                f"💕 {title}",
                "👇 评论区分享你的故事",
                "❤️ 点赞收藏，温暖更多人"
            ],
            "推荐标签": tags,
            "发布时间建议": "晚上8-10点（情感内容黄金时间）",
            "互动引导": "在评论区分享你的类似经历或感受",
            "背景音乐建议": "轻柔钢琴曲或温暖纯音乐"
        }
        
        return json.dumps(script, ensure_ascii=False, indent=2)