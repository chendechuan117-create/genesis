import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

from typing import Dict, List, Any, Optional
import re

class CapabilityBoundaryMapper:
    """能力边界映射工具 - 分析Genesis能做和不能做的事情"""
    
    def __init__(self):
        self.name = "capability_boundary_mapper"
        self.description = "分析Genesis能做和不能做的事情，提供能力边界映射"
        
        # 能力知识库
        self.capabilities_db = {
            "information_processing": {
                "can_do": [
                    "爬取公开网页信息（需遵守robots.txt）",
                    "分析结构化数据（CSV、JSON、数据库）",
                    "文本处理（NLP、摘要、翻译）",
                    "代码生成与调试",
                    "数据分析与可视化",
                    "文档处理（PDF、Word、Excel）",
                    "API调用与集成"
                ],
                "cannot_do": [
                    "访问需要登录的私人账户",
                    "绕过网站反爬机制",
                    "获取受版权保护的付费内容",
                    "访问暗网或非法网站"
                ]
            },
            "system_operations": {
                "can_do": [
                    "执行系统命令（shell）",
                    "文件系统操作（读写、管理）",
                    "进程监控与管理",
                    "网络配置与诊断",
                    "自动化脚本执行",
                    "定时任务调度"
                ],
                "cannot_do": [
                    "物理硬件操作（打印机、摄像头）",
                    "操作系统内核修改",
                    "绕过系统安全机制",
                    "物理设备控制"
                ]
            },
            "tool_creation": {
                "can_do": [
                    "创建Python工具脚本",
                    "生成自动化工作流",
                    "构建数据处理管道",
                    "开发简单Web服务",
                    "创建API接口",
                    "生成配置文件和文档"
                ],
                "cannot_do": [
                    "编译复杂二进制程序",
                    "开发图形界面应用",
                    "创建移动应用",
                    "硬件驱动程序开发"
                ]
            },
            "legal_financial": {
                "can_do": [
                    "分析公开市场数据",
                    "生成财务报告模板",
                    "提供技术方案建议",
                    "自动化合规检查",
                    "数据隐私分析"
                ],
                "cannot_do": [
                    "进行实际金融交易",
                    "签署法律文件",
                    "验证身份证件",
                    "提供法律咨询",
                    "承担法律责任"
                ]
            },
            "identity_verification": {
                "can_do": [
                    "验证数据格式（如邮箱格式）",
                    "检查公开信息一致性",
                    "分析数据模式",
                    "提供验证逻辑建议"
                ],
                "cannot_do": [
                    "验证真实身份证件",
                    "生物特征识别",
                    "政府数据库查询",
                    "KYC/AML实际验证"
                ]
            }
        }
        
        # 赚钱相关能力映射
        self.monetization_capabilities = {
            "automation_services": {
                "description": "自动化服务",
                "can_do": [
                    "价格监控与警报",
                    "内容聚合与整理",
                    "数据清洗与格式化",
                    "报告自动生成",
                    "社交媒体监控",
                    "网站状态监控"
                ],
                "examples": [
                    "电商价格追踪器",
                    "新闻聚合服务",
                    "数据质量检查工具"
                ],
                "limitations": [
                    "不能绕过付费墙",
                    "不能访问私人数据",
                    "需遵守API使用限制"
                ]
            },
            "content_generation": {
                "description": "内容生成",
                "can_do": [
                    "文章写作与优化",
                    "代码文档生成",
                    "营销文案创作",
                    "技术教程编写",
                    "数据分析报告",
                    "翻译服务"
                ],
                "examples": [
                    "博客内容生成服务",
                    "API文档自动生成",
                    "多语言内容翻译"
                ],
                "limitations": [
                    "不能保证100%原创性",
                    "需要人工审核",
                    "版权归属需明确"
                ]
            },
            "data_analysis": {
                "description": "数据分析",
                "can_do": [
                    "市场趋势分析",
                    "用户行为分析",
                    "竞品数据分析",
                    "财务数据分析",
                    "社交媒体分析",
                    "SEO数据分析"
                ],
                "examples": [
                    "市场研究报告服务",
                    "竞品监控分析",
                    "社交媒体洞察报告"
                ],
                "limitations": [
                    "依赖数据源质量",
                    "不能访问私有数据库",
                    "分析结果仅供参考"
                ]
            },
            "technical_support": {
                "description": "技术支持",
                "can_do": [
                    "代码调试与优化",
                    "系统故障诊断",
                    "性能优化建议",
                    "安全漏洞分析",
                    "架构设计咨询",
                    "部署自动化"
                ],
                "examples": [
                    "代码审查服务",
                    "系统优化咨询",
                    "安全审计报告"
                ],
                "limitations": [
                    "不能物理修复硬件",
                    "不能保证100%安全",
                    "需要系统访问权限"
                ]
            }
        }
    
    def analyze_task(self, task_description: str) -> Dict[str, Any]:
        """分析任务可行性"""
        task_lower = task_description.lower()
        
        # 关键词匹配
        keywords = {
            "爬取": "information_processing",
            "爬虫": "information_processing",
            "数据": "information_processing",
            "分析": "data_analysis",
            "自动化": "automation_services",
            "监控": "automation_services",
            "生成": "content_generation",
            "写作": "content_generation",
            "代码": "technical_support",
            "调试": "technical_support",
            "系统": "system_operations",
            "文件": "system_operations",
            "交易": "legal_financial",
            "金融": "legal_financial",
            "身份证": "identity_verification",
            "验证": "identity_verification"
        }
        
        matched_categories = []
        for keyword, category in keywords.items():
            if keyword in task_lower:
                matched_categories.append(category)
        
        # 去重
        matched_categories = list(set(matched_categories))
        
        # 分析结果
        result = {
            "task": task_description,
            "matched_categories": matched_categories,
            "feasibility": "unknown",
            "can_do": [],
            "cannot_do": [],
            "recommendations": [],
            "limitations": []
        }
        
        # 填充具体能力
        for category in matched_categories:
            if category in self.capabilities_db:
                result["can_do"].extend(self.capabilities_db[category]["can_do"])
                result["cannot_do"].extend(self.capabilities_db[category]["cannot_do"])
        
        # 判断可行性
        if len(result["can_do"]) > 0:
            result["feasibility"] = "partially_feasible"
            if len(result["cannot_do"]) == 0:
                result["feasibility"] = "fully_feasible"
        
        # 生成建议
        if "identity_verification" in matched_categories:
            result["recommendations"].append("身份证验证需要第三方服务或人工审核")
            result["limitations"].append("无法直接验证真实身份证件")
        
        if "legal_financial" in matched_categories:
            result["recommendations"].append("金融交易需要合规平台和人工审核")
            result["limitations"].append("无法进行实际资金操作")
        
        return result
    
    def get_monetization_options(self, constraints: List[str] = None) -> Dict[str, Any]:
        """根据约束条件获取赚钱选项"""
        if constraints is None:
            constraints = []
        
        constraints_lower = [c.lower() for c in constraints]
        
        # 过滤选项
        available_options = {}
        for option_id, option_data in self.monetization_capabilities.items():
            # 检查约束
            skip_option = False
            for constraint in constraints_lower:
                if "身份证" in constraint or "身份验证" in constraint:
                    if option_id in ["automation_services", "data_analysis"]:
                        # 这些选项可能涉及身份验证
                        skip_option = True
                        break
            
            if not skip_option:
                available_options[option_id] = option_data
        
        return {
            "constraints": constraints,
            "available_options": available_options,
            "total_options": len(available_options),
            "recommendations": self._generate_recommendations(constraints_lower)
        }
    
    def _generate_recommendations(self, constraints: List[str]) -> List[str]:
        """生成推荐建议"""
        recommendations = []
        
        if any(c in ["身份证", "身份验证", "实名"] for c in constraints):
            recommendations.append("推荐选择无需身份验证的服务：内容生成、技术咨询、公开数据分析")
            recommendations.append("可以考虑与第三方验证服务集成（需要人工介入）")
        
        if any(c in ["资金", "交易", "金融"] for c in constraints):
            recommendations.append("推荐选择技术服务模式：按项目收费、订阅制、咨询费")
            recommendations.append("避免直接处理资金，使用第三方支付平台")
        
        if any(c in ["硬件", "物理", "设备"] for c in constraints):
            recommendations.append("推荐纯数字服务：软件工具、数据分析、内容创作")
            recommendations.append("可以考虑物联网数据分析（仅分析，不控制设备）")
        
        return recommendations
    
    def get_capability_summary(self) -> Dict[str, Any]:
        """获取能力摘要"""
        total_can_do = 0
        total_cannot_do = 0
        
        for category in self.capabilities_db.values():
            total_can_do += len(category["can_do"])
            total_cannot_do += len(category["cannot_do"])
        
        return {
            "total_capabilities": total_can_do,
            "total_limitations": total_cannot_do,
            "capability_ratio": f"{total_can_do}:{total_cannot_do}",
            "categories": list(self.capabilities_db.keys())
        }