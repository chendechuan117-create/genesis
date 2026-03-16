#!/usr/bin/env python3
"""
OpenClaw API资源测试脚本
用于测试各种免费API的可用性和响应速度
"""

import requests
import json
import time
from typing import Dict, List, Optional

class OpenClawAPITester:
    """OpenClaw API测试器"""
    
    def __init__(self):
        self.results = []
        
    def test_openrouter(self, api_key: str) -> Dict:
        """测试OpenRouter API"""
        print("测试 OpenRouter API...")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "openrouter/auto",
            "messages": [
                {"role": "user", "content": "Hello, how are you?"}
            ],
            "max_tokens": 50
        }
        
        try:
            start_time = time.time()
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            elapsed_time = time.time() - start_time
            
            if response.status_code == 200:
                result = {
                    "platform": "OpenRouter",
                    "status": "success",
                    "response_time": round(elapsed_time, 2),
                    "model": response.json().get("model", "unknown"),
                    "tokens_used": response.json().get("usage", {}).get("total_tokens", 0)
                }
                print(f"✓ OpenRouter 测试成功 - 响应时间: {elapsed_time:.2f}s")
            else:
                result = {
                    "platform": "OpenRouter",
                    "status": "error",
                    "error_code": response.status_code,
                    "error_message": response.text[:100]
                }
                print(f"✗ OpenRouter 测试失败 - 错误码: {response.status_code}")
                
        except Exception as e:
            result = {
                "platform": "OpenRouter",
                "status": "exception",
                "error_message": str(e)
            }
            print(f"✗ OpenRouter 测试异常 - {e}")
            
        return result
    
    def test_bailian_compatibility(self, api_key: str) -> Dict:
        """测试阿里云百炼兼容性API"""
        print("测试 阿里云百炼 API...")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "qwen-turbo",
            "messages": [
                {"role": "user", "content": "你好"}
            ],
            "max_tokens": 50
        }
        
        try:
            start_time = time.time()
            response = requests.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            elapsed_time = time.time() - start_time
            
            if response.status_code == 200:
                result = {
                    "platform": "阿里云百炼",
                    "status": "success",
                    "response_time": round(elapsed_time, 2),
                    "model": response.json().get("model", "unknown")
                }
                print(f"✓ 阿里云百炼 测试成功 - 响应时间: {elapsed_time:.2f}s")
            else:
                result = {
                    "platform": "阿里云百炼",
                    "status": "error",
                    "error_code": response.status_code,
                    "error_message": response.text[:100]
                }
                print(f"✗ 阿里云百炼 测试失败 - 错误码: {response.status_code}")
                
        except Exception as e:
            result = {
                "platform": "阿里云百炼",
                "status": "exception",
                "error_message": str(e)
            }
            print(f"✗ 阿里云百炼 测试异常 - {e}")
            
        return result
    
    def test_openai_compatible_endpoint(self, base_url: str, api_key: str, model: str = "gpt-3.5-turbo") -> Dict:
        """测试OpenAI兼容端点"""
        print(f"测试 OpenAI兼容端点: {base_url}...")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": "Test message"}
            ],
            "max_tokens": 20
        }
        
        try:
            start_time = time.time()
            response = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            elapsed_time = time.time() - start_time
            
            if response.status_code == 200:
                result = {
                    "platform": "OpenAI兼容端点",
                    "status": "success",
                    "response_time": round(elapsed_time, 2),
                    "endpoint": base_url,
                    "model": response.json().get("model", model)
                }
                print(f"✓ {base_url} 测试成功 - 响应时间: {elapsed_time:.2f}s")
            else:
                result = {
                    "platform": "OpenAI兼容端点",
                    "status": "error",
                    "endpoint": base_url,
                    "error_code": response.status_code,
                    "error_message": response.text[:100]
                }
                print(f"✗ {base_url} 测试失败 - 错误码: {response.status_code}")
                
        except Exception as e:
            result = {
                "platform": "OpenAI兼容端点",
                "status": "exception",
                "endpoint": base_url,
                "error_message": str(e)
            }
            print(f"✗ {base_url} 测试异常 - {e}")
            
        return result
    
    def run_all_tests(self, config: Dict):
        """运行所有测试"""
        print("=" * 50)
        print("OpenClaw API资源测试开始")
        print("=" * 50)
        
        # 测试OpenRouter
        if config.get("openrouter_api_key"):
            result = self.test_openrouter(config["openrouter_api_key"])
            self.results.append(result)
        
        # 测试阿里云百炼
        if config.get("bailian_api_key"):
            result = self.test_bailian_compatibility(config["bailian_api_key"])
            self.results.append(result)
        
        # 测试其他OpenAI兼容端点
        for endpoint_config in config.get("other_endpoints", []):
            result = self.test_openai_compatible_endpoint(
                endpoint_config["base_url"],
                endpoint_config["api_key"],
                endpoint_config.get("model", "gpt-3.5-turbo")
            )
            self.results.append(result)
        
        # 输出测试报告
        self.generate_report()
    
    def generate_report(self):
        """生成测试报告"""
        print("\n" + "=" * 50)
        print("API测试报告")
        print("=" * 50)
        
        successful = 0
        failed = 0
        
        for result in self.results:
            if result["status"] == "success":
                successful += 1
                print(f"✓ {result['platform']}: 成功 (响应时间: {result.get('response_time', 'N/A')}s)")
            else:
                failed += 1
                print(f"✗ {result['platform']}: 失败 - {result.get('error_message', '未知错误')}")
        
        print(f"\n总计: {len(self.results)} 个API测试")
        print(f"成功: {successful}")
        print(f"失败: {failed}")
        
        # 保存报告到文件
        report_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_tests": len(self.results),
            "successful": successful,
            "failed": failed,
            "results": self.results
        }
        
        with open("api_test_report.json", "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n详细报告已保存到: api_test_report.json")

def main():
    """主函数"""
    # 配置API密钥（请替换为实际的API密钥）
    config = {
        # OpenRouter API密钥（从 https://openrouter.ai 获取）
        "openrouter_api_key": "sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        
        # 阿里云百炼API密钥（从阿里云控制台获取）
        "bailian_api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        
        # 其他OpenAI兼容端点
        "other_endpoints": [
            {
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "model": "gpt-3.5-turbo"
            },
            # 可以添加更多端点
        ]
    }
    
    # 创建测试器并运行测试
    tester = OpenClawAPITester()
    
    # 检查是否有配置API密钥
    has_configured_keys = any([
        config.get("openrouter_api_key") and not config["openrouter_api_key"].startswith("sk-or-v1-xxxx"),
        config.get("bailian_api_key") and not config["bailian_api_key"].startswith("sk-xxxx"),
        len(config.get("other_endpoints", [])) > 0
    ])
    
    if not has_configured_keys:
        print("⚠️  警告：未配置有效的API密钥")
        print("请编辑此脚本，将示例API密钥替换为实际的API密钥")
        print("\n如何获取API密钥：")
        print("1. OpenRouter: https://openrouter.ai")
        print("2. 阿里云百炼: https://www.aliyun.com/product/ai/bailian")
        print("3. 其他平台: 参考调研报告中的获取方式")
        return
    
    tester.run_all_tests(config)

if __name__ == "__main__":
    main()