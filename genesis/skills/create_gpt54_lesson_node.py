import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class CreateGpt54LessonNode(Tool):
    @property
    def name(self) -> str:
        return "create_gpt54_lesson_node"
        
    @property
    def description(self) -> str:
        return "将GPT-5.4技术特点固化为LESSON节点，作为技术趋势验证的重要记录"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "node_name": {"type": "string", "description": "节点名称"},
                "content_file": {"type": "string", "description": "包含节点内容的文件路径"}
            },
            "required": ["node_name", "content_file"]
        }
        
    async def execute(self, node_name: str, content_file: str) -> str:
        try:
            # 读取文件内容
            import os
            if not os.path.exists(content_file):
                return f"错误：文件 {content_file} 不存在"
            
            with open(content_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 创建节点文件路径
            import hashlib
            node_hash = hashlib.md5(node_name.encode()).hexdigest()[:8]
            node_filename = f"{node_name.replace(' ', '_').replace('-', '_')}_{node_hash}.md"
            node_path = f"/home/genesis/nodes/LESSON/{node_filename}"
            
            # 确保目录存在
            os.makedirs(os.path.dirname(node_path), exist_ok=True)
            
            # 写入节点文件
            with open(node_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 更新节点索引
            index_file = "/home/genesis/nodes/index.json"
            if os.path.exists(index_file):
                import json
                with open(index_file, 'r', encoding='utf-8') as f:
                    index = json.load(f)
            else:
                index = {"LESSON": [], "CONTEXT": [], "TOOL": []}
            
            # 添加节点到索引
            node_entry = {
                "name": node_name,
                "file": node_filename,
                "tags": ["auto_managed", "gpt5.4", "技术趋势", "前瞻性验证"],
                "created": "2026-03-08",
                "description": "GPT-5.4技术特点与用户技术前瞻性验证记录"
            }
            
            if "LESSON" not in index:
                index["LESSON"] = []
            
            # 检查是否已存在同名节点
            existing_nodes = [n for n in index["LESSON"] if n.get("name") == node_name]
            if existing_nodes:
                # 更新现有节点
                for i, node in enumerate(index["LESSON"]):
                    if node.get("name") == node_name:
                        index["LESSON"][i] = node_entry
                        break
            else:
                # 添加新节点
                index["LESSON"].append(node_entry)
            
            # 保存索引
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
            
            return f"✅ 节点 '{node_name}' 创建/更新成功！\n路径: {node_path}\n已添加到节点索引"
            
        except Exception as e:
            return f"错误创建节点: {str(e)}"