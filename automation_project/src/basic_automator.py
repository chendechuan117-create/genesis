#!/usr/bin/env python3
"""
基础自动化脚本 - 模拟点击和内容获取
"""

import time
import json
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

class BasicAutomator:
    """基础自动化器"""
    
    def __init__(self, headless=False, slow_mo=100):
        """
        初始化自动化器
        
        Args:
            headless: 是否无头模式
            slow_mo: 操作延迟（毫秒），模拟人类操作
        """
        self.headless = headless
        self.slow_mo = slow_mo
        self.results_dir = "data/results"
        os.makedirs(self.results_dir, exist_ok=True)
        
    def save_result(self, data, filename_prefix="result"):
        """保存结果到文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.results_dir}/{filename_prefix}_{timestamp}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 结果已保存到: {filename}")
        return filename
    
    def automate_website(self, url, actions):
        """
        自动化网站操作
        
        Args:
            url: 目标网址
            actions: 操作列表，每个操作是字典格式
                {
                    "type": "click"/"extract"/"input",
                    "selector": CSS选择器,
                    "value": 输入值（仅type="input"需要）,
                    "wait": 等待时间（秒）
                }
        
        Returns:
            提取的内容列表
        """
        print(f"🚀 开始自动化: {url}")
        
        with sync_playwright() as p:
            # 启动浏览器
            browser = p.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo
            )
            
            # 创建页面上下文
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            
            page = context.new_page()
            
            try:
                # 访问目标页面
                print(f"🌐 访问: {url}")
                page.goto(url, wait_until="networkidle")
                time.sleep(2)  # 等待页面完全加载
                
                results = []
                
                # 执行每个操作
                for i, action in enumerate(actions):
                    print(f"📝 执行操作 {i+1}/{len(actions)}: {action['type']} -> {action.get('selector', 'N/A')}")
                    
                    try:
                        if action["type"] == "click":
                            page.click(action["selector"])
                            print(f"   ✅ 点击成功: {action['selector']}")
                            
                        elif action["type"] == "extract":
                            # 提取文本内容
                            content = page.inner_text(action["selector"])
                            result_item = {
                                "action": action,
                                "content": content.strip(),
                                "timestamp": datetime.now().isoformat()
                            }
                            results.append(result_item)
                            print(f"   📄 提取内容: {content[:100]}...")
                            
                        elif action["type"] == "input":
                            page.fill(action["selector"], action["value"])
                            print(f"   ⌨️  输入成功: {action['value']}")
                        
                        # 等待指定时间
                        wait_time = action.get("wait", 1)
                        if wait_time > 0:
                            time.sleep(wait_time)
                            
                    except Exception as e:
                        print(f"   ❌ 操作失败: {e}")
                        # 截图保存错误
                        screenshot_path = f"logs/error_{datetime.now().strftime('%H%M%S')}.png"
                        page.screenshot(path=screenshot_path)
                        print(f"   📸 错误截图已保存: {screenshot_path}")
                
                return results
                
            except Exception as e:
                print(f"❌ 自动化过程出错: {e}")
                return None
                
            finally:
                # 关闭浏览器
                browser.close()
                print("🔄 浏览器已关闭")

class MaterialCollector:
    """素材收集器"""
    
    def __init__(self, save_dir="data/materials"):
        self.save_dir = save_dir
        os.makedirs(save_dir, exist_ok=True)
    
    def collect_text(self, text, source="unknown", tags=None):
        """收集文本素材"""
        if not text or len(text.strip()) < 10:
            return None
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.save_dir}/text_{timestamp}.txt"
        
        metadata = {
            "source": source,
            "timestamp": datetime.now().isoformat(),
            "length": len(text),
            "tags": tags or []
        }
        
        content = f"=== 元数据 ===\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n\n"
        content += f"=== 内容 ===\n{text}\n"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"📝 文本素材已保存: {filename}")
        return filename
    
    def collect_urls(self, urls, category="general"):
        """收集URL列表"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.save_dir}/urls_{category}_{timestamp}.json"
        
        data = {
            "category": category,
            "timestamp": datetime.now().isoformat(),
            "count": len(urls),
            "urls": urls
        }
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"🔗 URL列表已保存: {filename} ({len(urls)}个)")
        return filename

def demo_automation():
    """演示自动化功能"""
    print("🎬 开始演示自动化...")
    
    # 创建自动化器
    automator = BasicAutomator(headless=False, slow_mo=200)
    collector = MaterialCollector()
    
    # 示例：访问百度并搜索
    actions = [
        {"type": "extract", "selector": "title", "wait": 1},
        {"type": "input", "selector": "#kw", "value": "自动化测试", "wait": 1},
        {"type": "click", "selector": "#su", "wait": 2},
        {"type": "extract", "selector": ".result", "wait": 1}
    ]
    
    # 执行自动化
    results = automator.automate_website("https://www.baidu.com", actions)
    
    if results:
        # 保存结果
        automator.save_result(results, "baidu_search")
        
        # 收集素材
        for result in results:
            if result["action"]["type"] == "extract":
                collector.collect_text(
                    result["content"],
                    source="baidu",
                    tags=["search", "demo"]
                )
    
    print("🎉 演示完成！")

if __name__ == "__main__":
    demo_automation()