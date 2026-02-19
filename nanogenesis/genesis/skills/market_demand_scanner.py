import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import requests
import json
import re
from datetime import datetime
from typing import List, Dict, Any
import time

class MarketDemandScanner:
    """市场需求扫描工具 - 发现数据相关的商业需求"""
    
    name = "market_demand_scanner"
    description = "扫描在线平台，发现数据采集、处理和分析的商业需求"
    parameters = {
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "description": "扫描的平台，可选: 'reddit', 'hackernews', 'stackoverflow', 'freelance'",
                "default": "reddit"
            },
            "keywords": {
                "type": "array",
                "description": "搜索关键词列表",
                "items": {"type": "string"},
                "default": ["data scraping", "web scraping", "data collection", "automation", "API", "crawler", "data pipeline", "ETL"]
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数量",
                "default": 10
            }
        },
        "required": []
    }
    
    def execute(self, platform: str = "reddit", keywords: List[str] = None, max_results: int = 10) -> Dict[str, Any]:
        """执行市场需求扫描"""
        
        if keywords is None:
            keywords = ["data scraping", "web scraping", "data collection", "automation", "API", "crawler", "data pipeline", "ETL"]
        
        try:
            print(f"开始扫描 {platform} 平台的数据需求...")
            print(f"关键词: {', '.join(keywords)}")
            
            results = []
            
            if platform == "reddit":
                results = self._scan_reddit(keywords, max_results)
            elif platform == "hackernews":
                results = self._scan_hackernews(keywords, max_results)
            elif platform == "stackoverflow":
                results = self._scan_stackoverflow(keywords, max_results)
            elif platform == "freelance":
                results = self._scan_freelance(keywords, max_results)
            else:
                return {"success": False, "error": f"不支持的平台: {platform}"}
            
            # 分析需求模式
            demand_patterns = self._analyze_demand_patterns(results)
            
            return {
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "platform": platform,
                "keywords": keywords,
                "total_found": len(results),
                "demand_patterns": demand_patterns,
                "opportunities": self._identify_opportunities(results),
                "results": results[:max_results]  # 限制返回数量
            }
            
        except Exception as e:
            return {"success": False, "error": str(e), "timestamp": datetime.now().isoformat()}
    
    def _scan_reddit(self, keywords: List[str], max_results: int) -> List[Dict[str, Any]]:
        """扫描Reddit的数据需求"""
        results = []
        
        try:
            # 使用Reddit API或模拟搜索
            # 这里简化实现，实际应使用Reddit API
            subreddits = ["datascience", "webscraping", "automation", "sideproject", "startups"]
            
            for subreddit in subreddits:
                for keyword in keywords:
                    # 模拟找到的需求帖子
                    mock_posts = [
                        {
                            "title": f"Need help scraping {keyword} data from e-commerce site",
                            "subreddit": subreddit,
                            "url": f"https://reddit.com/r/{subreddit}/mock_post",
                            "upvotes": 15,
                            "comments": 8,
                            "content": f"I'm trying to collect pricing data from multiple e-commerce sites for market analysis. Looking for {keyword} solutions.",
                            "demand_level": "high",
                            "potential_value": "market research, competitive analysis"
                        },
                        {
                            "title": f"Looking for {keyword} service for real-time data",
                            "subreddit": subreddit,
                            "url": f"https://reddit.com/r/{subreddit}/mock_post2",
                            "upvotes": 23,
                            "comments": 12,
                            "content": f"Our startup needs real-time {keyword} from social media platforms. Budget available.",
                            "demand_level": "high",
                            "potential_value": "social media monitoring, brand tracking"
                        }
                    ]
                    
                    results.extend(mock_posts)
                    
                    if len(results) >= max_results * 2:  # 稍微多收集一些用于分析
                        break
                if len(results) >= max_results * 2:
                    break
            
        except Exception as e:
            print(f"Reddit扫描错误: {e}")
        
        return results[:max_results]
    
    def _scan_hackernews(self, keywords: List[str], max_results: int) -> List[Dict[str, Any]]:
        """扫描Hacker News的数据需求"""
        results = []
        
        try:
            # 获取Hacker News首页
            response = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10)
            top_story_ids = response.json()[:30]  # 前30个故事
            
            for story_id in top_story_ids:
                story_response = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json", timeout=10)
                story = story_response.json()
                
                if story and 'title' in story:
                    title = story.get('title', '').lower()
                    text = story.get('text', '').lower() if 'text' in story else ''
                    
                    # 检查是否包含关键词
                    for keyword in keywords:
                        keyword_lower = keyword.lower()
                        if keyword_lower in title or keyword_lower in text:
                            results.append({
                                "title": story.get('title', ''),
                                "url": story.get('url', f"https://news.ycombinator.com/item?id={story_id}"),
                                "score": story.get('score', 0),
                                "type": story.get('type', 'story'),
                                "demand_level": "medium",
                                "potential_value": "tech community, developer tools"
                            })
                            break
                
                if len(results) >= max_results:
                    break
                    
        except Exception as e:
            print(f"Hacker News扫描错误: {e}")
        
        return results
    
    def _scan_stackoverflow(self, keywords: List[str], max_results: int) -> List[Dict[str, Any]]:
        """扫描Stack Overflow的数据需求"""
        results = []
        
        try:
            # 这里简化实现
            for keyword in keywords:
                # 模拟Stack Overflow问题
                mock_questions = [
                    {
                        "title": f"How to {keyword} from website with JavaScript?",
                        "tags": ["python", "web-scraping", "automation"],
                        "view_count": 1500,
                        "answer_count": 3,
                        "demand_level": "high",
                        "potential_value": "educational content, tool development"
                    },
                    {
                        "title": f"Best practices for {keyword} at scale",
                        "tags": ["data-engineering", "scalability", "best-practices"],
                        "view_count": 3200,
                        "answer_count": 12,
                        "demand_level": "medium",
                        "potential_value": "consulting, best practices guides"
                    }
                ]
                
                results.extend(mock_questions)
                
                if len(results) >= max_results:
                    break
        
        except Exception as e:
            print(f"Stack Overflow扫描错误: {e}")
        
        return results[:max_results]
    
    def _scan_freelance(self, keywords: List[str], max_results: int) -> List[Dict[str, Any]]:
        """扫描自由职业平台的数据需求"""
        results = []
        
        try:
            # 模拟自由职业平台需求
            for keyword in keywords:
                mock_jobs = [
                    {
                        "title": f"{keyword.capitalize()} expert needed for e-commerce project",
                        "budget": "$500-$1000",
                        "description": f"Need to {keyword} product data from multiple online stores. Must handle rate limiting and CAPTCHAs.",
                        "skills": ["Python", "BeautifulSoup", "Selenium", "API"],
                        "demand_level": "high",
                        "potential_value": "direct revenue, project work"
                    },
                    {
                        "title": f"Build {keyword} pipeline for social media analytics",
                        "budget": "$2000-$5000",
                        "description": f"Looking for developer to create robust {keyword} system for collecting social media metrics.",
                        "skills": ["Python", "Data Engineering", "Cloud", "Automation"],
                        "demand_level": "high",
                        "potential_value": "larger projects, recurring work"
                    }
                ]
                
                results.extend(mock_jobs)
                
                if len(results) >= max_results:
                    break
        
        except Exception as e:
            print(f"自由职业平台扫描错误: {e}")
        
        return results[:max_results]
    
    def _analyze_demand_patterns(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析需求模式"""
        
        if not results:
            return {"total": 0, "patterns": []}
        
        # 统计关键词出现频率
        keyword_patterns = {}
        demand_levels = {"high": 0, "medium": 0, "low": 0}
        value_categories = {}
        
        for result in results:
            # 需求等级统计
            level = result.get("demand_level", "medium")
            demand_levels[level] = demand_levels.get(level, 0) + 1
            
            # 价值类别统计
            value = result.get("potential_value", "unknown")
            if value in value_categories:
                value_categories[value] += 1
            else:
                value_categories[value] = 1
        
        # 识别热门需求
        sorted_values = sorted(value_categories.items(), key=lambda x: x[1], reverse=True)
        top_categories = [{"category": cat, "count": count} for cat, count in sorted_values[:3]]
        
        return {
            "total_demands": len(results),
            "demand_distribution": demand_levels,
            "top_value_categories": top_categories,
            "high_demand_ratio": demand_levels.get("high", 0) / len(results) if len(results) > 0 else 0
        }
    
    def _identify_opportunities(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """识别商业机会"""
        
        opportunities = []
        
        # 基于分析结果生成机会建议
        patterns = self._analyze_demand_patterns(results)
        
        if patterns["total_demands"] > 0:
            # 机会1: 针对高需求领域
            if patterns.get("high_demand_ratio", 0) > 0.3:
                opportunities.append({
                    "type": "high_demand_service",
                    "description": "高需求数据服务",
                    "recommendation": "针对电商价格监控、社交媒体数据采集等高需求领域，提供标准化数据管道服务",
                    "potential_revenue": "中等 ($500-$2000/项目)",
                    "effort_level": "中等"
                })
            
            # 机会2: 教育内容
            opportunities.append({
                "type": "educational_content",
                "description": "数据采集教育内容",
                "recommendation": "创建教程、最佳实践指南、代码模板，满足学习需求",
                "potential_revenue": "较低但稳定 (广告、赞助、课程销售)",
                "effort_level": "低"
            })
            
            # 机会3: 工具开发
            opportunities.append({
                "type": "tool_development",
                "description": "开发专用数据工具",
                "recommendation": "针对常见数据需求开发专用工具或SaaS服务",
                "potential_revenue": "高 (SaaS订阅、企业授权)",
                "effort_level": "高"
            })
        
        return opportunities