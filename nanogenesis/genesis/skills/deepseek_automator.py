import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool


import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

class DeepSeekAutomatorTool(Tool):
    @property
    def name(self):
        return "deepseek_automator"
    
    @property
    def description(self):
        return "自动化访问DeepSeek网页版并获取AI回复"
    
    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "要询问的问题"},
                "wait_time": {"type": "integer", "default": 10, "description": "等待回复的时间(秒)"}
            },
            "required": ["question"]
        }
    
    async def execute(self, question, wait_time=10):
        try:
            # 启动浏览器
            driver = webdriver.Chrome()
            driver.get("https://chat.deepseek.com")
            
            # 等待页面加载
            time.sleep(3)
            
            # 查找输入框并发送问题
            input_box = driver.find_element(By.TAG_NAME, "textarea")
            input_box.send_keys(question)
            input_box.send_keys(Keys.RETURN)
            
            # 等待回复
            time.sleep(wait_time)
            
            # 提取最新回复
            # 这里需要根据实际页面结构调整选择器
            responses = driver.find_elements(By.CSS_SELECTOR, ".message-content")
            if responses:
                latest_response = responses[-1].text
            else:
                latest_response = "未找到回复"
            
            driver.quit()
            
            return f"问题: {question}\n回复: {latest_response[:500]}..."
            
        except Exception as e:
            return f"自动化失败: {str(e)}"
