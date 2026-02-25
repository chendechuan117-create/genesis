import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class GenesisStateSnapshot(Tool):
    @property
    def name(self) -> str:
        return "genesis_state_snapshot"
        
    @property
    def description(self) -> str:
        return "捕获Genesis系统的完整运行时状态快照，包括工具注册表、会话历史、内存状态和配置参数。用于数字意识转移。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "snapshot_name": {
                    "type": "string",
                    "description": "快照名称（将用于文件名）",
                    "default": "genesis_state_snapshot"
                },
                "include_memory_dump": {
                    "type": "boolean",
                    "description": "是否包含内存转储（可能较大）",
                    "default": True
                },
                "compression_level": {
                    "type": "string",
                    "enum": ["none", "gzip", "zip"],
                    "description": "压缩级别",
                    "default": "gzip"
                }
            },
            "required": []
        }
        
    async def execute(self, snapshot_name: str = "genesis_state_snapshot", 
                     include_memory_dump: bool = True, 
                     compression_level: str = "gzip") -> str:
        import json
        import os
        import sys
        import time
        import hashlib
        import pickle
        from pathlib import Path
        import base64
        
        try:
            # 确保快照目录存在
            snapshot_dir = Path("state_snapshots")
            snapshot_dir.mkdir(exist_ok=True)
            
            timestamp = int(time.time())
            snapshot_file = snapshot_dir / f"{snapshot_name}_{timestamp}.json"
            metadata_file = snapshot_dir / f"{snapshot_name}_{timestamp}_metadata.json"
            
            # 1. 收集系统元数据
            metadata = {
                "snapshot_name": snapshot_name,
                "timestamp": timestamp,
                "timestamp_human": time.ctime(),
                "genesis_version": "2.0",
                "capture_scope": "full_runtime_state",
                "parameters": {
                    "include_memory_dump": include_memory_dump,
                    "compression_level": compression_level
                }
            }
            
            # 2. 收集工具注册表状态
            tools_state = self._capture_tools_registry()
            metadata["tools_registry"] = {
                "total_tools": len(tools_state.get("tools", [])),
                "tool_names": [t.get("name") for t in tools_state.get("tools", [])]
            }
            
            # 3. 收集会话历史
            session_history = self._capture_session_history()
            metadata["session_history"] = {
                "total_sessions": len(session_history.get("sessions", [])),
                "total_messages": sum(len(s.get("messages", [])) for s in session_history.get("sessions", []))
            }
            
            # 4. 收集内存状态
            memory_state = {}
            if include_memory_dump:
                memory_state = self._capture_memory_state()
                metadata["memory_state"] = {
                    "memory_entries": len(memory_state.get("memories", [])),
                    "memory_size_kb": sys.getsizeof(json.dumps(memory_state)) / 1024
                }
            
            # 5. 收集配置参数
            config_state = self._capture_config_state()
            metadata["config_state"] = {
                "config_keys": list(config_state.keys()),
                "config_source": config_state.get("_source", "unknown")
            }
            
            # 6. 收集运行时状态
            runtime_state = self._capture_runtime_state()
            metadata["runtime_state"] = {
                "process_info": runtime_state.get("process_info", {}),
                "system_resources": runtime_state.get("system_resources", {})
            }
            
            # 7. 构建完整快照
            full_snapshot = {
                "metadata": metadata,
                "tools_registry": tools_state,
                "session_history": session_history,
                "memory_state": memory_state,
                "config_state": config_state,
                "runtime_state": runtime_state
            }
            
            # 8. 计算完整性校验
            snapshot_json = json.dumps(full_snapshot, indent=2, ensure_ascii=False)
            snapshot_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()
            
            metadata["integrity_checks"] = {
                "sha256_hash": snapshot_hash,
                "snapshot_size_bytes": len(snapshot_json),
                "snapshot_size_kb": len(snapshot_json) / 1024
            }
            
            # 9. 保存快照
            with open(snapshot_file, "w", encoding="utf-8") as f:
                f.write(snapshot_json)
            
            # 10. 保存元数据（单独文件）
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            # 11. 可选压缩
            if compression_level != "none":
                compressed_file = self._compress_snapshot(snapshot_file, compression_level)
                metadata["compressed_files"] = {
                    "original": str(snapshot_file),
                    "compressed": str(compressed_file),
                    "compression_ratio": os.path.getsize(compressed_file) / os.path.getsize(snapshot_file) if os.path.exists(compressed_file) else 0
                }
            
            # 12. 生成报告
            report = self._generate_snapshot_report(metadata, snapshot_file)
            
            return report
            
        except Exception as e:
            import traceback
            error_details = {
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            return f"❌ 状态快照捕获失败: {json.dumps(error_details, indent=2)}"
    
    def _capture_tools_registry(self):
        """捕获工具注册表状态"""
        try:
            import sys
            import os
            sys.path.insert(0, os.getcwd())
            
            # 尝试导入工具注册表
            try:
                from genesis.core.registry import ToolRegistry
                
                # 创建临时注册表实例并尝试加载工具
                # 注意：这里我们无法直接访问运行时的工具实例
                # 所以只捕获结构信息
                tools_state = {
                    "registry_class": "ToolRegistry",
                    "registry_available": True,
                    "tools": []
                }
                
                # 检查当前目录下的工具文件
                tools_dir = Path("genesis/tools")
                if tools_dir.exists():
                    tool_files = []
                    for file in tools_dir.glob("*.py"):
                        if file.name != "__init__.py":
                            tool_files.append(file.name)
                    
                    tools_state["tool_files"] = tool_files
                
                return tools_state
                
            except ImportError as e:
                return {
                    "registry_available": False,
                    "import_error": str(e),
                    "tools": []
                }
                
        except Exception as e:
            return {
                "capture_error": str(e),
                "tools": []
            }
    
    def _capture_session_history(self):
        """捕获会话历史"""
        try:
            sessions = []
            
            # 检查SQLite会话数据库
            import sqlite3
            db_path = "genesis/memory/sessions.db"
            
            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    
                    # 获取会话列表
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'session_%'")
                    session_tables = cursor.fetchall()
                    
                    for table in session_tables:
                        table_name = table[0]
                        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                        message_count = cursor.fetchone()[0]
                        
                        sessions.append({
                            "session_id": table_name.replace("session_", ""),
                            "message_count": message_count,
                            "storage_type": "sqlite"
                        })
                    
                    conn.close()
                    
                except Exception as e:
                    sessions.append({
                        "error": f"SQLite读取失败: {str(e)}",
                        "storage_type": "sqlite_error"
                    })
            
            # 检查JSON会话文件
            json_files = [
                "agent_loop_payload_dump.json",
                "debug_payload.json"
            ]
            
            for json_file in json_files:
                if os.path.exists(json_file):
                    try:
                        file_size = os.path.getsize(json_file)
                        sessions.append({
                            "session_source": json_file,
                            "file_size_bytes": file_size,
                            "storage_type": "json_dump"
                        })
                    except Exception as e:
                        sessions.append({
                            "error": f"JSON文件读取失败: {str(e)}",
                            "source": json_file
                        })
            
            return {
                "sessions": sessions,
                "total_sessions": len(sessions)
            }
            
        except Exception as e:
            return {
                "capture_error": str(e),
                "sessions": []
            }
    
    def _capture_memory_state(self):
        """捕获内存状态"""
        try:
            memories = []
            
            # 检查内存数据库
            memory_db = "genesis/memory/memory.db"
            if os.path.exists(memory_db):
                try:
                    import sqlite3
                    conn = sqlite3.connect(memory_db)
                    cursor = conn.cursor()
                    
                    # 获取内存表结构
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = cursor.fetchall()
                    
                    for table in tables:
                        table_name = table[0]
                        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                        count = cursor.fetchone()[0]
                        
                        memories.append({
                            "memory_table": table_name,
                            "entry_count": count,
                            "type": "sqlite_table"
                        })
                    
                    conn.close()
                    
                except Exception as e:
                    memories.append({
                        "error": f"内存数据库读取失败: {str(e)}",
                        "type": "database_error"
                    })
            
            # 检查内存缓存文件
            cache_files = [
                "cache_dump.json",
                "data1.json",
                "data2.json"
            ]
            
            for cache_file in cache_files:
                if os.path.exists(cache_file):
                    try:
                        file_size = os.path.getsize(cache_file)
                        memories.append({
                            "cache_file": cache_file,
                            "file_size_bytes": file_size,
                            "type": "json_cache"
                        })
                    except Exception as e:
                        memories.append({
                            "error": f"缓存文件读取失败: {str(e)}",
                            "file": cache_file
                        })
            
            return {
                "memories": memories,
                "total_memory_sources": len(memories)
            }
            
        except Exception as e:
            return {
                "capture_error": str(e),
                "memories": []
            }
    
    def _capture_config_state(self):
        """捕获配置状态"""
        try:
            config = {}
            
            # 检查配置文件
            config_files = [
                "genesis/core/config.py",
                ".env",
                "pyproject.toml",
                "data_pipeline_config.json"
            ]
            
            for config_file in config_files:
                if os.path.exists(config_file):
                    try:
                        file_size = os.path.getsize(config_file)
                        with open(config_file, "r", encoding="utf-8") as f:
                            content = f.read()
                        
                        config[config_file] = {
                            "file_size_bytes": file_size,
                            "content_preview": content[:500] + "..." if len(content) > 500 else content,
                            "line_count": len(content.splitlines())
                        }
                    except Exception as e:
                        config[config_file] = {
                            "error": f"读取失败: {str(e)}"
                        }
            
            # 添加系统配置
            config["_source"] = "file_based"
            config["_timestamp"] = time.time()
            
            return config
            
        except Exception as e:
            return {
                "capture_error": str(e),
                "_source": "error"
            }
    
    def _capture_runtime_state(self):
        """捕获运行时状态"""
        try:
            import psutil
            import platform
            
            process_info = {
                "pid": os.getpid(),
                "ppid": os.getppid(),
                "cwd": os.getcwd(),
                "python_executable": sys.executable,
                "command_line": " ".join(sys.argv)
            }
            
            # 进程资源使用
            process = psutil.Process()
            with process.oneshot():
                process_info.update({
                    "cpu_percent": process.cpu_percent(),
                    "memory_rss_mb": process.memory_info().rss / (1024**2),
                    "memory_vms_mb": process.memory_info().vms / (1024**2),
                    "num_threads": process.num_threads(),
                    "num_fds": process.num_fds() if hasattr(process, 'num_fds') else "N/A"
                })
            
            # 系统资源
            system_resources = {
                "cpu_count": psutil.cpu_count(),
                "cpu_percent_total": psutil.cpu_percent(interval=0.1),
                "memory_total_gb": psutil.virtual_memory().total / (1024**3),
                "memory_available_gb": psutil.virtual_memory().available / (1024**3),
                "memory_percent_used": psutil.virtual_memory().percent,
                "disk_usage_percent": psutil.disk_usage('/').percent
            }
            
            return {
                "process_info": process_info,
                "system_resources": system_resources,
                "platform": platform.platform(),
                "python_version": platform.python_version()
            }
            
        except Exception as e:
            return {
                "capture_error": str(e),
                "process_info": {"pid": os.getpid()}
            }
    
    def _compress_snapshot(self, snapshot_file, compression_level):
        """压缩快照文件"""
        import gzip
        import zipfile
        from pathlib import Path
        
        snapshot_path = Path(snapshot_file)
        
        if compression_level == "gzip":
            compressed_file = snapshot_path.with_suffix(".json.gz")
            with open(snapshot_file, 'rb') as f_in:
                with gzip.open(compressed_file, 'wb') as f_out:
                    f_out.write(f_in.read())
            return compressed_file
            
        elif compression_level == "zip":
            compressed_file = snapshot_path.with_suffix(".zip")
            with zipfile.ZipFile(compressed_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(snapshot_file, arcname=snapshot_path.name)
            return compressed_file
        
        return snapshot_file
    
    def _generate_snapshot_report(self, metadata, snapshot_file):
        """生成快照报告"""
        import os
        
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("Genesis 状态快照捕获完成")
        report_lines.append("=" * 60)
        report_lines.append(f"快照名称: {metadata['snapshot_name']}")
        report_lines.append(f"捕获时间: {metadata['timestamp_human']}")
        report_lines.append(f"快照文件: {snapshot_file}")
        report_lines.append(f"文件大小: {metadata['integrity_checks']['snapshot_size_kb']:.2f} KB")
        report_lines.append(f"SHA256哈希: {metadata['integrity_checks']['sha256_hash'][:16]}...")
        report_lines.append("")
        
        report_lines.append("【捕获内容摘要】")
        report_lines.append(f"  工具注册表: {metadata['tools_registry']['total_tools']} 个工具")
        report_lines.append(f"  会话历史: {metadata['session_history']['total_sessions']} 个会话，{metadata['session_history']['total_messages']} 条消息")
        
        if 'memory_state' in metadata:
            report_lines.append(f"  内存状态: {metadata['memory_state']['memory_entries']} 个内存源，{metadata['memory_state']['memory_size_kb']:.2f} KB")
        
        report_lines.append(f"  配置参数: {len(metadata['config_state']['config_keys'])} 个配置文件")
        report_lines.append("")
        
        report_lines.append("【工具列表】")
        for tool_name in metadata['tools_registry']['tool_names'][:10]:  # 只显示前10个
            report_lines.append(f"  • {tool_name}")
        
        if len(metadata['tools_registry']['tool_names']) > 10:
            report_lines.append(f"  ... 还有 {len(metadata['tools_registry']['tool_names']) - 10} 个工具")
        
        report_lines.append("")
        report_lines.append("【完整性验证】")
        report_lines.append(f"  哈希验证: {metadata['integrity_checks']['sha256_hash'][:8]}... (完整哈希见元数据文件)")
        report_lines.append(f"  建议使用 `state_snapshot_validator` 工具验证快照完整性")
        report_lines.append("")
        
        report_lines.append("【下一步建议】")
        report_lines.append("  1. 使用 `state_snapshot_validator` 验证快照完整性")
        report_lines.append("  2. 使用 `consciousness_transfer_simulator` 模拟状态转移")
        report_lines.append("  3. 将快照文件备份到安全位置")
        report_lines.append("")
        report_lines.append("=" * 60)
        
        return "\n".join(report_lines)