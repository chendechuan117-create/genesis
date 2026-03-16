import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class OpenclawSkillImporter(Tool):
    @property
    def name(self) -> str:
        return "openclaw_skill_importer"
        
    @property
    def description(self) -> str:
        return "从OpenClaw技能市场导入优质技能，逆向转换为Genesis认知节点，实现知识回流和生态集成"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "skill_url": {
                    "type": "string", 
                    "description": "OpenClaw技能URL或GitHub仓库链接"
                },
                "skill_file": {
                    "type": "string",
                    "description": "本地技能文件路径"
                },
                "skill_directory": {
                    "type": "string",
                    "description": "技能目录路径，批量转换"
                },
                "output_format": {
                    "type": "string",
                    "description": "输出格式：genesis_node, workshop_table, analysis_report",
                    "default": "genesis_node"
                },
                "quality_filter": {
                    "type": "boolean",
                    "description": "是否进行质量过滤，只导入高质量技能",
                    "default": True
                }
            },
            "anyOf": [
                {"required": ["skill_url"]},
                {"required": ["skill_file"]},
                {"required": ["skill_directory"]}
            ]
        }
        
    async def execute(self, skill_url: str = None, skill_file: str = None, 
                     skill_directory: str = None, output_format: str = "genesis_node",
                     quality_filter: bool = True) -> str:
        
        import re
        import os
        import json
        from pathlib import Path
        import tempfile
        
        results = []
        
        def analyze_skill_quality(content: str) -> dict:
            """分析技能质量"""
            quality_score = 0
            quality_indicators = []
            
            # 1. 完整性检查
            if "## 技能描述" in content:
                quality_score += 20
                quality_indicators.append("✅ 有技能描述")
            
            if "## 使用指令" in content:
                quality_score += 20
                quality_indicators.append("✅ 有使用指令")
            
            if "## 示例场景" in content:
                quality_score += 20
                quality_indicators.append("✅ 有示例场景")
            
            # 2. 技术深度检查
            technical_keywords = ["API", "配置", "参数", "集成", "工作流", "自动化"]
            tech_count = sum(1 for keyword in technical_keywords if keyword in content)
            if tech_count >= 3:
                quality_score += 20
                quality_indicators.append(f"✅ 技术深度足够 ({tech_count}个技术关键词)")
            
            # 3. 结构化检查
            if "| 参数名 | 类型 | 描述 |" in content:
                quality_score += 20
                quality_indicators.append("✅ 有结构化参数表")
            
            # 4. 可解释性检查
            if "白盒架构" in content or "可解释" in content or "决策透明" in content:
                quality_score += 10
                quality_indicators.append("✅ 包含可解释性元素")
            
            # 5. 实用性检查
            if "实际案例" in content or "已验证" in content or "生产环境" in content:
                quality_score += 10
                quality_indicators.append("✅ 有实际应用验证")
            
            return {
                "score": quality_score,
                "indicators": quality_indicators,
                "level": "高" if quality_score >= 70 else "中" if quality_score >= 50 else "低"
            }
        
        def convert_to_genesis_node(content: str, filename: str) -> str:
            """将技能内容转换为Genesis节点"""
            
            # 提取基本信息
            title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else filename.replace('.md', '')
            
            # 提取技能类型
            type_match = re.search(r'## 技能类型\s*\n(.+)', content)
            skill_type = type_match.group(1).strip() if type_match else "LESSON"
            
            # 提取原始节点信息
            node_name = ""
            tags = []
            
            node_info_match = re.search(r'## 原始节点信息\s*\n- \*\*节点名称\*\*: (.+?)\s*\n- \*\*节点标签\*\*: (.+?)\s*\n', content, re.DOTALL)
            if node_info_match:
                node_name = node_info_match.group(1).strip()
                tags_str = node_info_match.group(2).strip()
                tags = [tag.strip() for tag in tags_str.split(',')]
            else:
                # 从文件名推断
                node_name = filename.replace('.md', '').replace('-', '_').upper()
                tags = ["openclaw_imported", "skill_conversion"]
            
            # 提取技能描述
            desc_match = re.search(r'## 技能描述\s*\n(.+?)(?=\n##|\n---|\Z)', content, re.DOTALL)
            desc_content = desc_match.group(1).strip() if desc_match else content[:500] + "..."
            
            # 确定节点类型前缀
            if skill_type == "TOOL":
                prefix = "TOOL"
            elif skill_type == "CONTEXT":
                prefix = "CONTEXT"
            elif skill_type == "LESSON":
                prefix = "LESSON"
            else:
                # 根据内容推断
                if "工具" in desc_content or "API" in desc_content or "函数" in desc_content:
                    prefix = "TOOL"
                elif "用户" in desc_content or "配置" in desc_content or "环境" in desc_content:
                    prefix = "CONTEXT"
                else:
                    prefix = "LESSON"
            
            # 生成节点标识符
            if not node_name.startswith(prefix):
                node_identifier = f"[{prefix}_{node_name}]"
            else:
                node_identifier = f"[{node_name}]"
            
            # 生成标签字符串
            tags_str = ", ".join(tags)
            
            # 构建完整节点
            genesis_node = f"<{prefix}> {node_identifier} {title} | tags:{tags_str}\n\n{desc_content}"
            
            return genesis_node
        
        # 处理批量目录
        if skill_directory:
            if not os.path.exists(skill_directory):
                return f"错误：目录不存在 - {skill_directory}"
            
            skill_files = []
            for file in os.listdir(skill_directory):
                if file.endswith('.md') and not file.startswith('install-'):
                    skill_files.append(os.path.join(skill_directory, file))
            
            if not skill_files:
                return f"在目录 {skill_directory} 中未找到技能文件"
            
            for skill_path in skill_files:
                try:
                    with open(skill_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 质量过滤
                    quality = analyze_skill_quality(content)
                    
                    if quality_filter and quality["level"] == "低":
                        results.append(f"跳过低质量技能: {os.path.basename(skill_path)} (得分: {quality['score']})")
                        continue
                    
                    # 转换
                    genesis_node = convert_to_genesis_node(content, os.path.basename(skill_path))
                    
                    results.append({
                        "file": os.path.basename(skill_path),
                        "quality": quality,
                        "node": genesis_node
                    })
                    
                except Exception as e:
                    results.append(f"处理文件 {skill_path} 失败: {str(e)}")
        
        # 处理单个文件
        elif skill_file:
            if not os.path.exists(skill_file):
                return f"错误：文件不存在 - {skill_file}"
            
            try:
                with open(skill_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                quality = analyze_skill_quality(content)
                genesis_node = convert_to_genesis_node(content, os.path.basename(skill_file))
                
                results.append({
                    "file": os.path.basename(skill_file),
                    "quality": quality,
                    "node": genesis_node
                })
                
            except Exception as e:
                return f"处理文件失败: {str(e)}"
        
        # 格式化输出
        if output_format == "analysis_report":
            report = "## OpenClaw技能导入分析报告\n\n"
            
            if isinstance(results[0], dict):
                total = len(results)
                high_quality = sum(1 for r in results if r["quality"]["level"] == "高")
                medium_quality = sum(1 for r in results if r["quality"]["level"] == "中")
                
                report += f"### 统计概览\n"
                report += f"- 总技能数: {total}\n"
                report += f"- 高质量技能: {high_quality}\n"
                report += f"- 中等质量技能: {medium_quality}\n"
                report += f"- 低质量技能: {total - high_quality - medium_quality}\n\n"
                
                report += "### 详细分析\n"
                for result in results:
                    report += f"#### {result['file']}\n"
                    report += f"- 质量得分: {result['quality']['score']}/100\n"
                    report += f"- 质量等级: {result['quality']['level']}\n"
                    report += f"- 质量指标:\n"
                    for indicator in result['quality']['indicators']:
                        report += f"  {indicator}\n"
                    report += "\n"
                
                report += "### 转换建议\n"
                report += "1. **优先导入高质量技能** (得分≥70)\n"
                report += "2. **中等质量技能需要评估** (得分50-69)\n"
                report += "3. **低质量技能建议忽略** (得分<50)\n"
                
                return report
            else:
                return "\n".join(results)
        
        elif output_format == "workshop_table":
            # 创建Workshop表结构
            table_sql = """
            CREATE TABLE IF NOT EXISTS openclaw_imported_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT NOT NULL,
                skill_type TEXT,
                quality_score INTEGER,
                quality_level TEXT,
                genesis_node_name TEXT,
                import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                content_preview TEXT
            );
            """
            
            # 这里应该调用workshop工具执行SQL
            # 由于不能直接调用其他工具，返回SQL语句
            sql_statements = [table_sql]
            
            if isinstance(results[0], dict):
                for result in results:
                    insert_sql = f"""
                    INSERT INTO openclaw_imported_skills 
                    (skill_name, skill_type, quality_score, quality_level, genesis_node_name, content_preview)
                    VALUES (
                        '{result['file']}',
                        '{result['quality']['level']}',
                        {result['quality']['score']},
                        '{result['quality']['level']}',
                        '{result['file'].replace('.md', '').replace('-', '_').upper()}',
                        '{result['node'][:100]}...'
                    );
                    """
                    sql_statements.append(insert_sql)
            
            return "Workshop SQL语句已生成:\n" + "\n".join(sql_statements)
        
        else:  # genesis_node格式
            if isinstance(results[0], dict):
                output = "## 从OpenClaw技能转换的Genesis节点\n\n"
                for result in results:
                    output += f"### {result['file']} (质量: {result['quality']['level']}, 得分: {result['quality']['score']})\n\n"
                    output += result['node']
                    output += "\n\n---\n\n"
                return output
            else:
                return "\n".join(results)