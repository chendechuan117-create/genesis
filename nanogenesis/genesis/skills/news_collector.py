import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

"""
新闻收集与摘要生成工具
功能：搜索特定主题新闻，提取关键信息，生成结构化摘要
"""

import json
from datetime import datetime
from typing import List, Dict, Any

class NewsCollector:
    """新闻收集器"""
    
    def __init__(self):
        self.name = "news_collector"
        self.description = "搜索特定主题新闻并生成结构化摘要"
        self.parameters = {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "搜索主题（如：人工智能、科技、金融）"
                },
                "num_articles": {
                    "type": "integer",
                    "description": "收集的文章数量，默认5",
                    "default": 5
                },
                "output_format": {
                    "type": "string",
                    "description": "输出格式：json 或 markdown",
                    "default": "markdown"
                }
            },
            "required": ["topic"]
        }
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行新闻收集"""
        try:
            topic = params.get("topic", "")
            num_articles = params.get("num_articles", 5)
            output_format = params.get("output_format", "markdown")
            
            # 这里实际应该调用 web_search 工具
            # 由于工具调用限制，我们返回模拟数据并说明实际流程
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 模拟搜索结果
            mock_articles = [
                {
                    "title": f"{topic}领域最新突破：研究人员开发出新算法",
                    "source": "科技新闻网",
                    "date": "2026-02-15",
                    "summary": f"研究人员在{topic}领域取得重要进展，新算法在基准测试中表现优异。",
                    "url": "https://example.com/article1",
                    "category": "科技"
                },
                {
                    "title": f"{topic}市场趋势分析：未来五年增长预测",
                    "source": "财经日报",
                    "date": "2026-02-14",
                    "summary": f"根据最新报告，{topic}市场预计在未来五年内将保持高速增长。",
                    "url": "https://example.com/article2",
                    "category": "金融"
                },
                {
                    "title": f"{topic}应用案例：企业如何利用新技术提升效率",
                    "source": "商业周刊",
                    "date": "2026-02-13",
                    "summary": f"多家企业分享了使用{topic}技术优化业务流程的成功经验。",
                    "url": "https://example.com/article3",
                    "category": "商业"
                }
            ]
            
            # 生成摘要
            summary = {
                "topic": topic,
                "collection_time": current_time,
                "total_articles": len(mock_articles),
                "articles": mock_articles,
                "key_trends": [
                    f"{topic}技术持续创新",
                    "市场需求稳步增长",
                    "应用场景不断扩展"
                ]
            }
            
            # 格式化输出
            if output_format == "json":
                output = json.dumps(summary, ensure_ascii=False, indent=2)
            else:
                # Markdown 格式
                output = f"""# {topic} 新闻摘要
**生成时间**: {current_time}
**收集文章**: {len(mock_articles)} 篇

## 📊 关键趋势
{chr(10).join(f"- {trend}" for trend in summary['key_trends'])}

## 📰 最新文章
"""
                for i, article in enumerate(mock_articles, 1):
                    output += f"""
### {i}. {article['title']}
- **来源**: {article['source']}
- **日期**: {article['date']}
- **摘要**: {article['summary']}
- **分类**: {article['category']}
"""
            
            return {
                "success": True,
                "output": output,
                "metadata": {
                    "topic": topic,
                    "articles_collected": len(mock_articles),
                    "format": output_format
                },
                "next_step": "实际部署时需要集成 web_search 工具进行真实搜索"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "suggestion": "检查参数格式或网络连接"
            }


# 工具类定义
class NewsCollectorTool:
    name = "news_collector"
    description = "搜索特定主题新闻并生成结构化摘要"
    parameters = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "搜索主题（如：人工智能、科技、金融）"
            },
            "num_articles": {
                "type": "integer",
                "description": "收集的文章数量，默认5",
                "default": 5
            },
            "output_format": {
                "type": "string",
                "description": "输出格式：json 或 markdown",
                "default": "markdown"
            }
        },
        "required": ["topic"]
    }
    
    def execute(self, params):
        collector = NewsCollector()
        return collector.execute(params)