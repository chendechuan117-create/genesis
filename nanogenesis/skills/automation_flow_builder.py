import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

from typing import Dict, List, Any, Optional
import json
import subprocess
import os

class AutomationFlowBuilder:
    """自动化流程构建器 - 基于OpenClaw等前辈经验构建自动化流程"""
    
    name = "automation_flow_builder"
    description = "构建自动化流程的工具，支持模拟点击、素材获取等自动化任务"
    parameters = {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string", 
                "description": "自动化目标（如：模拟点击获取抖音素材）"
            },
            "reference_tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "参考工具（如：openclaw, selenium, playwright等）",
                "default": ["openclaw"]
            },
            "complexity": {
                "type": "string",
                "enum": ["simple", "medium", "complex"],
                "description": "流程复杂度",
                "default": "medium"
            },
            "output_type": {
                "type": "string",
                "enum": ["plan", "code", "both"],
                "description": "输出类型：计划文档或代码",
                "default": "plan"
            }
        },
        "required": ["goal"]
    }
    
    def execute(self, goal: str, reference_tools: List[str] = None, 
                complexity: str = "medium", output_type: str = "plan") -> Dict[str, Any]:
        """执行自动化流程构建"""
        
        if reference_tools is None:
            reference_tools = ["openclaw"]
        
        # 1. 分析目标，生成技术选型
        tech_stack = self._analyze_tech_stack(goal, reference_tools, complexity)
        
        # 2. 生成实施计划
        implementation_plan = self._generate_implementation_plan(goal, tech_stack, complexity)
        
        # 3. 生成安全沙箱建议
        safety_plan = self._generate_safety_plan(tech_stack)
        
        # 4. 生成分阶段执行步骤
        phased_steps = self._generate_phased_steps(implementation_plan)
        
        # 5. 生成代码（如果需要）
        code_snippets = {}
        if output_type in ["code", "both"]:
            code_snippets = self._generate_code_snippets(goal, tech_stack)
        
        result = {
            "goal": goal,
            "tech_stack": tech_stack,
            "implementation_plan": implementation_plan,
            "safety_plan": safety_plan,
            "phased_steps": phased_steps,
            "immediate_actions": self._get_immediate_actions(goal, tech_stack)
        }
        
        if code_snippets:
            result["code_snippets"] = code_snippets
        
        return result
    
    def _analyze_tech_stack(self, goal: str, reference_tools: List[str], complexity: str) -> Dict[str, Any]:
        """分析技术栈"""
        
        tech_stack = {
            "automation_frameworks": [],
            "browser_automation": [],
            "data_processing": [],
            "scheduling": [],
            "monitoring": []
        }
        
        # 基于目标分析
        if "模拟点击" in goal or "浏览器" in goal:
            tech_stack["browser_automation"].extend(["playwright", "selenium", "puppeteer"])
        
        if "获取素材" in goal or "数据采集" in goal:
            tech_stack["data_processing"].extend(["beautifulsoup4", "requests", "scrapy"])
            tech_stack["monitoring"].append("schedule")
        
        if "openclaw" in reference_tools:
            tech_stack["automation_frameworks"].append("openclaw (分布式多代理框架)")
            tech_stack["scheduling"].append("openclaw_scheduler")
        
        # 根据复杂度调整
        if complexity == "simple":
            tech_stack["browser_automation"] = ["playwright"]  # 最简单
            tech_stack["data_processing"] = ["beautifulsoup4", "requests"]
        elif complexity == "complex":
            tech_stack["scheduling"].append("celery")
            tech_stack["monitoring"].append("prometheus")
        
        return tech_stack
    
    def _generate_implementation_plan(self, goal: str, tech_stack: Dict[str, Any], complexity: str) -> List[str]:
        """生成实施计划"""
        
        plan = []
        
        # 基础步骤
        plan.append("1. 环境准备：安装Python依赖，配置浏览器驱动")
        plan.append("2. 目标分析：明确自动化流程的具体步骤")
        plan.append("3. 原型开发：使用Playwright/Selenium编写基础自动化脚本")
        
        # 根据技术栈添加步骤
        if "openclaw" in str(tech_stack["automation_frameworks"]):
            plan.append("4. OpenClaw集成：将自动化脚本封装为OpenClaw代理")
            plan.append("5. 分布式部署：配置多代理协同工作")
        
        if "数据采集" in goal:
            plan.append("6. 数据存储：设计数据库结构，存储采集结果")
            plan.append("7. 数据清洗：处理重复、无效数据")
        
        if complexity == "complex":
            plan.append("8. 监控告警：设置性能监控和异常告警")
            plan.append("9. 容错处理：实现失败重试和错误恢复")
        
        plan.append("10. 测试验证：完整流程测试，优化性能")
        
        return plan
    
    def _generate_safety_plan(self, tech_stack: Dict[str, Any]) -> Dict[str, List[str]]:
        """生成安全沙箱计划"""
        
        safety = {
            "before_execution": [],
            "during_execution": [],
            "after_execution": []
        }
        
        safety["before_execution"].extend([
            "创建虚拟环境：python -m venv automation_env",
            "备份当前配置：cp ~/.config/chromium ~/.config/chromium.backup",
            "设置资源限制：ulimit -n 1024 (防止文件描述符耗尽)"
        ])
        
        safety["during_execution"].extend([
            "使用代理IP池：避免IP被封禁",
            "设置请求间隔：time.sleep(random.uniform(1, 3))",
            "实现异常捕获：try-except处理网络异常"
        ])
        
        safety["after_execution"].extend([
            "清理临时文件：rm -rf /tmp/automation_*",
            "恢复浏览器配置：如有修改则还原",
            "生成执行报告：记录成功/失败情况"
        ])
        
        return safety
    
    def _generate_phased_steps(self, implementation_plan: List[str]) -> Dict[str, List[str]]:
        """生成分阶段执行步骤"""
        
        phases = {
            "phase_1_immediate": [],
            "phase_2_development": [],
            "phase_3_optimization": []
        }
        
        # 第一阶段：立即可做
        phases["phase_1_immediate"].extend([
            "使用现有工具调研：web_search搜索最新自动化框架",
            "分析OpenClaw文档：了解其架构和集成方式",
            "创建项目目录结构：mkdir -p automation_project/{src,config,logs}"
        ])
        
        # 第二阶段：需要开发
        for i, step in enumerate(implementation_plan[:5], 1):
            phases["phase_2_development"].append(f"{i}. {step}")
        
        # 第三阶段：优化扩展
        for i, step in enumerate(implementation_plan[5:], 6):
            phases["phase_3_optimization"].append(f"{i}. {step}")
        
        return phases
    
    def _generate_code_snippets(self, goal: str, tech_stack: Dict[str, Any]) -> Dict[str, str]:
        """生成代码片段"""
        
        snippets = {}
        
        # Playwright基础模板
        if "playwright" in str(tech_stack["browser_automation"]):
            snippets["playwright_template"] = '''from playwright.sync_api import sync_playwright
import time
import random

def automate_browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 调试时可设为False
        page = browser.new_page()
        
        try:
            # 访问目标网站
            page.goto("https://example.com")
            
            # 模拟点击
            page.click("button.primary")
            
            # 等待加载
            page.wait_for_selector(".content-loaded", timeout=10000)
            
            # 获取内容
            content = page.inner_text(".target-content")
            
            # 保存结果
            with open("result.txt", "w") as f:
                f.write(content)
                
            print("自动化完成")
            
        except Exception as e:
            print(f"错误: {e}")
            
        finally:
            browser.close()

if __name__ == "__main__":
    automate_browser()'''
        
        # 数据采集模板
        if "beautifulsoup4" in str(tech_stack["data_processing"]):
            snippets["data_collection_template"] = '''import requests
from bs4 import BeautifulSoup
import json
import time

class DataCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def collect_data(self, url):
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 提取数据逻辑
            data = {
                'title': soup.title.string if soup.title else '',
                'content': self._extract_content(soup),
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return data
            
        except Exception as e:
            print(f"采集失败: {e}")
            return None
    
    def _extract_content(self, soup):
        # 自定义内容提取逻辑
        # 这里可以根据具体网站结构调整
        pass

# 使用示例
collector = DataCollector()
result = collector.collect_data("https://example.com")
if result:
    with open("data.json", "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)'''
        
        return snippets
    
    def _get_immediate_actions(self, goal: str, tech_stack: Dict[str, Any]) -> List[str]:
        """获取立即可执行的动作"""
        
        actions = []
        
        actions.append(f"1. 搜索最新信息：web_search('{goal} automation with playwright selenium')")
        actions.append("2. 检查系统环境：python --version, pip list | grep playwright")
        
        if "openclaw" in str(tech_stack["automation_frameworks"]):
            actions.append("3. 搜索OpenClaw案例：web_search('openclaw automation examples github')")
        
        actions.append("4. 创建项目结构：mkdir automation_project && cd automation_project")
        actions.append("5. 安装基础依赖：pip install playwright beautifulsoup4 requests")
        
        return actions