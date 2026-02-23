import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import re
import json
import subprocess
from typing import Dict, List, Optional

class ProxyConfigFinder(Tool):
    @property
    def name(self) -> str:
        return "proxy_config_finder"
        
    @property
    def description(self) -> str:
        return "搜索和评估性价比高的代理配置方案，包括免费节点、付费服务、机场推荐等"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "search_type": {
                    "type": "string", 
                    "enum": ["free_nodes", "paid_services", "airports", "all"],
                    "description": "搜索类型：免费节点、付费服务、机场推荐、全部",
                    "default": "all"
                },
                "budget": {
                    "type": "string",
                    "description": "预算范围（如：免费、10元/月、50元/月）",
                    "default": "性价比高"
                },
                "features": {
                    "type": "string",
                    "description": "需要的特性（如：高速、稳定、解锁Netflix、多节点）",
                    "default": "高速稳定"
                }
            },
            "required": []
        }
        
    async def execute(self, search_type: str = "all", budget: str = "性价比高", features: str = "高速稳定") -> str:
        """搜索代理配置方案"""
        
        # 收集已知的代理资源信息
        resources = {
            "free_nodes": [
                {
                    "name": "FreeV2ray",
                    "description": "免费V2Ray节点分享",
                    "url": "https://github.com/freefq/free",
                    "features": ["每日更新", "多协议", "不稳定"],
                    "cost": "免费",
                    "rating": "★★☆☆☆"
                },
                {
                    "name": "v2ray免费节点",
                    "description": "GitHub上的免费节点列表",
                    "url": "https://github.com/mahdibland/SSAggregator",
                    "features": ["聚合多个源", "自动更新", "可用性一般"],
                    "cost": "免费",
                    "rating": "★★★☆☆"
                }
            ],
            "paid_services": [
                {
                    "name": "JustMySocks",
                    "description": "老牌Shadowsocks服务商",
                    "url": "https://justmysocks.net",
                    "features": ["稳定", "速度快", "支持支付宝"],
                    "cost": "$2.88/月起",
                    "rating": "★★★★☆"
                },
                {
                    "name": "V2Ray.Tech",
                    "description": "专业V2Ray服务",
                    "url": "https://v2ray.tech",
                    "features": ["原生V2Ray", "高速线路", "多节点"],
                    "cost": "¥15/月起",
                    "rating": "★★★★☆"
                },
                {
                    "name": "WannaFlix",
                    "description": "支持Netflix解锁",
                    "url": "https://wannaflix.com",
                    "features": ["解锁流媒体", "全球节点", "中文客服"],
                    "cost": "$4.99/月",
                    "rating": "★★★★☆"
                }
            ],
            "airports": [
                {
                    "name": "Nexitally",
                    "description": "知名机场，节点多速度快",
                    "url": "https://nexitally.com",
                    "features": ["IPLC专线", "游戏加速", "多协议"],
                    "cost": "¥15/月起",
                    "rating": "★★★★★"
                },
                {
                    "name": "MoeCloud",
                    "description": "二次元风格机场",
                    "url": "https://moec.lol",
                    "features": ["线路优化", "解锁流媒体", "社区活跃"],
                    "cost": "¥12/月起",
                    "rating": "★★★★☆"
                },
                {
                    "name": "V2Board机场",
                    "description": "基于V2Board的机场",
                    "url": "https://panel.v2board.com",
                    "features": ["管理方便", "订阅链接", "性价比高"],
                    "cost": "¥10-30/月",
                    "rating": "★★★☆☆"
                }
            ]
        }
        
        # 根据搜索类型筛选
        if search_type == "all":
            selected_resources = []
            for category in resources.values():
                selected_resources.extend(category)
        else:
            selected_resources = resources.get(search_type, [])
        
        # 根据预算和特性过滤
        filtered_resources = []
        for resource in selected_resources:
            # 简单的关键词匹配
            budget_match = True
            if budget != "性价比高":
                if "免费" in budget and "免费" not in resource["cost"]:
                    budget_match = False
                elif "元" in budget and "免费" in resource["cost"]:
                    budget_match = False
            
            features_match = True
            if features:
                feature_list = features.split()
                for f in feature_list:
                    if f not in str(resource["features"]):
                        features_match = False
                        break
            
            if budget_match and features_match:
                filtered_resources.append(resource)
        
        # 生成报告
        if not filtered_resources:
            return "未找到符合要求的代理配置方案。建议放宽搜索条件。"
        
        report = f"# 代理配置方案搜索报告\n\n"
        report += f"**搜索条件**: {search_type} | 预算: {budget} | 特性: {features}\n\n"
        
        for i, resource in enumerate(filtered_resources, 1):
            report += f"## {i}. {resource['name']}\n"
            report += f"- **描述**: {resource['description']}\n"
            report += f"- **网址**: {resource['url']}\n"
            report += f"- **特性**: {', '.join(resource['features'])}\n"
            report += f"- **价格**: {resource['cost']}\n"
            report += f"- **评分**: {resource['rating']}\n\n"
        
        report += "## 使用建议\n"
        report += "1. **免费节点**: 适合临时使用或测试，稳定性较差\n"
        report += "2. **付费服务**: 稳定可靠，适合长期使用\n"
        report += "3. **机场**: 节点多，线路优化好，性价比高\n\n"
        report += "## 配置步骤\n"
        report += "1. 选择服务并购买/获取订阅链接\n"
        report += "2. 在v2raya中添加订阅链接\n"
        report += "3. 选择节点并启用代理\n"
        
        return report