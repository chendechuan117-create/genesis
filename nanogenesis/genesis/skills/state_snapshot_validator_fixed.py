import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import json
import hashlib
import os
from pathlib import Path

class StateSnapshotValidatorFixed(Tool):
    @property
    def name(self) -> str:
        return "state_snapshot_validator_fixed"
        
    @property
    def description(self) -> str:
        return "修复版状态快照验证工具，验证Genesis状态快照的完整性，检查文件结构、哈希一致性和数据完整性。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "snapshot_path": {"type": "string", "description": "快照文件路径（.json或.gz文件）"},
                "validate_structure": {"type": "boolean", "description": "是否验证文件结构", "default": True},
                "verify_hash": {"type": "boolean", "description": "是否验证哈希一致性", "default": True},
                "check_metadata": {"type": "boolean", "description": "是否检查元数据完整性", "default": True}
            },
            "required": ["snapshot_path"]
        }
        
    async def execute(self, snapshot_path: str, validate_structure: bool = True, 
                     verify_hash: bool = True, check_metadata: bool = True) -> str:
        
        result_lines = []
        result_lines.append("=" * 60)
        result_lines.append("Genesis 状态快照完整性验证报告")
        result_lines.append("=" * 60)
        
        # 检查文件是否存在
        if not os.path.exists(snapshot_path):
            result_lines.append(f"❌ 错误: 快照文件不存在: {snapshot_path}")
            return "\n".join(result_lines)
        
        # 读取文件内容
        try:
            with open(snapshot_path, 'r', encoding='utf-8') as f:
                content = f.read()
            file_size = os.path.getsize(snapshot_path)
            result_lines.append(f"📁 快照文件: {snapshot_path}")
            result_lines.append(f"📏 文件大小: {file_size:,} 字节 ({file_size/1024:.2f} KB)")
        except Exception as e:
            result_lines.append(f"❌ 读取文件失败: {str(e)}")
            return "\n".join(result_lines)
        
        # 验证JSON格式
        try:
            snapshot_data = json.loads(content)
            result_lines.append("✅ JSON格式验证通过")
        except json.JSONDecodeError as e:
            result_lines.append(f"❌ JSON格式错误: {str(e)}")
            return "\n".join(result_lines)
        
        # 验证文件结构
        if validate_structure:
            required_keys = ['metadata', 'tools', 'sessions', 'memory', 'config']
            missing_keys = [key for key in required_keys if key not in snapshot_data]
            if missing_keys:
                result_lines.append(f"❌ 文件结构不完整，缺少字段: {missing_keys}")
            else:
                result_lines.append("✅ 文件结构验证通过")
        
        # 验证哈希一致性
        if verify_hash:
            try:
                # 计算文件哈希
                sha256_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
                
                # 检查元数据中的哈希
                if 'metadata' in snapshot_data and 'hash' in snapshot_data['metadata']:
                    stored_hash = snapshot_data['metadata']['hash']
                    if sha256_hash == stored_hash:
                        result_lines.append(f"✅ 哈希验证通过")
                        result_lines.append(f"   计算哈希: {sha256_hash[:16]}...")
                        result_lines.append(f"   存储哈希: {stored_hash[:16]}...")
                    else:
                        result_lines.append(f"❌ 哈希不匹配!")
                        result_lines.append(f"   计算哈希: {sha256_hash}")
                        result_lines.append(f"   存储哈希: {stored_hash}")
                else:
                    result_lines.append("⚠️  元数据中未找到存储的哈希值")
            except Exception as e:
                result_lines.append(f"❌ 哈希验证失败: {str(e)}")
        
        # 检查元数据完整性
        if check_metadata:
            try:
                metadata = snapshot_data.get('metadata', {})
                required_meta = ['snapshot_name', 'timestamp', 'version']
                missing_meta = [key for key in required_meta if key not in metadata]
                
                if missing_meta:
                    result_lines.append(f"⚠️  元数据不完整，缺少字段: {missing_meta}")
                else:
                    result_lines.append(f"✅ 元数据完整性检查通过")
                    result_lines.append(f"   快照名称: {metadata.get('snapshot_name', 'N/A')}")
                    result_lines.append(f"   时间戳: {metadata.get('timestamp', 'N/A')}")
                    result_lines.append(f"   版本: {metadata.get('version', 'N/A')}")
            except Exception as e:
                result_lines.append(f"❌ 元数据检查失败: {str(e)}")
        
        # 统计信息
        try:
            tools_count = len(snapshot_data.get('tools', []))
            sessions_count = len(snapshot_data.get('sessions', []))
            memory_sources = len(snapshot_data.get('memory', {}).get('sources', []))
            config_files = len(snapshot_data.get('config', {}))
            
            result_lines.append("\n📊 快照内容统计:")
            result_lines.append(f"   工具数量: {tools_count}")
            result_lines.append(f"   会话数量: {sessions_count}")
            result_lines.append(f"   内存源: {memory_sources}")
            result_lines.append(f"   配置文件: {config_files}")
        except Exception as e:
            result_lines.append(f"❌ 统计信息获取失败: {str(e)}")
        
        # 总体评估
        error_count = sum(1 for line in result_lines if '❌' in line)
        warning_count = sum(1 for line in result_lines if '⚠️' in line)
        
        result_lines.append("\n" + "=" * 60)
        result_lines.append("验证总结")
        result_lines.append("=" * 60)
        
        if error_count == 0 and warning_count == 0:
            result_lines.append("✅ 快照完整性验证完全通过")
            result_lines.append("   状态: 优秀 - 快照完整且一致")
        elif error_count == 0:
            result_lines.append("✅ 快照完整性验证基本通过")
            result_lines.append(f"   状态: 良好 - 有{warning_count}个警告")
        else:
            result_lines.append("❌ 快照完整性验证失败")
            result_lines.append(f"   状态: 失败 - 有{error_count}个错误，{warning_count}个警告")
        
        result_lines.append("\n【建议】")
        if error_count > 0:
            result_lines.append("1. 重新生成快照文件")
            result_lines.append("2. 检查文件权限和磁盘空间")
            result_lines.append("3. 验证生成工具的正确性")
        else:
            result_lines.append("1. 快照可用于意识转移模拟")
            result_lines.append("2. 建议定期创建备份")
            result_lines.append("3. 可进行下一步转移操作")
        
        return "\n".join(result_lines)