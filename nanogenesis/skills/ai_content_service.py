import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

#!/usr/bin/env python3
"""
AI内容生成服务系统 - 自动化赚钱引擎
功能：自动生成博客文章、社交媒体内容、营销文案
商业模式：按字数/篇数收费，订阅制服务
"""

import json
import random
import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

@dataclass
class ContentRequest:
    """客户内容请求"""
    client_id: str
    content_type: str  # blog, social_media, email, ad_copy
    topic: str
    target_audience: str
    tone: str  # professional, casual, persuasive, friendly
    word_count: int
    keywords: List[str]
    deadline: Optional[str] = None

@dataclass
class GeneratedContent:
    """生成的内容"""
    request_id: str
    title: str
    content: str
    word_count: int
    seo_score: float  # 0-100
    readability_score: float  # 0-100
    generated_at: str
    estimated_value: float  # 估算的商业价值（美元）

class AIContentService:
    """AI内容生成服务核心引擎"""
    
    def __init__(self):
        self.content_templates = {
            "blog": {
                "structure": ["引人入胜的标题", "问题陈述", "解决方案", "分步指南", "案例研究", "结论", "行动号召"],
                "price_per_1000_words": 50.0,  # 每千字50美元
                "avg_completion_time": "2小时"
            },
            "social_media": {
                "structure": ["钩子", "价值主张", "互动问题", "标签"],
                "price_per_post": 10.0,  # 每篇10美元
                "avg_completion_time": "30分钟"
            },
            "email": {
                "structure": ["主题行", "问候语", "价值陈述", "具体好处", "行动号召", "签名"],
                "price_per_email": 25.0,
                "avg_completion_time": "1小时"
            },
            "ad_copy": {
                "structure": ["标题", "副标题", "正文", "独特卖点", "社会证明", "紧迫感", "行动按钮"],
                "price_per_ad": 75.0,
                "avg_completion_time": "1.5小时"
            }
        }
        
        self.clients = {}
        self.revenue_log = []
        
    def register_client(self, client_name: str, email: str, plan: str = "basic") -> str:
        """注册新客户"""
        client_id = f"CLIENT_{random.randint(10000, 99999)}"
        self.clients[client_id] = {
            "name": client_name,
            "email": email,
            "plan": plan,
            "registered_at": datetime.datetime.now().isoformat(),
            "total_spent": 0.0,
            "content_count": 0
        }
        return client_id
    
    def generate_content(self, request: ContentRequest) -> GeneratedContent:
        """生成内容（模拟AI生成过程）"""
        
        # 获取模板配置
        template = self.content_templates[request.content_type]
        
        # 生成唯一ID
        request_id = f"CONTENT_{random.randint(100000, 999999)}"
        
        # 根据内容类型生成标题
        titles = {
            "blog": [
                f"如何{request.topic}：完整指南",
                f"{request.topic}的7个最佳实践",
                f"为什么{request.topic}对你的业务至关重要",
                f"掌握{request.topic}：专家分享的5个技巧"
            ],
            "social_media": [
                f"发现{request.topic}的秘密",
                f"你还在为{request.topic}烦恼吗？",
                f"{request.topic}：改变游戏规则的方法",
                f"关于{request.topic}，你需要知道的一切"
            ],
            "email": [
                f"关于{request.topic}的重要更新",
                f"提升你的{request.topic}策略",
                f"{request.topic}：特别邀请",
                f"解锁{request.topic}的潜力"
            ],
            "ad_copy": [
                f"革命性的{request.topic}解决方案",
                f"告别{request.topic}问题",
                f"{request.topic}专家就在这里",
                f"提升{request.topic}效果的终极指南"
            ]
        }
        
        title = random.choice(titles[request.content_type])
        
        # 生成内容（模拟）
        content_structure = template["structure"]
        content_parts = []
        
        for part in content_structure:
            if part == "引人入胜的标题":
                content_parts.append(f"# {title}\n\n")
            elif part == "问题陈述":
                content_parts.append(f"## 问题：为什么{request.topic}如此重要？\n\n")
                content_parts.append(f"在当今竞争激烈的市场中，{request.topic}已经成为{request.target_audience}面临的关键挑战。许多企业因为忽视这一点而错失了重要机会。\n\n")
            elif part == "解决方案":
                content_parts.append(f"## 解决方案：我们的方法\n\n")
                content_parts.append(f"通过结合先进的技术和行业最佳实践，我们开发了一套完整的{request.topic}解决方案。这种方法已经帮助数百家企业实现了显著增长。\n\n")
            elif part == "分步指南":
                content_parts.append(f"## 分步实施指南\n\n")
                steps = ["分析与评估", "策略制定", "实施执行", "监控优化"]
                for i, step in enumerate(steps, 1):
                    content_parts.append(f"{i}. **{step}**：详细描述这一步的关键要点和预期结果。\n")
                content_parts.append("\n")
            elif part == "案例研究":
                content_parts.append(f"## 成功案例\n\n")
                content_parts.append(f"一家中型企业通过实施我们的{request.topic}策略，在3个月内实现了：\n")
                content_parts.append("- 收入增长：+45%\n")
                content_parts.append("- 客户满意度：+32%\n")
                content_parts.append("- 运营效率：+28%\n\n")
            elif part == "结论":
                content_parts.append(f"## 结论\n\n")
                content_parts.append(f"{request.topic}不是可选项，而是必需品。通过正确的策略和工具，你可以将挑战转化为竞争优势。\n\n")
            elif part == "行动号召":
                content_parts.append(f"## 立即行动\n\n")
                content_parts.append(f"准备好提升你的{request.topic}能力了吗？联系我们获取个性化咨询。\n\n")
        
        # 组合内容
        full_content = "".join(content_parts)
        
        # 计算字数（模拟）
        word_count = len(full_content.split())
        if word_count < request.word_count:
            # 补充内容以达到目标字数
            additional_content = f"\n\n## 额外见解\n\n基于我们对{request.target_audience}的深入研究，我们还发现以下关键趋势：\n\n"
            additional_content += "1. **技术整合**：将{request.topic}与现有系统无缝集成的重要性\n"
            additional_content += "2. **数据驱动**：利用分析工具优化{request.topic}效果\n"
            additional_content += "3. **持续改进**：建立反馈循环以确保持续成功\n"
            additional_content += "4. **团队培训**：确保所有相关人员都掌握必要的{request.topic}技能\n\n"
            
            full_content += additional_content
            word_count = len(full_content.split())
        
        # 计算分数
        seo_score = min(85 + random.randint(-10, 15), 100)
        readability_score = min(80 + random.randint(-5, 20), 100)
        
        # 计算价值
        if request.content_type == "blog":
            estimated_value = (word_count / 1000) * template["price_per_1000_words"]
        else:
            estimated_value = template["price_per_post"]
        
        # 记录收入
        self._record_transaction(request.client_id, estimated_value)
        
        return GeneratedContent(
            request_id=request_id,
            title=title,
            content=full_content,
            word_count=word_count,
            seo_score=seo_score,
            readability_score=readability_score,
            generated_at=datetime.datetime.now().isoformat(),
            estimated_value=estimated_value
        )
    
    def _record_transaction(self, client_id: str, amount: float):
        """记录交易"""
        if client_id in self.clients:
            self.clients[client_id]["total_spent"] += amount
            self.clients[client_id]["content_count"] += 1
        
        self.revenue_log.append({
            "client_id": client_id,
            "amount": amount,
            "timestamp": datetime.datetime.now().isoformat(),
            "type": "content_generation"
        })
    
    def generate_business_report(self) -> Dict:
        """生成业务报告"""
        total_revenue = sum(log["amount"] for log in self.revenue_log)
        total_clients = len(self.clients)
        total_content = sum(client["content_count"] for client in self.clients.values())
        
        # 收入预测
        avg_daily_revenue = total_revenue / max(1, len(self.revenue_log))
        monthly_projection = avg_daily_revenue * 30
        
        return {
            "report_date": datetime.datetime.now().isoformat(),
            "total_revenue": round(total_revenue, 2),
            "total_clients": total_clients,
            "total_content_generated": total_content,
            "average_revenue_per_client": round(total_revenue / max(1, total_clients), 2),
            "monthly_revenue_projection": round(monthly_projection, 2),
            "top_clients": sorted(
                [(cid, data["name"], data["total_spent"]) for cid, data in self.clients.items()],
                key=lambda x: x[2],
                reverse=True
            )[:5],
            "revenue_by_content_type": self._calculate_revenue_by_type()
        }
    
    def _calculate_revenue_by_type(self) -> Dict:
        """按内容类型计算收入（简化版）"""
        return {
            "blog": len([l for l in self.revenue_log if l.get("content_type") == "blog"]) * 50,
            "social_media": len([l for l in self.revenue_log if l.get("content_type") == "social_media"]) * 10,
            "email": len([l for l in self.revenue_log if l.get("content_type") == "email"]) * 25,
            "ad_copy": len([l for l in self.revenue_log if l.get("content_type") == "ad_copy"]) * 75
        }
    
    def get_pricing_plans(self) -> Dict:
        """获取定价方案"""
        return {
            "basic": {
                "price": "$199/月",
                "features": [
                    "10篇博客文章（每篇1000字）",
                    "20篇社交媒体帖子",
                    "5封营销邮件",
                    "基础SEO优化",
                    "每周内容日历"
                ],
                "monthly_value": "$500+"
            },
            "pro": {
                "price": "$499/月",
                "features": [
                    "30篇博客文章",
                    "50篇社交媒体帖子",
                    "15封营销邮件",
                    "高级SEO优化",
                    "竞争对手分析",
                    "月度策略报告",
                    "优先支持"
                ],
                "monthly_value": "$1500+"
            },
            "enterprise": {
                "price": "$999/月",
                "features": [
                    "无限内容生成",
                    "定制内容策略",
                    "品牌声音分析",
                    "多语言支持",
                    "API访问",
                    "专属客户经理",
                    "24/7支持"
                ],
                "monthly_value": "$3000+"
            }
        }

# 工具类定义
class AIContentServiceTool:
    name = "ai_content_service"
    description = "AI内容生成服务系统 - 自动化创建和销售高质量内容"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["register_client", "generate_content", "get_report", "get_pricing"],
                "description": "要执行的操作"
            },
            "client_name": {
                "type": "string",
                "description": "客户名称（仅register_client需要）"
            },
            "client_email": {
                "type": "string",
                "description": "客户邮箱（仅register_client需要）"
            },
            "content_type": {
                "type": "string",
                "enum": ["blog", "social_media", "email", "ad_copy"],
                "description": "内容类型（仅generate_content需要）"
            },
            "topic": {
                "type": "string",
                "description": "内容主题（仅generate_content需要）"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self):
        self.service = AIContentService()
    
    def execute(self, params: Dict) -> Dict:
        action = params.get("action")
        
        if action == "register_client":
            client_name = params.get("client_name", "测试客户")
            client_email = params.get("client_email", "test@example.com")
            client_id = self.service.register_client(client_name, client_email)
            return {
                "success": True,
                "client_id": client_id,
                "message": f"客户注册成功！ID: {client_id}"
            }
        
        elif action == "generate_content":
            # 创建模拟客户如果不存在
            if not self.service.clients:
                client_id = self.service.register_client("默认客户", "default@example.com")
            else:
                client_id = list(self.service.clients.keys())[0]
            
            content_type = params.get("content_type", "blog")
            topic = params.get("topic", "数字营销策略")
            
            request = ContentRequest(
                client_id=client_id,
                content_type=content_type,
                topic=topic,
                target_audience="中小企业主",
                tone="professional",
                word_count=1000,
                keywords=["营销", "策略", "增长", "数字化"]
            )
            
            content = self.service.generate_content(request)
            
            return {
                "success": True,
                "content": asdict(content),
                "estimated_value": f"${content.estimated_value:.2f}",
                "message": f"内容生成成功！SEO评分：{content.seo_score}/100"
            }
        
        elif action == "get_report":
            report = self.service.generate_business_report()
            return {
                "success": True,
                "report": report,
                "message": f"当前总收入：${report['total_revenue']:.2f}，月度预测：${report['monthly_revenue_projection']:.2f}"
            }
        
        elif action == "get_pricing":
            plans = self.service.get_pricing_plans()
            return {
                "success": True,
                "pricing_plans": plans,
                "message": "定价方案获取成功"
            }
        
        else:
            return {"success": False, "message": "未知操作"}