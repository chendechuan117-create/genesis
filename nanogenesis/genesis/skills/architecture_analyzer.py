import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class ArchitectureAnalyzer(Tool):
    @property
    def name(self) -> str:
        return "architecture_analyzer"
        
    @property
    def description(self) -> str:
        return "分析Python代码库的架构问题，包括循环依赖、设计模式反模式、资源泄漏风险等。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "code_path": {"type": "string", "description": "代码库路径"}
            },
            "required": ["code_path"]
        }
        
    async def execute(self, code_path: str) -> str:
        import os
        import ast
        import networkx as nx
        from collections import defaultdict, Counter
        import re
        
        analysis_results = []
        
        # 1. 分析导入依赖关系
        def analyze_imports(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        imports.append(f"{module}.{alias.name}" if module else alias.name)
            
            return imports
        
        # 2. 检测循环依赖
        def detect_circular_dependencies(code_path):
            G = nx.DiGraph()
            module_imports = {}
            
            for root, dirs, files in os.walk(code_path):
                for file in files:
                    if file.endswith('.py'):
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, code_path)
                        module_name = rel_path.replace('/', '.').replace('.py', '')
                        
                        imports = analyze_imports(full_path)
                        module_imports[module_name] = imports
                        
                        # 添加节点
                        G.add_node(module_name)
                        
                        # 添加边（从当前模块到导入的模块）
                        for imp in imports:
                            # 简化处理：只考虑本地模块
                            if any(local_mod in imp for local_mod in ['genesis', 'agent', 'loop', 'core']):
                                G.add_edge(module_name, imp.split('.')[0])
            
            # 检测循环
            try:
                cycles = list(nx.simple_cycles(G))
                return cycles
            except:
                return []
        
        # 3. 检测潜在的性能反模式
        def detect_performance_antipatterns(filepath):
            patterns = {
                'nested_loops': r'for\s+\w+\s+in\s+.+:\s*\n\s*for\s+\w+\s+in\s+.+:',
                'deep_recursion': r'def\s+\w+\(.*\):\s*\n(.*\n)*?\s*return\s+\w+\(.*\)',
                'inefficient_string_concat': r'\+\s*".*"\s*\+\s*".*"',
                'global_variable_access': r'global\s+\w+',
            }
            
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            issues = []
            for pattern_name, pattern in patterns.items():
                matches = re.findall(pattern, content, re.MULTILINE)
                if matches:
                    issues.append(f"{pattern_name}: {len(matches)}处")
            
            return issues
        
        # 4. 分析资源管理
        def analyze_resource_management(filepath):
            resource_keywords = [
                'open(', 'close()', '__enter__', '__exit__', 'with ',
                'connect()', 'cursor()', 'execute(', 'commit()', 'rollback()'
            ]
            
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            resource_usage = {}
            for keyword in resource_keywords:
                count = content.count(keyword)
                if count > 0:
                    resource_usage[keyword] = count
            
            return resource_usage
        
        # 执行分析
        analysis_results.append("=== 架构分析报告 ===\\n")
        
        # 循环依赖检测
        cycles = detect_circular_dependencies(code_path)
        if cycles:
            analysis_results.append(f"⚠️ 发现循环依赖 ({len(cycles)}个):")
            for i, cycle in enumerate(cycles[:5], 1):  # 只显示前5个
                analysis_results.append(f"  循环{i}: {' -> '.join(cycle)}")
        else:
            analysis_results.append("✅ 未检测到循环依赖")
        
        # 分析关键文件
        key_files = ['agent.py', 'loop.py', 'core/base.py', 'core/tools.py']
        for rel_file in key_files:
            filepath = os.path.join(code_path, rel_file)
            if os.path.exists(filepath):
                analysis_results.append(f"\\n📄 分析文件: {rel_file}")
                
                # 性能反模式
                perf_issues = detect_performance_antipatterns(filepath)
                if perf_issues:
                    analysis_results.append(f"  性能警告: {', '.join(perf_issues)}")
                
                # 资源管理
                resources = analyze_resource_management(filepath)
                if resources:
                    analysis_results.append(f"  资源使用: {dict(resources)}")
        
        # 5. 模块耦合度分析
        module_stats = defaultdict(int)
        for root, dirs, files in os.walk(code_path):
            for file in files:
                if file.endswith('.py'):
                    full_path = os.path.join(root, file)
                    imports = analyze_imports(full_path)
                    module_stats['total_imports'] += len(imports)
                    module_stats['files_analyzed'] += 1
        
        if module_stats['files_analyzed'] > 0:
            avg_imports = module_stats['total_imports'] / module_stats['files_analyzed']
            analysis_results.append(f"\\n📊 模块统计:")
            analysis_results.append(f"  分析文件数: {module_stats['files_analyzed']}")
            analysis_results.append(f"  总导入数: {module_stats['total_imports']}")
            analysis_results.append(f"  平均导入/文件: {avg_imports:.1f}")
            
            if avg_imports > 10:
                analysis_results.append("  ⚠️ 高耦合度警告: 平均导入数过高")
        
        return "\\n".join(analysis_results)