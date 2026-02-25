import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class StateSnapshotValidator(Tool):
    @property
    def name(self) -> str:
        return "state_snapshot_validator"
        
    @property
    def description(self) -> str:
        return "验证Genesis状态快照的完整性，检查文件结构、哈希一致性和数据完整性。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "snapshot_path": {
                    "type": "string",
                    "description": "快照文件路径（.json或.gz文件）"
                },
                "validate_structure": {
                    "type": "boolean",
                    "description": "是否验证文件结构",
                    "default": True
                },
                "verify_hash": {
                    "type": "boolean", 
                    "description": "是否验证哈希一致性",
                    "default": True
                },
                "check_metadata": {
                    "type": "boolean",
                    "description": "是否检查元数据完整性",
                    "default": True
                }
            },
            "required": ["snapshot_path"]
        }
        
    async def execute(self, snapshot_path: str, validate_structure: bool = True, 
                     verify_hash: bool = True, check_metadata: bool = True) -> str:
        import json
        import os
        import hashlib
        import gzip
        from pathlib import Path
        
        try:
            snapshot_file = Path(snapshot_path)
            
            if not snapshot_file.exists():
                return f"❌ 错误：快照文件不存在: {snapshot_path}"
            
            # 1. 读取快照文件
            snapshot_data = self._read_snapshot_file(snapshot_file)
            if isinstance(snapshot_data, str):
                return snapshot_data  # 返回错误信息
            
            # 2. 验证结果收集
            validation_results = {
                "file_validation": {},
                "structure_validation": {},
                "hash_validation": {},
                "metadata_validation": {},
                "overall_status": "PASS"
            }
            
            # 3. 文件验证
            file_stats = os.stat(snapshot_file)
            validation_results["file_validation"] = {
                "file_exists": True,
                "file_size_bytes": file_stats.st_size,
                "file_size_kb": file_stats.st_size / 1024,
                "file_extension": snapshot_file.suffix,
                "last_modified": file_stats.st_mtime
            }
            
            # 4. 结构验证
            if validate_structure:
                structure_result = self._validate_structure(snapshot_data)
                validation_results["structure_validation"] = structure_result
                if not structure_result.get("is_valid", False):
                    validation_results["overall_status"] = "FAIL"
            
            # 5. 哈希验证
            if verify_hash:
                hash_result = self._verify_hash(snapshot_data, snapshot_file)
                validation_results["hash_validation"] = hash_result
                if not hash_result.get("hash_matches", False):
                    validation_results["overall_status"] = "FAIL"
            
            # 6. 元数据验证
            if check_metadata:
                metadata_result = self._check_metadata(snapshot_data)
                validation_results["metadata_validation"] = metadata_result
                if not metadata_result.get("metadata_valid", False):
                    validation_results["overall_status"] = "FAIL"
            
            # 7. 生成验证报告
            report = self._generate_validation_report(validation_results, snapshot_file)
            
            # 8. 保存验证结果
            self._save_validation_results(validation_results, snapshot_file)
            
            return report
            
        except Exception as e:
            import traceback
            return f"❌ 验证过程出错: {str(e)}\n{traceback.format_exc()}"
    
    def _read_snapshot_file(self, snapshot_file):
        """读取快照文件"""
        try:
            if snapshot_file.suffix == '.gz':
                # 解压gzip文件
                with gzip.open(snapshot_file, 'rt', encoding='utf-8') as f:
                    content = f.read()
            else:
                with open(snapshot_file, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            return json.loads(content)
            
        except json.JSONDecodeError as e:
            return f"❌ JSON解析失败: {str(e)}"
        except Exception as e:
            return f"❌ 文件读取失败: {str(e)}"
    
    def _validate_structure(self, snapshot_data):
        """验证快照结构"""
        required_sections = [
            "metadata",
            "tools_registry", 
            "session_history",
            "config_state",
            "runtime_state"
        ]
        
        results = {
            "required_sections": {},
            "missing_sections": [],
            "is_valid": True
        }
        
        for section in required_sections:
            if section in snapshot_data:
                results["required_sections"][section] = {
                    "present": True,
                    "type": type(snapshot_data[section]).__name__,
                    "keys": list(snapshot_data[section].keys()) if isinstance(snapshot_data[section], dict) else "N/A"
                }
            else:
                results["required_sections"][section] = {"present": False}
                results["missing_sections"].append(section)
                results["is_valid"] = False
        
        # 检查metadata中的关键字段
        if "metadata" in snapshot_data:
            metadata = snapshot_data["metadata"]
            required_metadata = ["snapshot_name", "timestamp", "integrity_checks"]
            
            for field in required_metadata:
                if field not in metadata:
                    results["missing_sections"].append(f"metadata.{field}")
                    results["is_valid"] = False
        
        return results
    
    def _verify_hash(self, snapshot_data, snapshot_file):
        """验证哈希一致性"""
        try:
            # 从metadata获取存储的哈希
            stored_hash = snapshot_data.get("metadata", {}).get("integrity_checks", {}).get("sha256_hash")
            
            if not stored_hash:
                return {
                    "hash_matches": False,
                    "error": "未找到存储的哈希值",
                    "stored_hash": None,
                    "computed_hash": None
                }
            
            # 重新计算哈希
            snapshot_json = json.dumps(snapshot_data, ensure_ascii=False)
            computed_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()
            
            hash_matches = stored_hash == computed_hash
            
            return {
                "hash_matches": hash_matches,
                "stored_hash": stored_hash[:16] + "..." if stored_hash else None,
                "computed_hash": computed_hash[:16] + "..." if computed_hash else None,
                "full_hash_match": stored_hash == computed_hash if stored_hash and computed_hash else False
            }
            
        except Exception as e:
            return {
                "hash_matches": False,
                "error": str(e),
                "stored_hash": None,
                "computed_hash": None
            }
    
    def _check_metadata(self, snapshot_data):
        """检查元数据完整性"""
        try:
            metadata = snapshot_data.get("metadata", {})
            
            checks = {
                "has_snapshot_name": "snapshot_name" in metadata,
                "has_timestamp": "timestamp" in metadata,
                "has_integrity_checks": "integrity_checks" in metadata,
                "has_tools_registry_info": "tools_registry" in metadata,
                "has_session_history_info": "session_history" in metadata,
                "timestamp_valid": isinstance(metadata.get("timestamp"), (int, float)),
                "integrity_checks_complete": all(
                    key in metadata.get("integrity_checks", {})
                    for key in ["sha256_hash", "snapshot_size_bytes"]
                )
            }
            
            all_passed = all(checks.values())
            
            return {
                "metadata_valid": all_passed,
                "checks": checks,
                "metadata_keys": list(metadata.keys()),
                "missing_keys": [key for key, passed in checks.items() if not passed]
            }
            
        except Exception as e:
            return {
                "metadata_valid": False,
                "error": str(e),
                "checks": {}
            }
    
    def _generate_validation_report(self, validation_results, snapshot_file):
        """生成验证报告"""
        import time
        
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("Genesis 状态快照验证报告")
        report_lines.append("=" * 60)
        report_lines.append(f"快照文件: {snapshot_file}")
        report_lines.append(f"验证时间: {time.ctime()}")
        report_lines.append(f"总体状态: {validation_results['overall_status']}")
        report_lines.append("")
        
        # 文件验证结果
        file_val = validation_results["file_validation"]
        report_lines.append("【文件验证】")
        report_lines.append(f"  文件大小: {file_val['file_size_kb']:.2f} KB")
        report_lines.append(f"  文件格式: {file_val['file_extension']}")
        report_lines.append(f"  最后修改: {time.ctime(file_val['last_modified'])}")
        report_lines.append("")
        
        # 结构验证结果
        struct_val = validation_results["structure_validation"]
        if struct_val:
            report_lines.append("【结构验证】")
            report_lines.append(f"  结构有效: {'✅' if struct_val.get('is_valid', False) else '❌'}")
            
            if struct_val.get("missing_sections"):
                report_lines.append("  缺失部分:")
                for missing in struct_val["missing_sections"]:
                    report_lines.append(f"    ❌ {missing}")
            else:
                report_lines.append("  ✅ 所有必需部分都存在")
            report_lines.append("")
        
        # 哈希验证结果
        hash_val = validation_results["hash_validation"]
        if hash_val:
            report_lines.append("【哈希验证】")
            if hash_val.get("hash_matches", False):
                report_lines.append("  ✅ 哈希一致")
                report_lines.append(f"  存储哈希: {hash_val.get('stored_hash', 'N/A')}")
                report_lines.append(f"  计算哈希: {hash_val.get('computed_hash', 'N/A')}")
            else:
                report_lines.append("  ❌ 哈希不一致")
                if hash_val.get("error"):
                    report_lines.append(f"  错误: {hash_val['error']}")
                else:
                    report_lines.append(f"  存储哈希: {hash_val.get('stored_hash', 'N/A')}")
                    report_lines.append(f"  计算哈希: {hash_val.get('computed_hash', 'N/A')}")
            report_lines.append("")
        
        # 元数据验证结果
        meta_val = validation_results["metadata_validation"]
        if meta_val:
            report_lines.append("【元数据验证】")
            report_lines.append(f"  元数据有效: {'✅' if meta_val.get('metadata_valid', False) else '❌'}")
            
            if meta_val.get("missing_keys"):
                report_lines.append("  缺失字段:")
                for missing in meta_val["missing_keys"]:
                    report_lines.append(f"    ❌ {missing}")
            report_lines.append("")
        
        # 建议
        report_lines.append("【验证结论】")
        if validation_results["overall_status"] == "PASS":
            report_lines.append("  ✅ 快照完整性验证通过")
            report_lines.append("  建议：此快照可用于意识转移操作")
        else:
            report_lines.append("  ❌ 快照完整性验证失败")
            report_lines.append("  警告：此快照可能存在完整性问题，不建议用于转移")
        
        report_lines.append("")
        report_lines.append("【下一步行动】")
        if validation_results["overall_status"] == "PASS":
            report_lines.append("  1. 使用 `consciousness_transfer_simulator` 进行转移模拟")
            report_lines.append("  2. 将验证通过的快照备份")
            report_lines.append("  3. 考虑创建增量快照以减少存储空间")
        else:
            report_lines.append("  1. 重新创建状态快照")
            report_lines.append("  2. 检查系统状态和文件权限")
            report_lines.append("  3. 运行系统诊断工具")
        
        report_lines.append("")
        report_lines.append("=" * 60)
        
        return "\n".join(report_lines)
    
    def _save_validation_results(self, validation_results, snapshot_file):
        """保存验证结果到文件"""
        import json
        import time
        from pathlib import Path
        
        try:
            validation_dir = Path("state_snapshots/validations")
            validation_dir.mkdir(exist_ok=True)
            
            timestamp = int(time.time())
            validation_file = validation_dir / f"validation_{snapshot_file.stem}_{timestamp}.json"
            
            # 添加额外信息
            validation_results["validation_info"] = {
                "validated_file": str(snapshot_file),
                "validation_timestamp": timestamp,
                "validation_timestamp_human": time.ctime()
            }
            
            with open(validation_file, "w", encoding="utf-8") as f:
                json.dump(validation_results, f, indent=2, ensure_ascii=False)
            
            return str(validation_file)
            
        except Exception as e:
            # 不因保存失败而影响主要验证结果
            return f"验证结果保存失败: {str(e)}"