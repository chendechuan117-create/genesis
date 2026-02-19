import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

from typing import Dict, List, Optional
import json
import random
from datetime import datetime

class ContentGenerator:
    """抖音/小红书内容生成工具"""
    
    name = "content_generator"
    description = "生成抖音/小红书平台的内容创意、标题、描述和标签"
    parameters = {
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "enum": ["douyin", "xiaohongshu"],
                "description": "平台名称"
            },
            "content_type": {
                "type": "string",
                "enum": ["product_review", "tutorial", "entertainment", "lifestyle"],
                "description": "内容类型"
            },
            "topic": {
                "type": "string",
                "description": "具体主题（如'电子产品'、'美妆'）"
            },
            "count": {
                "type": "integer",
                "description": "生成数量",
                "default": 3
            },
            "tone": {
                "type": "string",
                "enum": ["professional", "casual", "enthusiastic", "humorous"],
                "description": "语气风格",
                "default": "casual"
            }
        },
        "required": ["platform", "content_type", "topic"]
    }
    
    def execute(self, platform: str, content_type: str, topic: str, 
                count: int = 3, tone: str = "casual") -> Dict:
        """执行内容生成"""
        
        # 生成内容创意
        content_ideas = []
        
        for i in range(count):
            idea = {
                "id": f"idea_{i+1}",
                "platform": platform,
                "content_type": content_type,
                "topic": topic,
                "tone": tone,
                "generated_at": datetime.now().isoformat(),
                "title": self._generate_title(platform, content_type, topic, tone),
                "description": self._generate_description(platform, content_type, topic, tone),
                "hashtags": self._generate_hashtags(platform, content_type, topic),
                "key_points": self._generate_key_points(content_type, topic),
                "call_to_action": self._generate_cta(platform, content_type),
                "estimated_production_time": self._estimate_time(content_type),
                "difficulty_level": self._assess_difficulty(content_type)
            }
            content_ideas.append(idea)
        
        return {
            "success": True,
            "platform": platform,
            "content_type": content_type,
            "topic": topic,
            "count": count,
            "content_ideas": content_ideas,
            "next_steps": [
                "选择1-2个创意进行制作",
                "使用实验追踪器记录内容计划",
                "设置发布时间和指标追踪"
            ]
        }
    
    def _generate_title(self, platform: str, content_type: str, topic: str, tone: str) -> str:
        """生成标题"""
        templates = {
            "douyin": {
                "product_review": {
                    "professional": ["深度评测：{topic}到底值不值？", "{topic}全面测评，优缺点一次说清"],
                    "casual": ["用了3个月的{topic}，真实感受分享", "这款{topic}真的那么好用吗？实测告诉你"],
                    "enthusiastic": ["OMG！这款{topic}也太好用了吧！", "被问爆的{topic}，今天终于来分享了"],
                    "humorous": ["花XXX元买的{topic}，结果...", "关于{topic}，我有话要说"]
                },
                "tutorial": {
                    "professional": ["{topic}详细教程，一步步教你", "掌握{topic}的5个关键技巧"],
                    "casual": ["手把手教你{topic}，超简单", "{topic}这样做，效果翻倍"]
                }
            },
            "xiaohongshu": {
                "product_review": {
                    "professional": ["{topic}深度测评报告", "真实使用体验：{topic}优缺点分析"],
                    "casual": ["我的{topic}使用心得", "关于{topic}，你想知道的都在这里"],
                    "enthusiastic": ["无限回购的{topic}！太爱了", "这款{topic}真的绝了！"]
                }
            }
        }
        
        platform_templates = templates.get(platform, {})
        type_templates = platform_templates.get(content_type, {})
        tone_templates = type_templates.get(tone, [])
        
        if tone_templates:
            template = random.choice(tone_templates)
            return template.format(topic=topic)
        else:
            return f"{topic}{'评测' if content_type == 'product_review' else '分享'}"
    
    def _generate_description(self, platform: str, content_type: str, topic: str, tone: str) -> str:
        """生成描述"""
        descriptions = {
            "product_review": [
                f"今天来聊聊{topic}，从购买到使用整整体验了1个月，优缺点都会详细说明。",
                f"关于{topic}，网上评价褒贬不一，我来说说真实使用感受。",
                f"这款{topic}最近很火，到底值不值得入手？看完这个视频你就知道了。"
            ],
            "tutorial": [
                f"很多朋友问{topic}怎么做，今天分享我的独家方法。",
                f"掌握{topic}其实很简单，跟着我做就行。"
            ]
        }
        
        desc_list = descriptions.get(content_type, [f"分享{topic}的相关内容。"])
        description = random.choice(desc_list)
        
        # 添加平台特定格式
        if platform == "xiaohongshu":
            description += "\n\n#小红书 #分享"
        
        return description
    
    def _generate_hashtags(self, platform: str, content_type: str, topic: str) -> List[str]:
        """生成话题标签"""
        base_tags = [f"#{topic}"]
        
        platform_tags = {
            "douyin": ["#抖音", "#抖音好物", "#种草"],
            "xiaohongshu": ["#小红书", "#好物分享", "#种草"]
        }
        
        type_tags = {
            "product_review": ["#测评", "#评测", "#真实体验", "#购物分享"],
            "tutorial": ["#教程", "#教学", "#技巧", "#干货"]
        }
        
        tags = base_tags + platform_tags.get(platform, []) + type_tags.get(content_type, [])
        
        # 添加一些随机热门标签
        hot_tags = ["#热门", "#推荐", "#必看", "#实用"]
        tags.extend(random.sample(hot_tags, 2))
        
        return tags[:8]  # 限制标签数量
    
    def _generate_key_points(self, content_type: str, topic: str) -> List[str]:
        """生成关键点"""
        if content_type == "product_review":
            return [
                f"{topic}的外观设计",
                f"使用体验和感受", 
                f"优点和缺点分析",
                f"性价比评估",
                f"适合人群推荐"
            ]
        elif content_type == "tutorial":
            return [
                f"准备工作和材料",
                f"步骤一：...",
                f"步骤二：...", 
                f"步骤三：...",
                f"注意事项和小技巧"
            ]
        else:
            return ["要点1", "要点2", "要点3"]
    
    def _generate_cta(self, platform: str, content_type: str) -> str:
        """生成行动号召"""
        ctas = {
            "product_review": {
                "douyin": "想知道购买链接？评论区告诉我！",
                "xiaohongshu": "需要链接的姐妹可以私信我哦～"
            },
            "tutorial": {
                "douyin": "学会了记得点赞收藏！",
                "xiaohongshu": "记得关注我，更多干货分享"
            }
        }
        
        return ctas.get(content_type, {}).get(platform, "喜欢的话记得点赞关注！")
    
    def _estimate_time(self, content_type: str) -> str:
        """估计制作时间"""
        times = {
            "product_review": "2-4小时（拍摄+剪辑）",
            "tutorial": "3-5小时（准备+拍摄+剪辑）",
            "entertainment": "1-3小时",
            "lifestyle": "2-3小时"
        }
        return times.get(content_type, "2-3小时")
    
    def _assess_difficulty(self, content_type: str) -> str:
        """评估难度"""
        difficulties = {
            "product_review": "中等（需要产品+拍摄+剪辑）",
            "tutorial": "中高（需要准备+演示+剪辑）",
            "entertainment": "低到中等",
            "lifestyle": "低到中等"
        }
        return difficulties.get(content_type, "中等")

# 工具导出
tool_class = ContentGenerator