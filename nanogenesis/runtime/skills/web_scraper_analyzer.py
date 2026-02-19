import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

import requests
from bs4 import BeautifulSoup
import re
from typing import Dict, List, Optional, Any
import json
from urllib.parse import urljoin, urlparse

class WebScraperAnalyzer:
    """网页抓取和分析工具，专门用于获取技术项目实现细节"""
    
    name = "web_scraper_analyzer"
    description = "抓取指定URL的网页内容，提取技术实现细节、代码结构、架构描述等信息"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string", 
                "description": "要抓取的网页URL"
            },
            "extract_patterns": {
                "type": "array",
                "description": "要提取的内容模式列表",
                "items": {
                    "type": "string",
                    "enum": ["code_blocks", "architecture", "implementation", "github_links", "api_docs", "all"]
                },
                "default": ["all"]
            },
            "timeout": {
                "type": "integer",
                "description": "请求超时时间（秒）",
                "default": 10
            }
        },
        "required": ["url"]
    }
    
    def execute(self, url: str, extract_patterns: List[str] = ["all"], timeout: int = 10) -> Dict[str, Any]:
        """执行网页抓取和分析"""
        
        try:
            # 设置请求头，模拟浏览器
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            print(f"正在抓取: {url}")
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            # 解析HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 移除脚本和样式标签
            for script in soup(["script", "style"]):
                script.decompose()
            
            # 提取主要内容
            result = {
                "url": url,
                "status": "success",
                "title": self._extract_title(soup),
                "description": self._extract_description(soup),
                "content_summary": {},
                "technical_details": {},
                "links": [],
                "code_snippets": [],
                "architecture_info": {}
            }
            
            # 根据提取模式处理内容
            if "all" in extract_patterns:
                extract_patterns = ["code_blocks", "architecture", "implementation", "github_links", "api_docs"]
            
            # 提取代码块
            if "code_blocks" in extract_patterns:
                result["code_snippets"] = self._extract_code_blocks(soup)
            
            # 提取架构信息
            if "architecture" in extract_patterns:
                result["architecture_info"] = self._extract_architecture_info(soup)
            
            # 提取实现细节
            if "implementation" in extract_patterns:
                result["technical_details"]["implementation"] = self._extract_implementation_details(soup)
            
            # 提取GitHub链接
            if "github_links" in extract_patterns:
                result["links"] = self._extract_github_links(soup, url)
            
            # 提取API文档
            if "api_docs" in extract_patterns:
                result["technical_details"]["api_docs"] = self._extract_api_docs(soup)
            
            # 提取主要内容摘要
            result["content_summary"] = self._extract_content_summary(soup)
            
            return result
            
        except requests.exceptions.RequestException as e:
            return {
                "url": url,
                "status": "error",
                "error": f"请求失败: {str(e)}"
            }
        except Exception as e:
            return {
                "url": url,
                "status": "error",
                "error": f"处理失败: {str(e)}"
            }
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取页面标题"""
        title_tag = soup.find('title')
        return title_tag.get_text().strip() if title_tag else "无标题"
    
    def _extract_description(self, soup: BeautifulSoup) -> str:
        """提取页面描述"""
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            return meta_desc['content'].strip()
        
        # 尝试从第一个段落提取
        first_p = soup.find('p')
        if first_p:
            text = first_p.get_text().strip()
            if len(text) > 50:
                return text[:200] + "..."
        
        return "无描述"
    
    def _extract_code_blocks(self, soup: BeautifulSoup) -> List[Dict]:
        """提取代码块"""
        code_blocks = []
        
        # 查找pre标签中的代码
        for pre in soup.find_all('pre'):
            code_text = pre.get_text().strip()
            if code_text and len(code_text) > 10:
                code_blocks.append({
                    "type": "pre_block",
                    "content": code_text[:500] + "..." if len(code_text) > 500 else code_text,
                    "language": self._detect_language(code_text)
                })
        
        # 查找code标签
        for code in soup.find_all('code'):
            code_text = code.get_text().strip()
            if code_text and len(code_text) > 20 and code.parent.name != 'pre':
                code_blocks.append({
                    "type": "inline_code",
                    "content": code_text[:200] + "..." if len(code_text) > 200 else code_text
                })
        
        return code_blocks
    
    def _detect_language(self, code: str) -> str:
        """检测代码语言"""
        code_lower = code.lower()
        
        if any(keyword in code_lower for keyword in ['def ', 'import ', 'class ', 'print(', 'self.']):
            return "python"
        elif any(keyword in code_lower for keyword in ['function ', 'const ', 'let ', 'console.log', '=>']):
            return "javascript"
        elif any(keyword in code_lower for keyword in ['public ', 'private ', 'class ', 'void ', 'System.out']):
            return "java"
        elif any(keyword in code_lower for keyword in ['#include', 'int main', 'printf', 'std::']):
            return "c/c++"
        elif any(keyword in code_lower for keyword in ['package ', 'import ', 'func ', ':=', 'fmt.Println']):
            return "go"
        elif any(keyword in code_lower for keyword in ['<html', '<div', 'class=', 'id=']):
            return "html"
        elif any(keyword in code_lower for keyword in ['{', '}', ':', ';', 'color:', 'font-size:']):
            return "css"
        
        return "unknown"
    
    def _extract_architecture_info(self, soup: BeautifulSoup) -> Dict:
        """提取架构信息"""
        architecture_info = {}
        
        # 查找包含架构关键词的段落
        arch_keywords = ['architecture', '架构', 'design', '设计', 'system', '系统', 'framework', '框架']
        
        for keyword in arch_keywords:
            elements = soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'div'], 
                                   string=re.compile(keyword, re.IGNORECASE))
            
            for elem in elements:
                # 获取相关文本
                text = elem.get_text().strip()
                if len(text) > 30:
                    # 获取后续段落
                    next_text = ""
                    next_elem = elem.find_next(['p', 'div'])
                    if next_elem:
                        next_text = next_elem.get_text().strip()[:300]
                    
                    architecture_info[keyword] = {
                        "context": text[:200],
                        "details": next_text
                    }
                    break
        
        return architecture_info
    
    def _extract_implementation_details(self, soup: BeautifulSoup) -> Dict:
        """提取实现细节"""
        impl_info = {}
        
        # 查找实现相关关键词
        impl_keywords = ['implementation', '实现', 'how to', 'setup', '安装', '配置', 'usage', '使用']
        
        for keyword in impl_keywords:
            elements = soup.find_all(['h2', 'h3', 'h4', 'p'], 
                                   string=re.compile(keyword, re.IGNORECASE))
            
            for elem in elements:
                text = elem.get_text().strip()
                if len(text) > 20:
                    # 收集后续几个段落
                    details = []
                    current = elem.find_next(['p', 'li', 'code'])
                    for _ in range(5):
                        if current and current.name in ['p', 'li']:
                            details.append(current.get_text().strip())
                            current = current.find_next(['p', 'li', 'code'])
                        else:
                            break
                    
                    impl_info[keyword] = {
                        "title": text,
                        "details": details[:3]  # 只取前3个
                    }
                    break
        
        return impl_info
    
    def _extract_github_links(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """提取GitHub链接"""
        github_links = []
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.get_text().strip()
            
            # 检查是否是GitHub链接
            if 'github.com' in href:
                full_url = urljoin(base_url, href)
                github_links.append({
                    "url": full_url,
                    "text": text if text else "GitHub链接",
                    "is_github": True
                })
            # 检查是否包含github关键词
            elif 'github' in text.lower() or 'repo' in text.lower():
                full_url = urljoin(base_url, href)
                github_links.append({
                    "url": full_url,
                    "text": text,
                    "is_github": "github" in text.lower()
                })
        
        return github_links
    
    def _extract_api_docs(self, soup: BeautifulSoup) -> Dict:
        """提取API文档信息"""
        api_info = {}
        
        # 查找API相关部分
        api_keywords = ['api', 'endpoint', '接口', 'rest', 'graphql', 'webhook']
        
        for keyword in api_keywords:
            elements = soup.find_all(['h2', 'h3', 'h4'], 
                                   string=re.compile(keyword, re.IGNORECASE))
            
            for elem in elements:
                section_title = elem.get_text().strip()
                
                # 查找代码块或表格
                code_blocks = elem.find_next_all(['pre', 'code', 'table'])
                endpoints = []
                
                for block in code_blocks[:3]:  # 只检查前3个
                    if block.name == 'pre':
                        endpoints.append({
                            "type": "code_example",
                            "content": block.get_text().strip()[:300]
                        })
                    elif block.name == 'table':
                        # 简单提取表格内容
                        rows = []
                        for row in block.find_all('tr')[:5]:
                            cells = [cell.get_text().strip() for cell in row.find_all(['td', 'th'])]
                            if cells:
                                rows.append(cells)
                        endpoints.append({
                            "type": "table",
                            "rows": rows
                        })
                
                if endpoints:
                    api_info[section_title] = endpoints
        
        return api_info
    
    def _extract_content_summary(self, soup: BeautifulSoup) -> Dict:
        """提取内容摘要"""
        # 提取所有文本
        all_text = soup.get_text()
        
        # 分割成段落
        paragraphs = [p.strip() for p in all_text.split('\n') if p.strip()]
        
        # 过滤掉太短的段落
        meaningful_paragraphs = [p for p in paragraphs if len(p) > 50]
        
        # 取前5个有意义的段落作为摘要
        summary_paragraphs = meaningful_paragraphs[:5]
        
        # 提取关键词
        words = re.findall(r'\b\w{4,}\b', all_text.lower())
        word_freq = {}
        for word in words:
            if word not in ['this', 'that', 'with', 'from', 'have', 'what', 'when', 'where']:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        top_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "paragraphs": summary_paragraphs,
            "keywords": [word for word, freq in top_keywords],
            "total_paragraphs": len(meaningful_paragraphs)
        }