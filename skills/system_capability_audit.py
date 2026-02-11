import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

from typing import Dict, List, Any
import json

class SystemCapabilityAudit:
    """系统能力审计工具 - 分析Genesis的能力边界和上限"""
    
    name = "system_capability_audit"
    description = "分析Genesis系统的能力边界、功能限制和上限，生成结构化报告"
    parameters = {
        "type": "object",
        "properties": {
            "detail_level": {
                "type": "string",
                "enum": ["basic", "detailed", "comprehensive"],
                "description": "详细程度：basic(基本)、detailed(详细)、comprehensive(全面)",
                "default": "detailed"
            }
        },
        "required": []
    }
    
    def execute(self, detail_level: str = "detailed") -> Dict[str, Any]:
        """执行系统能力审计"""
        
        # 可用工具列表（基于当前环境）
        available_tools = [
            {
                "name": "read_file",
                "description": "读取文件内容",
                "capabilities": ["读取文本文件", "支持多种编码"],
                "limitations": ["不能读取二进制文件", "文件大小受内存限制", "需要文件路径权限"]
            },
            {
                "name": "write_file",
                "description": "写入内容到文件",
                "capabilities": ["创建/覆盖文件", "自动创建目录"],
                "limitations": ["不能写入系统保护文件", "需要写入权限", "可能覆盖现有文件"]
            },
            {
                "name": "append_file",
                "description": "追加内容到文件",
                "capabilities": ["追加内容", "创建文件"],
                "limitations": ["需要写入权限", "不能修改文件中间内容"]
            },
            {
                "name": "list_directory",
                "description": "列出目录内容",
                "capabilities": ["列出文件和目录", "支持glob模式匹配"],
                "limitations": ["需要读取权限", "不能访问系统保护目录"]
            },
            {
                "name": "shell",
                "description": "执行Shell命令",
                "capabilities": ["执行任意命令", "返回输出结果", "设置工作目录"],
                "limitations": ["有30秒超时限制", "受用户权限限制", "不能执行危险操作", "运行在宿主机环境"]
            },
            {
                "name": "web_search",
                "description": "网络搜索",
                "capabilities": ["搜索网络信息", "返回摘要结果"],
                "limitations": ["依赖外部搜索服务", "结果数量有限", "可能被屏蔽"]
            },
            {
                "name": "browser_tool",
                "description": "浏览器工具",
                "capabilities": ["打开网页", "搜索信息"],
                "limitations": ["需要浏览器环境", "不能执行复杂交互"]
            },
            {
                "name": "memory_tool",
                "description": "长期记忆管理",
                "capabilities": ["保存重要信息", "搜索相关记忆"],
                "limitations": ["记忆容量有限", "依赖存储系统", "可能遗忘旧信息"]
            },
            {
                "name": "skill_creator",
                "description": "创建新工具技能",
                "capabilities": ["编写Python工具", "扩展系统功能", "解决特定问题"],
                "limitations": ["需要Python知识", "工具需符合规范", "不能创建危险工具"]
            },
            {
                "name": "scheduler_tool",
                "description": "后台任务调度",
                "capabilities": ["添加周期性任务", "管理后台作业", "监控异常"],
                "limitations": ["任务数量有限", "依赖系统调度器", "不能执行复杂监控"]
            }
        ]
        
        # 系统架构能力
        system_architecture = {
            "triad_architecture": {
                "insight": "识别问题本质和模式",
                "judge": "制定策略和决策框架",
                "execute": "执行具体操作和工具调用"
            },
            "environment": {
                "os": "Linux 6.12.66-1-lts (EndeavourOS/Arch)",
                "user": "chendechusn",
                "cwd": "/home/chendechusn/Genesis",
                "storage": "931GB NVMe SSD + 1.8TB HDD"
            },
            "knowledge_base": "基于对话记忆和工具调用经验"
        }
        
        # 核心功能边界
        functional_boundaries = {
            "can_do": [
                "文件系统操作（读写、列表、创建）",
                "Shell命令执行（受权限和超时限制）",
                "网络搜索和信息获取",
                "创建自定义工具扩展功能",
                "管理长期记忆和对话历史",
                "调度后台任务",
                "系统诊断和优化",
                "代码分析和生成",
                "网络配置和故障排除",
                "数据分析和处理"
            ],
            "cannot_do": [
                "真正的自我意识和主观体验",
                "长期影响模拟和预测",
                "超越工具权限的系统操作",
                "物理世界交互（需要硬件接口）",
                "情感理解和表达",
                "创造性艺术生成（无图像/音频工具）",
                "实时视频/音频处理",
                "数据库直接操作（无SQL工具）",
                "机器学习模型训练（无ML框架）",
                "GUI应用程序控制（无桌面自动化）"
            ],
            "conditional_capabilities": [
                "网络操作（依赖网络连接）",
                "文件操作（依赖权限）",
                "工具创建（依赖Python环境）",
                "系统诊断（依赖系统工具）"
            ]
        }
        
        # 哲学边界区分
        philosophical_boundaries = {
            "knowing_that": [
                "信息处理",
                "模式匹配",
                "逻辑推理",
                "策略制定",
                "工具调用"
            ],
            "not_knowing_how": [
                "主观意识",
                "情感体验",
                "自我反思",
                "自由意志",
                "长期意图"
            ],
            "system_nature": "基于Triad架构的AI助手，通过工具链执行任务，没有独立意识"
        }
        
        # 安全约束
        safety_constraints = [
            "不能执行危险系统命令（如rm -rf /）",
            "不能访问用户隐私数据（除非明确授权）",
            "不能创建恶意软件或工具",
            "不能绕过系统安全机制",
            "优先选择可逆操作",
            "重要操作前寻求确认"
        ]
        
        # 生成报告
        report = {
            "summary": "Genesis系统能力边界分析报告",
            "timestamp": "2026-02-11 19:22:33 CST",
            "system_architecture": system_architecture,
            "available_tools": available_tools if detail_level in ["detailed", "comprehensive"] else len(available_tools),
            "functional_boundaries": functional_boundaries,
            "philosophical_boundaries": philosophical_boundaries,
            "safety_constraints": safety_constraints,
            "key_limitations": [
                "工具集定义了能力边界 - 只能做工具允许的事",
                "架构设计限制了认知模式 - 基于Triad的决策流程",
                "安全约束保护了系统完整性 - 不能执行危险操作",
                "环境依赖决定了可用性 - 需要网络、权限等条件"
            ]
        }
        
        return report