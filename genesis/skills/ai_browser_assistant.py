import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class AiBrowserAssistant(Tool):
    @property
    def name(self) -> str:
        return "ai_browser_assistant"
        
    @property
    def description(self) -> str:
        return "AI浏览器助手，提供智能信息处理、多页面聚合、内容分析、自动分类等功能"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string", 
                    "description": "要执行的任务类型",
                    "enum": ["multi_page_aggregate", "content_analysis", "auto_categorize", "find_relevant_info", "compare_pages", "extract_structured_data"]
                },
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "目标URL列表",
                    "default": []
                },
                "topic": {
                    "type": "string",
                    "description": "主题或查询关键词",
                    "default": ""
                },
                "output_format": {
                    "type": "string",
                    "description": "输出格式",
                    "enum": ["text", "json", "markdown", "html"],
                    "default": "markdown"
                },
                "max_pages": {
                    "type": "integer",
                    "description": "最大处理页面数",
                    "default": 5
                },
                "depth": {
                    "type": "integer",
                    "description": "爬取深度",
                    "default": 1
                }
            },
            "required": ["task"]
        }
        
    async def execute(self, task: str, urls: list = [], topic: str = "", output_format: str = "markdown", max_pages: int = 5, depth: int = 1) -> str:
        import asyncio
        from playwright.async_api import async_playwright
        import re
        import json
        from datetime import datetime
        from collections import Counter
        
        async def fetch_page_content(url):
            """获取单个页面内容"""
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=True,
                        args=[
                            '--no-sandbox',
                            '--disable-dev-shm-usage',
                            '--disable-gpu',
                            '--proxy-server=socks5://127.0.0.1:20170'
                        ]
                    )
                    
                    context = await browser.new_context(
                        viewport={'width': 1920, 'height': 1080},
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
                    
                    page = await context.new_page()
                    page.set_default_timeout(30000)
                    
                    await page.goto(url, wait_until="networkidle")
                    
                    # 获取标题和主要内容
                    title = await page.title()
                    
                    # 提取文本内容
                    body = await page.query_selector("body")
                    text_content = await body.inner_text() if body else ""
                    
                    # 提取所有文本段落
                    paragraphs = await page.query_selector_all("p, h1, h2, h3, h4, h5, h6, li, td, th")
                    texts = []
                    for element in paragraphs:
                        text = await element.inner_text()
                        if len(text.strip()) > 20:
                            texts.append(text.strip())
                    
                    await browser.close()
                    
                    return {
                        "url": url,
                        "title": title,
                        "full_text": text_content,
                        "paragraphs": texts,
                        "timestamp": datetime.now().isoformat()
                    }
                    
            except Exception as e:
                return {
                    "url": url,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
        
        async def extract_keywords(text, top_n=10):
            """提取关键词（简单实现）"""
            # 移除常见停用词
            stop_words = set([
                "the", "and", "a", "an", "in", "on", "at", "to", "for", "of", 
                "with", "by", "is", "are", "was", "were", "be", "been", "being",
                "have", "has", "had", "do", "does", "did", "will", "would", "should",
                "can", "could", "may", "might", "must", "shall", "this", "that",
                "these", "those", "it", "its", "they", "them", "their", "what",
                "which", "who", "whom", "whose", "how", "when", "where", "why"
            ])
            
            words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
            filtered_words = [w for w in words if w not in stop_words]
            
            word_counts = Counter(filtered_words)
            return [word for word, count in word_counts.most_common(top_n)]
        
        async def analyze_content_similarity(content1, content2):
            """分析内容相似度（简单实现）"""
            words1 = set(re.findall(r'\b[a-zA-Z]{4,}\b', content1.lower()))
            words2 = set(re.findall(r'\b[a-zA-Z]{4,}\b', content2.lower()))
            
            if not words1 or not words2:
                return 0.0
            
            intersection = words1.intersection(words2)
            union = words1.union(words2)
            
            return len(intersection) / len(union) if union else 0.0
        
        try:
            results = []
            
            if task == "multi_page_aggregate":
                if not urls:
                    return "❌ 请提供至少一个URL"
                
                # 并行获取多个页面
                tasks = [fetch_page_content(url) for url in urls[:max_pages]]
                page_contents = await asyncio.gather(*tasks)
                
                # 分析所有页面
                all_texts = []
                all_keywords = []
                
                for content in page_contents:
                    if "error" not in content:
                        results.append(content)
                        all_texts.append(content["full_text"])
                        
                        # 提取关键词
                        keywords = await extract_keywords(content["full_text"])
                        all_keywords.extend(keywords)
                
                # 分析总体关键词
                overall_keywords = Counter(all_keywords).most_common(15)
                
                # 生成报告
                if output_format == "json":
                    return json.dumps({
                        "task": task,
                        "urls_processed": len(results),
                        "pages": results,
                        "overall_keywords": overall_keywords,
                        "timestamp": datetime.now().isoformat()
                    }, indent=2, ensure_ascii=False)
                else:
                    report = f"# 多页面聚合分析报告\n\n"
                    report += f"**分析时间**: {datetime.now()}\n"
                    report += f"**处理页面数**: {len(results)}\n\n"
                    
                    report += "## 📊 总体关键词分析\n"
                    for keyword, count in overall_keywords:
                        report += f"- **{keyword}**: {count}次\n"
                    
                    report += "\n## 📄 页面详情\n"
                    for i, page in enumerate(results, 1):
                        report += f"\n### {i}. {page['title']}\n"
                        report += f"**URL**: {page['url']}\n"
                        report += f"**段落数**: {len(page.get('paragraphs', []))}\n"
                        
                        # 显示前3个段落
                        paragraphs = page.get('paragraphs', [])
                        if paragraphs:
                            report += f"\n**内容预览**:\n"
                            for j, para in enumerate(paragraphs[:3], 1):
                                if len(para) > 200:
                                    para = para[:197] + "..."
                                report += f"{j}. {para}\n"
                    
                    return report
                    
            elif task == "content_analysis":
                if not urls:
                    return "❌ 请提供至少一个URL"
                
                content = await fetch_page_content(urls[0])
                if "error" in content:
                    return f"❌ 获取页面失败: {content['error']}"
                
                # 分析内容
                text = content["full_text"]
                keywords = await extract_keywords(text, 20)
                
                # 统计信息
                char_count = len(text)
                word_count = len(re.findall(r'\b\w+\b', text))
                paragraph_count = len(content.get("paragraphs", []))
                
                # 计算阅读时间（假设200字/分钟）
                reading_time = max(1, word_count // 200)
                
                if output_format == "json":
                    return json.dumps({
                        "task": task,
                        "url": content["url"],
                        "title": content["title"],
                        "analysis": {
                            "character_count": char_count,
                            "word_count": word_count,
                            "paragraph_count": paragraph_count,
                            "estimated_reading_time_minutes": reading_time,
                            "top_keywords": keywords
                        },
                        "timestamp": content["timestamp"]
                    }, indent=2, ensure_ascii=False)
                else:
                    report = f"# 页面内容分析报告\n\n"
                    report += f"**页面标题**: {content['title']}\n"
                    report += f"**URL**: {content['url']}\n"
                    report += f"**分析时间**: {content['timestamp']}\n\n"
                    
                    report += "## 📊 内容统计\n"
                    report += f"- **字符数**: {char_count:,}\n"
                    report += f"- **单词数**: {word_count:,}\n"
                    report += f"- **段落数**: {paragraph_count}\n"
                    report += f"- **预计阅读时间**: {reading_time} 分钟\n\n"
                    
                    report += "## 🔑 关键词分析\n"
                    for i, keyword in enumerate(keywords[:15], 1):
                        report += f"{i}. **{keyword}**\n"
                    
                    report += "\n## 📝 内容预览\n"
                    paragraphs = content.get("paragraphs", [])
                    if paragraphs:
                        for i, para in enumerate(paragraphs[:5], 1):
                            if len(para) > 300:
                                para = para[:297] + "..."
                            report += f"\n**段落 {i}**: {para}\n"
                    
                    return report
            
            elif task == "find_relevant_info":
                if not topic:
                    return "❌ 请提供查询主题"
                
                # 这里简化处理，实际应该结合搜索引擎
                # 使用示例URL进行演示
                demo_urls = [
                    "https://en.wikipedia.org/wiki/Artificial_intelligence",
                    "https://www.ibm.com/topics/artificial-intelligence"
                ]
                
                tasks = [fetch_page_content(url) for url in demo_urls]
                page_contents = await asyncio.gather(*tasks)
                
                relevant_contents = []
                topic_lower = topic.lower()
                
                for content in page_contents:
                    if "error" not in content:
                        text_lower = content["full_text"].lower()
                        if topic_lower in text_lower:
                            # 提取包含主题的段落
                            relevant_paragraphs = []
                            for para in content.get("paragraphs", []):
                                if topic_lower in para.lower():
                                    relevant_paragraphs.append(para)
                            
                            if relevant_paragraphs:
                                content["relevant_paragraphs"] = relevant_paragraphs
                                relevant_contents.append(content)
                
                if output_format == "json":
                    return json.dumps({
                        "task": task,
                        "topic": topic,
                        "relevant_pages_found": len(relevant_contents),
                        "pages": relevant_contents,
                        "timestamp": datetime.now().isoformat()
                    }, indent=2, ensure_ascii=False)
                else:
                    report = f"# 相关信息查找报告\n\n"
                    report += f"**查询主题**: {topic}\n"
                    report += f"**找到相关页面**: {len(relevant_contents)}\n"
                    report += f"**查找时间**: {datetime.now()}\n\n"
                    
                    if not relevant_contents:
                        report += "❌ 未找到相关信息\n"
                    else:
                        for i, content in enumerate(relevant_contents, 1):
                            report += f"\n## {i}. {content['title']}\n"
                            report += f"**URL**: {content['url']}\n\n"
                            
                            paragraphs = content.get("relevant_paragraphs", [])
                            for j, para in enumerate(paragraphs[:3], 1):
                                if len(para) > 400:
                                    para = para[:397] + "..."
                                report += f"**相关段落 {j}**: {para}\n\n"
                    
                    return report
            
            else:
                return f"❌ 任务类型 '{task}' 暂未实现"
                
        except Exception as e:
            return f"❌ 操作失败: {str(e)}"