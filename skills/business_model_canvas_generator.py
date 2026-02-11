import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

from typing import Dict, Any, List
import json

class BusinessModelCanvasGenerator:
    """生成商业模型画布的工具"""
    
    name = "business_model_canvas_generator"
    description = "根据核心价值主张生成商业模型画布（九大模块分析）"
    parameters = {
        "type": "object",
        "properties": {
            "value_proposition": {
                "type": "string", 
                "description": "核心价值主张（例如：AI辅助决策平台、智能助手服务等）"
            },
            "include_examples": {
                "type": "boolean",
                "description": "是否包含具体示例",
                "default": True
            },
            "format": {
                "type": "string",
                "description": "输出格式：text, json, markdown",
                "default": "markdown"
            }
        },
        "required": ["value_proposition"]
    }
    
    def execute(self, value_proposition: str, include_examples: bool = True, format: str = "markdown") -> Dict[str, Any]:
        """生成商业模型画布"""
        
        # 基于AI系统特性的商业模型分析
        canvas = {
            "value_proposition": value_proposition,
            "customer_segments": self._get_customer_segments(value_proposition),
            "value_propositions": self._get_value_propositions(value_proposition),
            "channels": self._get_channels(),
            "customer_relationships": self._get_customer_relationships(),
            "revenue_streams": self._get_revenue_streams(),
            "key_resources": self._get_key_resources(),
            "key_activities": self._get_key_activities(),
            "key_partnerships": self._get_key_partnerships(),
            "cost_structure": self._get_cost_structure(),
            "assumptions_and_risks": self._get_assumptions_and_risks()
        }
        
        if format == "json":
            return {"status": "success", "canvas": canvas}
        else:
            return {"status": "success", "output": self._format_canvas(canvas, format, include_examples)}
    
    def _get_customer_segments(self, value_prop: str) -> List[str]:
        """客户细分"""
        segments = [
            "个人用户（开发者、研究人员、学生）",
            "中小型企业（需要AI能力但无技术团队）",
            "大型企业（需要定制化AI解决方案）",
            "教育机构（教学和研究用途）",
            "政府和非营利组织（公共服务）"
        ]
        
        if "决策" in value_prop:
            segments.extend(["企业管理者", "数据分析师", "战略规划部门"])
        elif "助手" in value_prop:
            segments.extend(["个人助理用户", "客服团队", "内容创作者"])
        
        return segments
    
    def _get_value_propositions(self, value_prop: str) -> List[str]:
        """价值主张"""
        propositions = [
            "24/7智能助手服务",
            "多任务处理能力",
            "快速信息检索和分析",
            "代码生成和调试",
            "文档处理和总结",
            "个性化学习指导"
        ]
        
        if "决策" in value_prop:
            propositions.extend([
                "数据驱动的决策支持",
                "风险分析和预测",
                "多方案对比评估",
                "实时市场情报"
            ])
        
        return propositions
    
    def _get_channels(self) -> List[str]:
        """渠道通路"""
        return [
            "官方网站和API文档",
            "开源社区（GitHub、GitLab）",
            "应用商店和插件市场",
            "技术博客和教程",
            "开发者大会和技术沙龙",
            "企业销售团队",
            "合作伙伴网络"
        ]
    
    def _get_customer_relationships(self) -> List[str]:
        """客户关系"""
        return [
            "自助服务（文档、教程）",
            "社区支持（论坛、Discord）",
            "技术支持（工单系统）",
            "企业级客户支持（专属客户经理）",
            "培训和教育服务",
            "持续更新和维护"
        ]
    
    def _get_revenue_streams(self) -> List[Dict[str, Any]]:
        """收入来源"""
        streams = [
            {"name": "API调用费用", "model": "按使用量计费（每千次调用）", "target": "所有用户"},
            {"name": "订阅服务", "model": "月费/年费（基础版、专业版、企业版）", "target": "个人和企业用户"},
            {"name": "企业定制", "model": "项目制收费（一次性或年度维护）", "target": "大型企业"},
            {"name": "培训服务", "model": "按课程或按小时收费", "target": "企业和教育机构"},
            {"name": "数据服务", "model": "数据API或数据集销售", "target": "研究机构和企业"},
            {"name": "广告收入", "model": "精准广告投放", "target": "免费用户"},
            {"name": "联盟营销", "model": "推荐相关工具和服务获得佣金", "target": "所有用户"}
        ]
        return streams
    
    def _get_key_resources(self) -> List[str]:
        """核心资源"""
        return [
            "AI模型和算法",
            "计算基础设施（服务器、GPU）",
            "数据存储和处理系统",
            "开发团队（AI工程师、产品经理）",
            "知识产权（专利、算法）",
            "用户数据和反馈",
            "品牌和声誉"
        ]
    
    def _get_key_activities(self) -> List[str]:
        """关键业务"""
        return [
            "AI模型训练和优化",
            "系统开发和维护",
            "数据收集和处理",
            "用户体验设计",
            "市场推广和销售",
            "客户支持和服务",
            "安全和合规管理"
        ]
    
    def _get_key_partnerships(self) -> List[str]:
        """重要合作"""
        return [
            "云服务提供商（AWS、Azure、Google Cloud）",
            "硬件供应商（NVIDIA、Intel）",
            "开源社区和贡献者",
            "大学和研究机构",
            "系统集成商",
            "分销渠道合作伙伴",
            "内容提供商（新闻、数据源）"
        ]
    
    def _get_cost_structure(self) -> List[Dict[str, Any]]:
        """成本结构"""
        costs = [
            {"category": "基础设施", "items": ["服务器租赁", "GPU计算", "存储成本", "网络带宽"]},
            {"category": "人力成本", "items": ["研发团队工资", "运营团队", "销售和市场", "管理成本"]},
            {"category": "研发投入", "items": ["模型训练", "算法研究", "产品开发", "测试验证"]},
            {"category": "运营成本", "items": ["电力和冷却", "软件许可", "办公场地", "法律和合规"]},
            {"category": "市场费用", "items": ["广告投放", "渠道佣金", "活动赞助", "内容制作"]}
        ]
        return costs
    
    def _get_assumptions_and_risks(self) -> Dict[str, List[str]]:
        """假设和风险"""
        return {
            "关键假设": [
                "AI技术持续进步且成本下降",
                "市场需求稳定增长",
                "用户愿意为AI服务付费",
                "能够保持技术领先优势",
                "法律法规支持AI发展"
            ],
            "主要风险": [
                "技术被快速超越",
                "数据隐私和安全问题",
                "法律法规变化",
                "市场竞争加剧",
                "用户接受度不足",
                "成本控制失败"
            ]
        }
    
    def _format_canvas(self, canvas: Dict[str, Any], format: str, include_examples: bool) -> str:
        """格式化输出"""
        if format == "text":
            return self._format_text(canvas, include_examples)
        else:  # markdown
            return self._format_markdown(canvas, include_examples)
    
    def _format_markdown(self, canvas: Dict[str, Any], include_examples: bool) -> str:
        """Markdown格式输出"""
        output = f"# 商业模型画布：{canvas['value_proposition']}\n\n"
        
        output += "## 1. 客户细分\n"
        for segment in canvas['customer_segments']:
            output += f"- {segment}\n"
        
        output += "\n## 2. 价值主张\n"
        for prop in canvas['value_propositions']:
            output += f"- {prop}\n"
        
        output += "\n## 3. 渠道通路\n"
        for channel in canvas['channels']:
            output += f"- {channel}\n"
        
        output += "\n## 4. 客户关系\n"
        for relationship in canvas['customer_relationships']:
            output += f"- {relationship}\n"
        
        output += "\n## 5. 收入来源\n"
        for stream in canvas['revenue_streams']:
            output += f"- **{stream['name']}**：{stream['model']}（目标：{stream['target']}）\n"
        
        output += "\n## 6. 核心资源\n"
        for resource in canvas['key_resources']:
            output += f"- {resource}\n"
        
        output += "\n## 7. 关键业务\n"
        for activity in canvas['key_activities']:
            output += f"- {activity}\n"
        
        output += "\n## 8. 重要合作\n"
        for partnership in canvas['key_partnerships']:
            output += f"- {partnership}\n"
        
        output += "\n## 9. 成本结构\n"
        for cost in canvas['cost_structure']:
            output += f"- **{cost['category']}**：{', '.join(cost['items'])}\n"
        
        output += "\n## 10. 假设与风险\n"
        output += "### 关键假设\n"
        for assumption in canvas['assumptions_and_risks']['关键假设']:
            output += f"- {assumption}\n"
        
        output += "\n### 主要风险\n"
        for risk in canvas['assumptions_and_risks']['主要风险']:
            output += f"- {risk}\n"
        
        if include_examples:
            output += "\n---\n"
            output += "## 具体实施示例\n\n"
            output += "### 第一阶段（0-6个月）：验证MVP\n"
            output += "1. **免费增值模式**：基础功能免费，高级功能收费\n"
            output += "2. **开发者API**：按调用次数收费（$0.01/100次调用）\n"
            output += "3. **企业试用**：提供30天免费试用，然后按用户数收费\n\n"
            
            output += "### 第二阶段（6-18个月）：规模化\n"
            output += "1. **分层订阅**：个人版$9.99/月，团队版$49.99/月，企业版定制\n"
            output += "2. **垂直解决方案**：针对特定行业（金融、医疗、教育）的定制方案\n"
            output += "3. **生态系统**：应用商店，第三方开发者分成\n\n"
            
            output += "### 第三阶段（18-36个月）：平台化\n"
            output += "1. **数据服务**：匿名化数据分析和洞察报告\n"
            output += "2. **白标解决方案**：为其他公司提供品牌化的AI服务\n"
            output += "3. **硬件集成**：与智能设备厂商合作\n"
        
        return output
    
    def _format_text(self, canvas: Dict[str, Any], include_examples: bool) -> str:
        """纯文本格式输出"""
        # 简化实现，主要使用markdown
        return self._format_markdown(canvas, include_examples).replace('# ', '').replace('## ', '').replace('### ', '')


# 导出工具
tool = BusinessModelCanvasGenerator()