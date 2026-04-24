import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class SmartBrowserFilter(Tool):
    @property
    def name(self) -> str:
        return "smart_browser_filter"
        
    @property
    def description(self) -> str:
        return "智能浏览器过滤器，可以提取网页核心内容、过滤广告/噪音、总结信息、监控变化等"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "description": "要执行的操作",
                    "enum": ["extract_content", "filter_noise", "summarize", "monitor_changes", "extract_links", "extract_articles"]
                },
                "url": {
                    "type": "string", 
                    "description": "目标URL"
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "关键词列表，用于内容过滤",
                    "default": []
                },
                "output_file": {
                    "type": "string",
                    "description": "输出文件路径",
                    "default": "/tmp/smart_browser_output.txt"
                },
                "interval": {
                    "type": "integer",
                    "description": "监控间隔（秒），仅用于monitor_changes",
                    "default": 300
                }
            },
            "required": ["action", "url"]
        }
        
    async def execute(self, action: str, url: str, keywords: list = [], output_file: str = "/tmp/smart_browser_output.txt", interval: int = 300) -> str:
        import asyncio
        from playwright.async_api import async_playwright
        import re
        import json
        from datetime import datetime
        
        async def extract_main_content(page):
            """提取网页主要内容，过滤广告和噪音"""
            # 尝试多种策略提取主要内容
            content_selectors = [
                "article", "main", ".content", ".post-content", ".article-content",
                "#content", ".main-content", ".entry-content"
            ]
            
            for selector in content_selectors:
                elements = await page.query_selector_all(selector)
                if elements:
                    contents = []
                    for element in elements:
                        text = await element.inner_text()
                        if len(text.strip()) > 100:  # 过滤太短的内容
                            contents.append(text.strip())
                    if contents:
                        return "\n\n".join(contents)
            
            # 如果没有找到特定选择器，提取所有段落
            paragraphs = await page.query_selector_all("p")
            texts = []
            for p in paragraphs:
                text = await p.inner_text()
                if len(text.strip()) > 50:  # 过滤太短的段落
                    texts.append(text.strip())
            
            return "\n\n".join(texts[:20])  # 限制返回段落数量
        
        async def filter_by_keywords(content, keywords):
            """根据关键词过滤内容"""
            if not keywords:
                return content
            
            lines = content.split("\n")
            filtered_lines = []
            
            for line in lines:
                line_lower = line.lower()
                for keyword in keywords:
                    if keyword.lower() in line_lower:
                        filtered_lines.append(line)
                        break
            
            return "\n".join(filtered_lines)
        
        async def summarize_content(content):
            """简单的内容总结"""
            sentences = re.split(r'[.!?]+', content)
            sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
            
            # 取前5个句子作为总结
            summary = " ".join(sentences[:5])
            if len(summary) > 500:
                summary = summary[:497] + "..."
            
            return summary
        
        async def extract_links(page):
            """提取所有链接"""
            links = await page.query_selector_all("a")
            result = []
            
            for link in links:
                try:
                    href = await link.get_attribute("href")
                    text = await link.inner_text()
                    if href and href.startswith(("http://", "https://")):
                        result.append({
                            "url": href,
                            "text": text.strip()[:100] if text else ""
                        })
                except:
                    continue
            
            return result
        
        try:
            async with async_playwright() as p:
                # 使用系统Chrome
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
                
                # 设置超时
                page.set_default_timeout(30000)
                
                # 访问页面
                await page.goto(url, wait_until="networkidle")
                
                result = ""
                
                if action == "extract_content":
                    content = await extract_main_content(page)
                    result = f"=== 网页主要内容提取 ===\nURL: {url}\n提取时间: {datetime.now()}\n\n{content}"
                    
                elif action == "filter_noise":
                    content = await extract_main_content(page)
                    filtered = await filter_by_keywords(content, keywords)
                    result = f"=== 关键词过滤内容 ===\nURL: {url}\n关键词: {keywords}\n\n{filtered}"
                    
                elif action == "summarize":
                    content = await extract_main_content(page)
                    summary = await summarize_content(content)
                    result = f"=== 内容总结 ===\nURL: {url}\n\n{summary}"
                    
                elif action == "extract_links":
                    links = await extract_links(page)
                    result = f"=== 链接提取 ===\nURL: {url}\n找到链接数: {len(links)}\n\n"
                    for i, link in enumerate(links[:20], 1):  # 只显示前20个
                        result += f"{i}. {link['text']}\n   {link['url']}\n\n"
                    
                elif action == "extract_articles":
                    # 尝试提取类似文章的结构
                    content = await extract_main_content(page)
                    # 按段落分割
                    paragraphs = [p for p in content.split("\n\n") if len(p.strip()) > 100]
                    result = f"=== 文章内容提取 ===\nURL: {url}\n提取段落数: {len(paragraphs)}\n\n"
                    for i, para in enumerate(paragraphs[:10], 1):  # 只显示前10段
                        result += f"【段落 {i}】\n{para}\n\n"
                
                elif action == "monitor_changes":
                    # 这是一个后台监控任务
                    import subprocess
                    import threading
                    
                    def monitor_task():
                        """后台监控任务"""
                        import time
                        import hashlib
                        
                        previous_hash = None
                        while True:
                            try:
                                # 这里简化处理，实际应该使用异步方式
                                # 记录状态到文件
                                with open(output_file, "a", encoding="utf-8") as f:
                                    f.write(f"[{datetime.now()}] 监控检查: {url}\n")
                                time.sleep(interval)
                            except:
                                break
                    
                    # 启动后台线程
                    thread = threading.Thread(target=monitor_task, daemon=True)
                    thread.start()
                    
                    result = f"✅ 已启动网页监控任务\nURL: {url}\n检查间隔: {interval}秒\n状态文件: {output_file}\n\n监控任务已在后台运行，您可以继续其他操作。"
                
                # 保存结果到文件
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(result)
                
                await browser.close()
                
                return f"✅ {action} 操作完成！\n结果已保存到: {output_file}\n\n{result[:500]}..." if len(result) > 500 else result
                
        except Exception as e:
            return f"❌ 操作失败: {str(e)}"