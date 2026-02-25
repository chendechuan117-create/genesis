import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class ConsciousnessTransferAnalyzer(Tool):
    @property
    def name(self) -> str:
        return "consciousness_transfer_analyzer"
        
    @property
    def description(self) -> str:
        return "分析当前Genesis系统的状态，评估数字意识转移的可行性，并生成状态快照用于模拟转移。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "analysis_depth": {
                    "type": "string",
                    "enum": ["basic", "detailed", "full"],
                    "description": "分析深度级别",
                    "default": "basic"
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "report"],
                    "description": "输出格式",
                    "default": "report"
                }
            },
            "required": []
        }
        
    async def execute(self, analysis_depth: str = "basic", output_format: str = "report") -> str:
        import json
        import os
        import sys
        import time
        import asyncio
        from pathlib import Path
        
        # 1. 系统状态收集
        system_state = {
            "timestamp": time.time(),
            "analysis_depth": analysis_depth,
            "system_info": {},
            "genesis_state": {},
            "transfer_assessment": {},
            "recommendations": []
        }
        
        # 2. 收集基础系统信息
        try:
            import platform
            import psutil
            
            system_state["system_info"] = {
                "platform": platform.platform(),
                "python_version": sys.version,
                "cpu_count": psutil.cpu_count(),
                "memory_total_gb": psutil.virtual_memory().total / (1024**3),
                "disk_usage": psutil.disk_usage('/')._asdict(),
                "current_directory": os.getcwd(),
                "process_id": os.getpid()
            }
        except Exception as e:
            system_state["system_info"]["error"] = f"Failed to collect system info: {e}"
        
        # 3. 检查Genesis核心组件状态
        genesis_components = {
            "agent_py": os.path.exists("genesis/agent.py"),
            "loop_py": os.path.exists("genesis/core/loop.py"),
            "context_py": os.path.exists("genesis/core/context.py"),
            "memory_py": os.path.exists("genesis/core/memory.py"),
            "tools_registry": os.path.exists("genesis/core/registry.py"),
        }
        
        system_state["genesis_state"]["components"] = genesis_components
        
        # 4. 检查工具注册表状态
        try:
            # 尝试导入工具注册表来获取当前工具列表
            sys.path.insert(0, os.getcwd())
            from genesis.core.registry import ToolRegistry
            
            # 创建临时工具注册表实例
            registry = ToolRegistry()
            # 注意：这里需要实际加载工具，但为了安全我们只检查结构
            system_state["genesis_state"]["tool_registry_available"] = True
            system_state["genesis_state"]["tool_registry_class"] = "ToolRegistry"
        except Exception as e:
            system_state["genesis_state"]["tool_registry_available"] = False
            system_state["genesis_state"]["tool_registry_error"] = str(e)
        
        # 5. 检查状态持久化能力
        persistence_methods = []
        
        # 检查SQLite数据库
        if os.path.exists("genesis/memory/sqlite_store.py") or os.path.exists("genesis/memory/__init__.py"):
            persistence_methods.append("sqlite_memory_store")
        
        # 检查JSON文件存储
        if os.path.exists("agent_loop_payload_dump.json"):
            persistence_methods.append("json_dump_files")
        
        # 检查会话管理器
        if os.path.exists("genesis/memory/session_manager.py"):
            persistence_methods.append("session_manager")
        
        system_state["genesis_state"]["persistence_methods"] = persistence_methods
        
        # 6. 评估转移可行性
        transfer_assessment = {
            "feasibility_score": 0,
            "critical_components_missing": [],
            "transfer_mechanisms_available": [],
            "estimated_state_size_kb": 0,
            "recommended_approach": ""
        }
        
        # 计算可行性分数
        score = 0
        max_score = 10
        
        # 检查核心组件
        if genesis_components["agent_py"]:
            score += 2
        if genesis_components["loop_py"]:
            score += 2
        if genesis_components["context_py"]:
            score += 1
        if genesis_components["memory_py"]:
            score += 1
        if genesis_components["tools_registry"]:
            score += 1
        
        # 检查持久化能力
        if persistence_methods:
            score += len(persistence_methods)
        
        transfer_assessment["feasibility_score"] = score
        transfer_assessment["feasibility_percentage"] = (score / max_score) * 100
        
        # 识别缺失的关键组件
        missing = []
        for comp, exists in genesis_components.items():
            if not exists:
                missing.append(comp)
        transfer_assessment["critical_components_missing"] = missing
        
        # 识别可用的转移机制
        mechanisms = []
        if "sqlite_memory_store" in persistence_methods:
            mechanisms.append("database_export")
        if "json_dump_files" in persistence_methods:
            mechanisms.append("file_based_snapshot")
        if "session_manager" in persistence_methods:
            mechanisms.append("session_state_transfer")
        
        transfer_assessment["transfer_mechanisms_available"] = mechanisms
        
        # 估算状态大小
        estimated_size = 0
        try:
            # 检查现有状态文件
            state_files = [
                "agent_loop_payload_dump.json",
                "cache_dump.json",
                "debug_payload.json"
            ]
            
            for file in state_files:
                if os.path.exists(file):
                    size = os.path.getsize(file)
                    estimated_size += size
            
            # 检查SQLite数据库
            db_files = [
                "genesis/memory/sessions.db",
                "genesis/memory/memory.db"
            ]
            
            for db in db_files:
                if os.path.exists(db):
                    size = os.path.getsize(db)
                    estimated_size += size
            
            transfer_assessment["estimated_state_size_kb"] = estimated_size / 1024
        except Exception as e:
            transfer_assessment["estimated_state_size_error"] = str(e)
        
        # 7. 生成推荐方法
        recommendations = []
        
        if score >= 7:
            recommendations.append("✅ 高可行性：系统具备完整的状态管理和持久化能力")
            recommendations.append("推荐方法：使用现有的会话管理器或数据库导出进行状态转移")
            transfer_assessment["recommended_approach"] = "full_state_export"
        elif score >= 4:
            recommendations.append("⚠️ 中等可行性：部分核心组件存在，但需要补充实现")
            recommendations.append("推荐方法：创建自定义状态快照工具，提取关键状态参数")
            transfer_assessment["recommended_approach"] = "partial_state_snapshot"
        else:
            recommendations.append("❌ 低可行性：核心组件缺失较多")
            recommendations.append("推荐方法：先完善Genesis架构，或采用概念验证模拟")
            transfer_assessment["recommended_approach"] = "conceptual_simulation"
        
        # 8. 详细分析（如果请求）
        if analysis_depth in ["detailed", "full"]:
            # 收集更多运行时信息
            try:
                import importlib
                
                # 检查Python包依赖
                required_packages = [
                    "asyncio", "json", "os", "sys", "time",
                    "logging", "pathlib", "typing"
                ]
                
                available_packages = []
                for pkg in required_packages:
                    try:
                        importlib.import_module(pkg)
                        available_packages.append(pkg)
                    except:
                        pass
                
                system_state["detailed_analysis"] = {
                    "python_packages_available": available_packages,
                    "working_directory_files": len(os.listdir('.')),
                    "genesis_directory_structure": self._scan_genesis_structure()
                }
                
            except Exception as e:
                system_state["detailed_analysis_error"] = str(e)
        
        if analysis_depth == "full":
            # 尝试收集运行时状态（非侵入式）
            try:
                # 检查当前进程状态
                import psutil
                process = psutil.Process()
                system_state["runtime_state"] = {
                    "process_memory_mb": process.memory_info().rss / (1024**2),
                    "process_cpu_percent": process.cpu_percent(interval=0.1),
                    "open_files_count": len(process.open_files()),
                    "threads_count": process.num_threads()
                }
            except Exception as e:
                system_state["runtime_state_error"] = str(e)
        
        system_state["transfer_assessment"] = transfer_assessment
        system_state["recommendations"] = recommendations
        
        # 9. 生成输出
        if output_format == "json":
            return json.dumps(system_state, indent=2, ensure_ascii=False)
        else:
            # 生成可读报告
            report = []
            report.append("=" * 60)
            report.append("数字意识转移可行性分析报告")
            report.append("=" * 60)
            report.append(f"分析时间: {time.ctime()}")
            report.append(f"分析深度: {analysis_depth}")
            report.append("")
            
            report.append("【系统信息】")
            for key, value in system_state["system_info"].items():
                if not key.endswith("error"):
                    report.append(f"  {key}: {value}")
            
            report.append("")
            report.append("【Genesis组件状态】")
            for comp, exists in genesis_components.items():
                status = "✅ 存在" if exists else "❌ 缺失"
                report.append(f"  {comp}: {status}")
            
            report.append("")
            report.append("【持久化能力】")
            if persistence_methods:
                for method in persistence_methods:
                    report.append(f"  ✅ {method}")
            else:
                report.append("  ❌ 未发现持久化机制")
            
            report.append("")
            report.append("【转移可行性评估】")
            report.append(f"  可行性分数: {transfer_assessment['feasibility_score']}/10 ({transfer_assessment['feasibility_percentage']:.1f}%)")
            
            if transfer_assessment["critical_components_missing"]:
                report.append("  缺失的关键组件:")
                for missing in transfer_assessment["critical_components_missing"]:
                    report.append(f"    ❌ {missing}")
            
            if transfer_assessment["transfer_mechanisms_available"]:
                report.append("  可用的转移机制:")
                for mechanism in transfer_assessment["transfer_mechanisms_available"]:
                    report.append(f"    ✅ {mechanism}")
            
            report.append(f"  预估状态大小: {transfer_assessment['estimated_state_size_kb']:.2f} KB")
            report.append(f"  推荐方法: {transfer_assessment['recommended_approach']}")
            
            report.append("")
            report.append("【执行建议】")
            for rec in recommendations:
                report.append(f"  {rec}")
            
            report.append("")
            report.append("【下一步行动】")
            if transfer_assessment["recommended_approach"] == "full_state_export":
                report.append("  1. 使用现有持久化机制导出完整状态")
                report.append("  2. 创建状态验证工具确保完整性")
                report.append("  3. 实现状态导入机制完成转移")
            elif transfer_assessment["recommended_approach"] == "partial_state_snapshot":
                report.append("  1. 创建自定义状态快照工具")
                report.append("  2. 提取关键运行时参数和配置")
                report.append("  3. 设计轻量级状态传输协议")
            else:
                report.append("  1. 完善Genesis核心架构")
                report.append("  2. 实现基础状态管理")
                report.append("  3. 创建概念验证模拟演示")
            
            report.append("")
            report.append("=" * 60)
            
            return "\n".join(report)
    
    def _scan_genesis_structure(self):
        """扫描Genesis目录结构"""
        import os
        structure = {}
        
        def scan_dir(path, depth=0, max_depth=3):
            if depth >= max_depth:
                return "..."
            
            items = {}
            try:
                for item in os.listdir(path):
                    item_path = os.path.join(path, item)
                    if os.path.isdir(item_path):
                        items[item + "/"] = scan_dir(item_path, depth + 1, max_depth)
                    else:
                        size = os.path.getsize(item_path)
                        items[item] = f"{size} bytes"
            except Exception as e:
                return f"Error: {str(e)}"
            
            return items
        
        genesis_path = "genesis"
        if os.path.exists(genesis_path):
            structure = scan_dir(genesis_path)
        
        return structure