#!/usr/bin/env python3
"""
技能迁移脚本 v2 - 将 skills/ 目录下的 Python 工具文件迁移到 NodeVault 中
按照 META_SKILLS_BLUEPRINT.md 的蓝图设计
"""

import os
import sys
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from genesis.v4.manager import NodeVault

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_tool_info_from_source(source_code: str) -> Dict[str, Any]:
    """
    从 Python 源码中提取工具信息
    返回: {name, description, metadata_signature}
    """
    info = {
        "name": "",
        "description": "",
        "metadata_signature": {}
    }
    
    # 提取类名
    class_match = re.search(r'class\s+(\w+Tool)\s*\(', source_code)
    if class_match:
        class_name = class_match.group(1)
        # 将类名转换为工具名（驼峰转下划线）
        tool_name = re.sub(r'(?<!^)(?=[A-Z])', '_', class_name).lower()
        info["name"] = tool_name
    
    # 提取 description
    desc_match = re.search(r'@property\s*\ndef\s+description\s*\(self\)\s*->\s*str:\s*return\s+"([^"]+)"', source_code)
    if not desc_match:
        desc_match = re.search(r'@property\s*\ndef\s+description\s*\(self\)\s*->\s*str:\s*return\s+\'([^\']+)\'', source_code)
    if desc_match:
        info["description"] = desc_match.group(1)
    
    # 分析源码内容，提取可能的 metadata_signature
    metadata = {}
    
    # 检查是否包含特定关键词
    keywords = {
        "n8n": ["n8n", "workflow", "automation"],
        "browser": ["browser", "selenium", "playwright", "web"],
        "wechat": ["wechat", "微信"],
        "github": ["github", "repo", "repository"],
        "file": ["file", "analyzer", "reader"],
        "network": ["network", "diagnostic", "ip"],
        "ai": ["ai", "ollama", "local_ai"],
        "sqlite": ["sqlite", "database"],
        "jwt": ["jwt", "token"],
        "ocr": ["ocr", "image"],
        "deployment": ["deployment", "monitor"],
        "system": ["system", "monitor"]
    }
    
    source_lower = source_code.lower()
    for category, words in keywords.items():
        for word in words:
            if word in source_lower:
                if category == "n8n":
                    metadata["framework"] = "n8n"
                    metadata["task_kind"] = "automation"
                elif category == "browser":
                    metadata["task_kind"] = "browser_automation"
                elif category == "wechat":
                    metadata["framework"] = "wechat_work"
                    metadata["task_kind"] = "messaging"
                elif category == "github":
                    metadata["task_kind"] = "github_operations"
                elif category == "file":
                    metadata["task_kind"] = "file_analysis"
                elif category == "network":
                    metadata["task_kind"] = "network_diagnostic"
                elif category == "ai":
                    metadata["framework"] = "ollama"
                    metadata["task_kind"] = "ai_assistance"
                elif category == "sqlite":
                    metadata["task_kind"] = "database_operations"
                elif category == "jwt":
                    metadata["task_kind"] = "security_analysis"
                elif category == "ocr":
                    metadata["task_kind"] = "image_analysis"
                elif category == "deployment":
                    metadata["task_kind"] = "deployment_monitoring"
                elif category == "system":
                    metadata["task_kind"] = "system_monitoring"
                break
    
    # 如果没有检测到特定框架，使用通用标签
    if not metadata:
        metadata["task_kind"] = "tool_execution"
    
    info["metadata_signature"] = metadata
    return info

def migrate_skill_file(file_path: Path, vault: NodeVault) -> bool:
    """迁移单个技能文件到 NodeVault"""
    try:
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        # 跳过 __init__.py
        if file_path.name == "__init__.py":
            logger.info(f"跳过 __init__.py 文件: {file_path}")
            return True
        
        # 提取工具信息
        tool_info = extract_tool_info_from_source(source_code)
        
        if not tool_info["name"]:
            logger.warning(f"无法从文件中提取工具名称: {file_path}")
            return False
        
        # 生成节点ID
        node_id = f"TOOL_{tool_info['name'].upper()}"
        
        # 检查是否已存在
        existing = vault.get_node_content(node_id)
        if existing:
            logger.info(f"工具节点已存在: {node_id}")
            return True
        
        # 创建工具节点
        title = tool_info["description"] or f"工具: {tool_info['name']}"
        
        vault.create_node(
            node_id=node_id,
            ntype="TOOL",
            title=title,
            human_translation=f"Python工具: {tool_info['name']}",
            tags=f"tool,python,skill,{tool_info['name']}",
            full_content=source_code,
            source="skill_migration",
            metadata_signature=tool_info["metadata_signature"],
            confidence_score=0.8,
            last_verified_at="2024-01-01 00:00:00",
            verification_source="file_migration"
        )
        
        logger.info(f"✓ 迁移成功: {file_path.name} -> {node_id}")
        return True
        
    except Exception as e:
        logger.error(f"迁移失败 {file_path}: {e}")
        return False

def query_tool_nodes(vault: NodeVault) -> List[Dict[str, Any]]:
    """查询数据库中的 TOOL 节点"""
    try:
        conn = vault._conn
        cursor = conn.execute(
            "SELECT node_id, type, title FROM knowledge_nodes WHERE type = ? ORDER BY created_at DESC",
            ("TOOL",)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"查询 TOOL 节点失败: {e}")
        return []

def main():
    """主迁移函数"""
    # 初始化 NodeVault
    vault = NodeVault()
    
    # skills 目录路径
    skills_dir = Path(__file__).parent / "genesis" / "skills"
    
    if not skills_dir.exists():
        logger.error(f"skills 目录不存在: {skills_dir}")
        return False
    
    # 获取所有 Python 文件
    skill_files = list(skills_dir.glob("*.py"))
    
    if not skill_files:
        logger.warning("未找到技能文件")
        return False
    
    logger.info(f"找到 {len(skill_files)} 个技能文件")
    
    # 迁移所有文件
    success_count = 0
    failed_files = []
    
    for skill_file in skill_files:
        if migrate_skill_file(skill_file, vault):
            success_count += 1
        else:
            failed_files.append(skill_file.name)
    
    # 输出统计信息
    logger.info(f"\n迁移完成:")
    logger.info(f"  成功: {success_count}/{len(skill_files)}")
    
    if failed_files:
        logger.info(f"  失败: {len(failed_files)}")
        for f in failed_files:
            logger.info(f"    - {f}")
    
    # 验证迁移结果
    logger.info("\n验证迁移结果:")
    tool_nodes = query_tool_nodes(vault)
    logger.info(f"数据库中的 TOOL 节点数量: {len(tool_nodes)}")
    
    # 显示部分迁移的工具
    if tool_nodes:
        logger.info("\n已迁移的工具节点示例:")
        for i, node in enumerate(tool_nodes[:10]):
            logger.info(f"  {i+1}. {node['node_id']}: {node['title'][:50]}...")
    
    return len(failed_files) == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)