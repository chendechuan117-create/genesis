import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class FileAnalyzer(Tool):
    @property
    def name(self) -> str:
        return "file_analyzer"
        
    @property
    def description(self) -> str:
        return "分析文件系统，统计文件类型、大小、修改时间等信息"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string", 
                    "description": "要分析的目录路径",
                    "default": "."
                },
                "max_depth": {
                    "type": "integer",
                    "description": "最大递归深度",
                    "default": 3
                },
                "file_types": {
                    "type": "array",
                    "description": "要统计的文件扩展名列表，如 ['.py', '.md', '.txt']",
                    "items": {"type": "string"},
                    "default": []
                }
            },
            "required": []
        }
        
    async def execute(self, directory: str = ".", max_depth: int = 3, file_types: list = []) -> str:
        import os
        import time
        from pathlib import Path
        from collections import defaultdict
        
        def get_file_info(path, current_depth=0):
            if current_depth > max_depth:
                return None
                
            try:
                stat = os.stat(path)
                return {
                    'path': path,
                    'size': stat.st_size,
                    'modified': stat.st_mtime,
                    'is_dir': os.path.isdir(path),
                    'extension': Path(path).suffix.lower() if not os.path.isdir(path) else ''
                }
            except:
                return None
        
        def analyze_directory(dir_path, depth=0):
            results = {
                'total_files': 0,
                'total_dirs': 0,
                'total_size': 0,
                'by_extension': defaultdict(int),
                'by_size_category': defaultdict(int),
                'recent_files': [],
                'largest_files': []
            }
            
            try:
                for root, dirs, files in os.walk(dir_path):
                    current_depth = root.count(os.sep) - dir_path.count(os.sep)
                    if current_depth > max_depth:
                        continue
                    
                    # 统计目录
                    results['total_dirs'] += len(dirs)
                    
                    # 统计文件
                    for file in files:
                        file_path = os.path.join(root, file)
                        file_info = get_file_info(file_path, current_depth)
                        
                        if file_info:
                            results['total_files'] += 1
                            results['total_size'] += file_info['size']
                            
                            # 按扩展名统计
                            ext = file_info['extension']
                            if ext:
                                results['by_extension'][ext] += 1
                            
                            # 按大小分类统计
                            size_mb = file_info['size'] / (1024 * 1024)
                            if size_mb < 0.1:
                                results['by_size_category']['< 0.1 MB'] += 1
                            elif size_mb < 1:
                                results['by_size_category']['0.1-1 MB'] += 1
                            elif size_mb < 10:
                                results['by_size_category']['1-10 MB'] += 1
                            elif size_mb < 100:
                                results['by_size_category']['10-100 MB'] += 1
                            else:
                                results['by_size_category']['> 100 MB'] += 1
                            
                            # 记录最近修改的文件
                            results['recent_files'].append((file_info['modified'], file_path, file_info['size']))
                            
                            # 记录最大的文件
                            results['largest_files'].append((file_info['size'], file_path))
                            
            except Exception as e:
                return f"分析目录时出错: {str(e)}"
            
            # 排序
            results['recent_files'].sort(reverse=True)
            results['largest_files'].sort(reverse=True)
            
            return results
        
        # 开始分析
        dir_path = os.path.abspath(directory)
        if not os.path.exists(dir_path):
            return f"目录不存在: {dir_path}"
        
        analysis = analyze_directory(dir_path)
        
        if isinstance(analysis, str):
            return analysis
        
        # 生成报告
        report = []
        report.append(f"目录分析报告: {dir_path}")
        report.append("=" * 50)
        report.append(f"总文件数: {analysis['total_files']}")
        report.append(f"总目录数: {analysis['total_dirs']}")
        report.append(f"总大小: {analysis['total_size'] / (1024**3):.2f} GB")
        report.append("")
        
        # 按扩展名统计
        if analysis['by_extension']:
            report.append("按文件类型统计:")
            for ext, count in sorted(analysis['by_extension'].items(), key=lambda x: x[1], reverse=True)[:10]:
                report.append(f"  {ext}: {count} 个文件")
        
        # 按大小分类
        report.append("")
        report.append("按文件大小分类:")
        for category, count in sorted(analysis['by_size_category'].items()):
            report.append(f"  {category}: {count} 个文件")
        
        # 最近修改的文件
        report.append("")
        report.append("最近修改的5个文件:")
        for mtime, path, size in analysis['recent_files'][:5]:
            mod_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
            size_mb = size / (1024 * 1024)
            report.append(f"  {mod_time} - {path} ({size_mb:.2f} MB)")
        
        # 最大的文件
        report.append("")
        report.append("最大的5个文件:")
        for size, path in analysis['largest_files'][:5]:
            size_mb = size / (1024 * 1024)
            report.append(f"  {size_mb:.2f} MB - {path}")
        
        return "\n".join(report)