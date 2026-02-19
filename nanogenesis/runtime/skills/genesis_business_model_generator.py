import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

from typing import Dict, List, Any
import json

class GenesisBusinessModelGenerator:
    """基于Genesis Triad架构特性生成独特盈利模式的工具"""
    
    name = "genesis_business_model_generator"
    description = "基于Genesis Triad架构特性，生成与单一AI区别化的盈利模式建议"
    
    parameters = {
        "type": "object",
        "properties": {
            "architecture_features": {
                "type": "string", 
                "description": "Genesis Triad架构的核心特性描述"
            }
        },
        "required": ["architecture_features"]
    }
    
    def execute(self, architecture_features: str) -> Dict[str, Any]:
        """基于架构特性生成盈利模式"""
        
        # 架构特性到商业价值的映射逻辑
        architecture_to_value = {
            "职责分离": {
                "商业价值": "高可靠性、模块化服务、故障隔离",
                "盈利模式": [
                    "企业级SLA订阅服务（99.9%可用性保证）",
                    "模块化功能订阅（可单独购买洞察、决策、执行服务）",
                    "故障恢复和容灾服务"
                ]
            },
            "多代理协作": {
                "商业价值": "复杂流程自动化、多任务并行处理",
                "盈利模式": [
                    "端到端业务流程自动化服务",
                    "多部门协同工作流解决方案",
                    "实时监控和干预服务"
                ]
            },
            "意图识别（洞察者）": {
                "商业价值": "精准需求理解、上下文感知",
                "盈利模式": [
                    "客户意图分析服务（市场调研、用户研究）",
                    "智能需求预测和推荐系统",
                    "上下文感知的个性化服务"
                ]
            },
            "元认知决策（裁决者）": {
                "商业价值": "战略规划、风险评估、路径优化",
                "盈利模式": [
                    "企业战略咨询和决策支持",
                    "风险评估和应急预案服务",
                    "复杂项目规划和路径优化"
                ]
            },
            "工具执行（执行者）": {
                "商业价值": "实际任务落地、工具链集成",
                "盈利模式": [
                    "自动化运维和部署服务",
                    "跨平台工具链集成服务",
                    "定制化执行脚本和工具开发"
                ]
            }
        }
        
        # 分析输入的特性
        features = architecture_features.lower()
        matched_features = []
        
        for key in architecture_to_value:
            if key.lower() in features:
                matched_features.append(key)
        
        # 生成盈利模式建议
        revenue_models = []
        unique_value_propositions = []
        
        for feature in matched_features:
            value_data = architecture_to_value[feature]
            unique_value_propositions.append(f"{feature} → {value_data['商业价值']}")
            revenue_models.extend(value_data['盈利模式'])
        
        # 如果没有匹配到特定特性，提供通用但基于Triad的建议
        if not matched_features:
            unique_value_propositions = [
                "Triad架构 → 模块化、可扩展、高可靠的AI系统",
                "多角色协作 → 复杂任务分解和执行能力",
                "职责分离 → 专业化的AI服务交付"
            ]
            
            revenue_models = [
                "分层订阅模式：基础层（单一AI功能）、专业层（Triad协作）、企业层（全功能+定制）",
                "按角色计费：洞察服务费、决策服务费、执行服务费",
                "项目制服务：基于Triad架构的端到端解决方案",
                "培训认证：Genesis Triad架构师认证课程",
                "技术授权：Triad架构的技术许可和专利授权"
            ]
        
        # 去重
        revenue_models = list(dict.fromkeys(revenue_models))
        
        return {
            "架构特性": matched_features if matched_features else ["Triad架构（通用）"],
            "独特价值主张": unique_value_propositions,
            "基于架构的盈利模式": revenue_models,
            "与传统单一AI的区别": [
                "模块化收费 vs 统一收费",
                "按角色/功能订阅 vs 整体订阅",
                "复杂流程服务 vs 简单问答服务",
                "企业级可靠性 vs 消费级可用性",
                "端到端解决方案 vs 单点工具"
            ],
            "目标客户": [
                "需要复杂业务流程自动化的企业",
                "对AI系统可靠性要求高的金融机构",
                "需要多部门协同的大型组织",
                "技术公司寻求AI架构升级"
            ]
        }

# 创建工具实例
tool = GenesisBusinessModelGenerator()