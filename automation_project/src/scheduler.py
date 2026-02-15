#!/usr/bin/env python3
"""
自动化任务调度器
支持定时执行、并发控制、结果监控
"""

import schedule
import time
import threading
import json
import os
from datetime import datetime
from queue import Queue
from basic_automator import BasicAutomator, MaterialCollector

class TaskScheduler:
    """任务调度器"""
    
    def __init__(self, max_concurrent=3):
        """
        初始化调度器
        
        Args:
            max_concurrent: 最大并发任务数
        """
        self.max_concurrent = max_concurrent
        self.task_queue = Queue()
        self.active_tasks = 0
        self.task_history = []
        self.log_dir = "logs"
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 初始化组件
        self.automator = BasicAutomator(headless=True)  # 生产环境用无头模式
        self.collector = MaterialCollector()
        
    def log_task(self, task_id, status, message, data=None):
        """记录任务日志"""
        log_entry = {
            "task_id": task_id,
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "message": message,
            "data": data
        }
        
        self.task_history.append(log_entry)
        
        # 保存到文件
        log_file = f"{self.log_dir}/tasks_{datetime.now().strftime('%Y%m%d')}.json"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        
        print(f"[{status}] {task_id}: {message}")
        
    def add_task(self, task_config):
        """
        添加任务到队列
        
        Args:
            task_config: 任务配置字典
                {
                    "id": "任务ID",
                    "type": "website"/"monitor"/"collect",
                    "url": "目标网址",
                    "actions": [操作列表],
                    "schedule": "10:30" 或 "every 1 hour",
                    "enabled": True
                }
        """
        self.task_queue.put(task_config)
        self.log_task(task_config["id"], "QUEUED", "任务已加入队列", task_config)
        
    def worker(self):
        """工作线程，执行任务"""
        while True:
            if self.active_tasks >= self.max_concurrent:
                time.sleep(1)
                continue
                
            if not self.task_queue.empty():
                task_config = self.task_queue.get()
                self.active_tasks += 1
                
                # 在新线程中执行任务
                thread = threading.Thread(
                    target=self.execute_task,
                    args=(task_config,)
                )
                thread.start()
                
            time.sleep(0.5)
    
    def execute_task(self, task_config):
        """执行单个任务"""
        task_id = task_config["id"]
        
        try:
            self.log_task(task_id, "STARTED", "开始执行任务")
            
            if task_config["type"] == "website":
                # 网站自动化任务
                results = self.automator.automate_website(
                    task_config["url"],
                    task_config["actions"]
                )
                
                if results:
                    # 保存结果
                    result_file = self.automator.save_result(results, task_id)
                    
                    # 收集素材
                    for result in results:
                        if result["action"]["type"] == "extract":
                            self.collector.collect_text(
                                result["content"],
                                source=task_config["url"],
                                tags=[task_config["type"], task_id]
                            )
                    
                    self.log_task(task_id, "COMPLETED", 
                                 f"任务完成，收集到{len(results)}条结果",
                                 {"result_file": result_file})
                else:
                    self.log_task(task_id, "FAILED", "未获取到结果")
                    
            elif task_config["type"] == "monitor":
                # 监控任务（简化版）
                self.log_task(task_id, "COMPLETED", "监控任务执行完成")
                
            elif task_config["type"] == "collect":
                # 收集任务
                self.log_task(task_id, "COMPLETED", "收集任务执行完成")
                
        except Exception as e:
            self.log_task(task_id, "ERROR", f"任务执行出错: {str(e)}")
            
        finally:
            self.active_tasks -= 1
            self.task_queue.task_done()
    
    def setup_scheduled_tasks(self):
        """设置定时任务"""
        # 这里可以添加具体的定时任务
        # 例如：schedule.every().day.at("10:30").do(self.add_task, task_config)
        
        # 演示：每5分钟执行一次测试任务
        test_task = {
            "id": "test_daily",
            "type": "website",
            "url": "https://www.baidu.com",
            "actions": [
                {"type": "extract", "selector": "title", "wait": 1}
            ],
            "schedule": "every 5 minutes",
            "enabled": True
        }
        
        schedule.every(5).minutes.do(self.add_task, test_task)
        self.log_task("system", "INFO", "定时任务已设置：每5分钟执行测试任务")
    
    def run(self):
        """运行调度器"""
        print("🚀 启动自动化任务调度器...")
        print(f"📊 配置：最大并发 {self.max_concurrent} 个任务")
        
        # 设置定时任务
        self.setup_scheduled_tasks()
        
        # 启动工作线程
        worker_thread = threading.Thread(target=self.worker, daemon=True)
        worker_thread.start()
        
        # 启动调度线程
        schedule_thread = threading.Thread(target=self.run_schedule, daemon=True)
        schedule_thread.start()
        
        # 主线程保持运行
        try:
            while True:
                self.print_status()
                time.sleep(60)  # 每分钟打印一次状态
                
        except KeyboardInterrupt:
            print("\n🛑 收到停止信号，正在关闭调度器...")
            self.log_task("system", "STOPPED", "调度器已停止")
    
    def run_schedule(self):
        """运行schedule调度循环"""
        while True:
            schedule.run_pending()
            time.sleep(1)
    
    def print_status(self):
        """打印当前状态"""
        status = {
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "队列任务数": self.task_queue.qsize(),
            "活跃任务数": self.active_tasks,
            "历史任务数": len(self.task_history),
            "最大并发数": self.max_concurrent
        }
        
        print("\n" + "="*50)
        print("📈 调度器状态")
        for key, value in status.items():
            print(f"  {key}: {value}")
        print("="*50)

def create_sample_tasks():
    """创建示例任务"""
    scheduler = TaskScheduler(max_concurrent=2)
    
    # 示例1：新闻网站监控
    news_task = {
        "id": "news_monitor",
        "type": "website",
        "url": "https://news.baidu.com",
        "actions": [
            {"type": "extract", "selector": ".hotnews a", "wait": 2},
            {"type": "extract", "selector": ".mod-tab-content .ulist li", "wait": 1}
        ],
        "schedule": "every 1 hour",
        "enabled": True
    }
    
    # 示例2：技术博客收集
    tech_task = {
        "id": "tech_blog_collect",
        "type": "website", 
        "url": "https://blog.csdn.net",
        "actions": [
            {"type": "extract", "selector": ".main_father .title a", "wait": 2},
            {"type": "click", "selector": ".more", "wait": 1},
            {"type": "extract", "selector": ".article-list .title a", "wait": 2}
        ],
        "schedule": "every 2 hours",
        "enabled": True
    }
    
    # 立即执行一次测试
    test_task = {
        "id": "quick_test",
        "type": "website",
        "url": "https://www.example.com",
        "actions": [
            {"type": "extract", "selector": "h1", "wait": 1},
            {"type": "extract", "selector": "p", "wait": 1}
        ],
        "schedule": "now",
        "enabled": True
    }
    
    # 添加任务
    scheduler.add_task(test_task)
    scheduler.add_task(news_task)
    scheduler.add_task(tech_task)
    
    return scheduler

if __name__ == "__main__":
    print("🤖 自动化赚钱系统 - 任务调度器")
    print("="*50)
    
    # 创建并运行调度器
    scheduler = create_sample_tasks()
    
    # 运行调度器（前台运行）
    scheduler.run()