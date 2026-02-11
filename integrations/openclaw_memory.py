"""
OpenClaw 记忆集成

读取 OpenClaw 的记忆文件，转换为 Genesis 可用的上下文
"""

from typing import Dict, List, Optional
from pathlib import Path
import json
import logging


logger = logging.getLogger(__name__)


class OpenClawMemoryLoader:
    """OpenClaw 记忆加载器"""
    
    def __init__(self, openclaw_memory_path: str):
        """
        初始化
        
        Args:
            openclaw_memory_path: OpenClaw 记忆文件路径
                例如: ~/.openclaw/memory 或 /path/to/openclaw/data
        """
        self.memory_path = Path(openclaw_memory_path)
        
        if not self.memory_path.exists():
            raise FileNotFoundError(f"OpenClaw 记忆路径不存在: {openclaw_memory_path}")
    
    def load_all_memories(self) -> Dict[str, str]:
        """
        加载所有记忆文件
        
        Returns:
            {文件名: 内容} 的字典
        """
        memories = {}
        
        # 检查是否有 SQLite 数据库
        sqlite_file = self.memory_path / "main.sqlite"
        if sqlite_file.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(str(sqlite_file))
                cursor = conn.cursor()
                
                # 尝试读取常见的表结构
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                
                for (table_name,) in tables:
                    try:
                        cursor.execute(f"SELECT * FROM {table_name} LIMIT 100")
                        rows = cursor.fetchall()
                        if rows:
                            # 将表内容转换为文本
                            content = f"Table: {table_name}\n"
                            for row in rows:
                                content += str(row) + "\n"
                            memories[f"sqlite_{table_name}"] = content
                    except Exception as e:
                        logger.debug(f"读取表 {table_name} 失败: {e}")
                
                conn.close()
            except Exception as e:
                logger.debug(f"读取 SQLite 失败: {e}")
        
        # 支持的文件类型
        extensions = ['.md', '.txt', '.json']
        
        for ext in extensions:
            for file in self.memory_path.rglob(f'*{ext}'):
                try:
                    # 使用相对路径作为 key
                    relative_path = file.relative_to(self.memory_path)
                    key = str(relative_path)
                    
                    # 读取内容
                    with open(file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    memories[key] = content
                
                except Exception as e:
                    logger.debug(f"读取文件失败 {file}: {e}")
        
        return memories
    
    def load_by_category(self, category: str) -> Dict[str, str]:
        """
        按分类加载记忆
        
        Args:
            category: 分类名称（如 docker, python, git）
        
        Returns:
            该分类的记忆
        """
        all_memories = self.load_all_memories()
        
        # 筛选包含该分类的文件
        filtered = {}
        category_lower = category.lower()
        
        for key, content in all_memories.items():
            if category_lower in key.lower() or category_lower in content.lower():
                filtered[key] = content
        
        return filtered
    
    def search_memories(self, query: str, limit: int = 10) -> Dict[str, str]:
        """
        搜索记忆
        
        Args:
            query: 搜索关键词
            limit: 返回数量限制
        
        Returns:
            匹配的记忆
        """
        all_memories = self.load_all_memories()
        
        # 计算相关性分数
        scored = []
        query_lower = query.lower()
        
        for key, content in all_memories.items():
            score = 0
            content_lower = content.lower()
            
            # 标题匹配（文件名）
            if query_lower in key.lower():
                score += 10
            
            # 内容匹配
            score += content_lower.count(query_lower)
            
            if score > 0:
                scored.append((key, content, score))
        
        # 排序并返回
        scored.sort(key=lambda x: x[2], reverse=True)
        
        result = {}
        for key, content, score in scored[:limit]:
            result[key] = content
        
        return result
    
    def get_summary(self) -> Dict:
        """获取记忆库摘要"""
        all_memories = self.load_all_memories()
        
        # 统计信息
        total_files = len(all_memories)
        total_size = sum(len(content) for content in all_memories.values())
        
        # 按扩展名分类
        by_ext = {}
        for key in all_memories.keys():
            ext = Path(key).suffix or 'no_ext'
            by_ext[ext] = by_ext.get(ext, 0) + 1
        
        return {
            'total_files': total_files,
            'total_size': total_size,
            'by_extension': by_ext,
            'memory_path': str(self.memory_path)
        }


def convert_openclaw_to_genesis_context(
    openclaw_memories: Dict[str, str],
    max_files: int = 10
) -> Dict[str, str]:
    """
    将 OpenClaw 记忆转换为 Genesis 上下文格式
    
    Args:
        openclaw_memories: OpenClaw 记忆字典
        max_files: 最多转换的文件数
    
    Returns:
        Genesis 格式的上下文
    """
    genesis_context = {}
    
    for i, (key, content) in enumerate(openclaw_memories.items()):
        if i >= max_files:
            break
        
        # 生成摘要（前200字符）
        summary = content[:200] + "..." if len(content) > 200 else content
        
        # 转换为 Genesis 格式
        genesis_key = f"openclaw_{Path(key).stem}"
        genesis_context[genesis_key] = f"[来自 OpenClaw: {key}]\n{content}"
    
    return genesis_context


# 示例用法
if __name__ == '__main__':
    import sys
    
    # 测试路径（需要根据实际情况修改）
    test_paths = [
        "~/.openclaw/memory",
        "~/openclaw/data",
        # "/home/user/.openclaw/memory",
    ]
    
    loader = None
    for path in test_paths:
        expanded_path = Path(path).expanduser()
        if expanded_path.exists():
            print(f"找到 OpenClaw 记忆路径: {expanded_path}")
            loader = OpenClawMemoryLoader(str(expanded_path))
            break
    
    if not loader:
        print("未找到 OpenClaw 记忆路径")
        print("请手动指定路径:")
        print("  python3 openclaw_memory.py /path/to/openclaw/memory")
        
        if len(sys.argv) > 1:
            loader = OpenClawMemoryLoader(sys.argv[1])
        else:
            sys.exit(1)
    
    # 获取摘要
    print("\n" + "="*60)
    print("OpenClaw 记忆库摘要")
    print("="*60)
    summary = loader.get_summary()
    print(f"总文件数: {summary['total_files']}")
    print(f"总大小: {summary['total_size']} 字符")
    print(f"文件类型: {summary['by_extension']}")
    
    # 搜索测试
    print("\n" + "="*60)
    print("搜索测试: 'docker'")
    print("="*60)
    results = loader.search_memories("docker", limit=5)
    print(f"找到 {len(results)} 个相关记忆:")
    for key in results.keys():
        print(f"  - {key}")
    
    # 转换为 Genesis 格式
    print("\n" + "="*60)
    print("转换为 Genesis 格式")
    print("="*60)
    genesis_context = convert_openclaw_to_genesis_context(results, max_files=3)
    print(f"转换了 {len(genesis_context)} 个上下文:")
    for key in genesis_context.keys():
        print(f"  - {key}")
