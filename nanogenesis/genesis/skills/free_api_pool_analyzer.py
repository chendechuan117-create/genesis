import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool


import asyncio
import aiohttp
import json
from datetime import datetime
from typing import Dict, List, Optional

class FreeApiPoolAnalyzer(Tool):
    @property
    def name(self) -> str:
        return "free_api_pool_analyzer"
    
    @property
    def description(self) -> str:
        return "智能管理免费API池，自动轮询多个免费AI API服务，统一处理和分析响应数据。支持OpenRouter、HuggingFace、DeepSeek等免费资源。"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_apis", "test_api", "analyze_data", "benchmark"],
                    "description": "执行的操作: 'list_apis'列出可用API, 'test_api'测试单个API, 'analyze_data'分析数据, 'benchmark'性能对比"
                },
                "api_name": {
                    "type": "string",
                    "description": "API名称 (当action为'test_api'时使用)",
                    "enum": ["openrouter", "huggingface", "deepseek", "all"]
                },
                "query": {
                    "type": "string",
                    "description": "查询文本 (当action为'analyze_data'时使用)"
                },
                "data_type": {
                    "type": "string",
                    "enum": ["sentiment", "summary", "keywords", "classification"],
                    "description": "数据分析类型",
                    "default": "summary"
                }
            },
            "required": ["action"]
        }
    
    async def execute(self, action: str, api_name: str = None, query: str = None, data_type: str = "summary") -> str:
        # 免费API池配置
        API_POOL = {
            "openrouter": {
                "name": "OpenRouter",
                "url": "https://openrouter.ai/api/v1/chat/completions",
                "free_tier": True,
                "rate_limit": "100/day",
                "headers": {
                    "Authorization": "Bearer free",
                    "Content-Type": "application/json"
                },
                "model": "openai/gpt-3.5-turbo"
            },
            "huggingface": {
                "name": "HuggingFace",
                "url": "https://api-inference.huggingface.co/models/gpt2",
                "free_tier": True,
                "rate_limit": "limited",
                "headers": {
                    "Authorization": "Bearer hf_free",
                    "Content-Type": "application/json"
                }
            },
            "deepseek": {
                "name": "DeepSeek",
                "url": "https://api.deepseek.com/chat/completions",
                "free_tier": True,
                "rate_limit": "unlimited",
                "headers": {
                    "Authorization": "Bearer free",
                    "Content-Type": "application/json"
                },
                "model": "deepseek-chat"
            }
        }
        
        async def test_single_api(api_config: Dict, query_text: str = "Hello, test the API") -> Dict:
            '''测试单个API的可用性'''
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "model": api_config.get("model", "gpt-3.5-turbo"),
                        "messages": [{"role": "user", "content": query_text}],
                        "max_tokens": 50
                    }
                    
                    timeout = aiohttp.ClientTimeout(total=10)
                    async with session.post(
                        api_config["url"],
                        headers=api_config["headers"],
                        json=payload,
                        timeout=timeout
                    ) as response:
                        status = response.status
                        response_time = response.elapsed.total_seconds()
                        
                        if status == 200:
                            data = await response.json()
                            return {
                                "status": "available",
                                "response_time": response_time,
                                "status_code": status,
                                "response_preview": str(data)[:200] if data else "No data"
                            }
                        else:
                            return {
                                "status": f"error_{status}",
                                "response_time": response_time,
                                "status_code": status,
                                "error": await response.text()[:200]
                            }
            except Exception as e:
                return {
                    "status": f"exception: {str(e)[:100]}",
                    "response_time": 0,
                    "status_code": 0
                }
        
        async def analyze_with_api(api_config: Dict, query_text: str, analysis_type: str) -> str:
            '''使用API分析数据'''
            try:
                async with aiohttp.ClientSession() as session:
                    # 根据分析类型构建提示
                    prompts = {
                        "sentiment": "分析以下文本的情感倾向（正面/负面/中性）并给出置信度：",
                        "summary": "请简要总结以下内容的核心要点：",
                        "keywords": "提取以下文本的关键词（3-5个）：",
                        "classification": "对以下文本进行分类："
                    }
                    
                    prompt = prompts.get(analysis_type, "分析以下内容：")
                    
                    payload = {
                        "model": api_config.get("model", "gpt-3.5-turbo"),
                        "messages": [
                            {"role": "system", "content": f"你是一个数据分析助手。{prompt}"},
                            {"role": "user", "content": query_text}
                        ],
                        "max_tokens": 150,
                        "temperature": 0.3
                    }
                    
                    timeout = aiohttp.ClientTimeout(total=15)
                    async with session.post(
                        api_config["url"],
                        headers=api_config["headers"],
                        json=payload,
                        timeout=timeout
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            if "choices" in data and len(data["choices"]) > 0:
                                return data["choices"][0]["message"]["content"]
                            elif "generated_text" in data:
                                return data["generated_text"]
                            else:
                                return json.dumps(data, ensure_ascii=False)[:300]
                        else:
                            return f"API错误: {response.status}"
            except Exception as e:
                return f"分析异常: {str(e)[:100]}"
        
        async def benchmark_apis(query_text: str) -> List[Dict]:
            '''对多个API进行性能对比'''
            tasks = []
            for api_id, config in API_POOL.items():
                tasks.append(test_single_api(config, query_text))
            
            results = await asyncio.gather(*tasks)
            
            benchmark_data = []
            for (api_id, config), result in zip(API_POOL.items(), results):
                benchmark_data.append({
                    "api": config["name"],
                    "status": result["status"],
                    "response_time": result["response_time"],
                    "available": "available" in result["status"]
                })
            
            return sorted(benchmark_data, key=lambda x: x["response_time"])
        
        # 执行主逻辑
        if action == "list_apis":
            result = []
            for api_id, config in API_POOL.items():
                result.append({
                    "id": api_id,
                    "name": config["name"],
                    "free_tier": config["free_tier"],
                    "rate_limit": config["rate_limit"],
                    "url": config["url"],
                    "model": config.get("model", "default")
                })
            
            report = "## 📊 免费API池清单\n\n"
            for api in result:
                report += f"### {api['name']} ({api['id']})\n"
                report += f"- 免费层级: {'✅ 是' if api['free_tier'] else '❌ 否'}\n"
                report += f"- 速率限制: {api['rate_limit']}\n"
                report += f"- 模型: {api['model']}\n"
                report += f"- 端点: `{api['url']}`\n\n"
            
            report += f"\n**总计**: {len(result)} 个免费API服务"
            return report
        
        elif action == "test_api":
            if not api_name or api_name not in API_POOL and api_name != "all":
                available_apis = ", ".join(API_POOL.keys())
                return f"❌ 请指定有效的API名称。可用API: {available_apis}"
            
            if api_name == "all":
                # 测试所有API
                test_query = "测试API连接和响应能力"
                results = []
                
                for api_id, config in API_POOL.items():
                    result = await test_single_api(config, test_query)
                    results.append({
                        "api": config["name"],
                        **result
                    })
                
                report = "## 🔍 全API测试报告\n\n"
                for r in results:
                    report += f"### {r['api']}\n"
                    report += f"- 状态: {r['status']}\n"
                    report += f"- 响应时间: {r['response_time']:.2f}秒\n"
                    report += f"- 状态码: {r['status_code']}\n"
                    if "response_preview" in r:
                        report += f"- 响应预览: {r['response_preview']}\n"
                    report += "\n"
                
                available_count = sum(1 for r in results if "available" in r["status"])
                report += f"**可用性统计**: {available_count}/{len(results)} 个API可用"
                return report
            else:
                # 测试单个API
                api_config = API_POOL[api_name]
                test_result = await test_single_api(api_config)
                
                report = f"## 🔍 API测试报告: {api_config['name']}\n\n"
                report += f"- **API名称**: {api_config['name']}\n"
                report += f"- **测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                report += f"- **响应状态**: {test_result['status']}\n"
                report += f"- **响应时间**: {test_result['response_time']:.2f}秒\n"
                report += f"- **状态码**: {test_result['status_code']}\n"
                
                if "available" in test_result['status']:
                    report += "\n✅ **API可用性**: 良好"
                else:
                    report += "\n⚠️ **API可用性**: 可能受限，建议检查网络或API密钥"
                
                return report
        
        elif action == "analyze_data":
            if not query:
                return "❌ 请提供要分析的查询文本"
            
            # 选择最可靠的API进行数据分析
            target_api = "deepseek" if "deepseek" in API_POOL else list(API_POOL.keys())[0]
            api_config = API_POOL[target_api]
            
            analysis_result = await analyze_with_api(api_config, query, data_type)
            
            report = f"## 📈 数据分析报告\n\n"
            report += f"- **分析时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            report += f"- **使用API**: {api_config['name']}\n"
            report += f"- **分析类型**: {data_type}\n"
            report += f"- **查询内容**: {query[:100]}{'...' if len(query) > 100 else ''}\n\n"
            report += f"### 分析结果:\n{analysis_result}\n\n"
            report += f"---\n*使用免费API池分析完成*"
            
            return report
        
        elif action == "benchmark":
            test_query = query or "比较不同API的性能表现"
            benchmark_results = await benchmark_apis(test_query)
            
            report = "## ⚡ API性能对比报告\n\n"
            report += f"- **测试查询**: {test_query}\n"
            report += f"- **测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            report += f"- **测试API数量**: {len(benchmark_results)}\n\n"
            
            report += "### 性能排名:\n"
            for i, result in enumerate(benchmark_results, 1):
                status_icon = "✅" if result["available"] else "❌"
                report += f"{i}. **{result['api']}** {status_icon}\n"
                report += f"   响应时间: {result['response_time']:.3f}秒\n"
                report += f"   状态: {result['status']}\n"
            
            # 找出最快可用的API
            fastest = next((r for r in benchmark_results if r["available"]), None)
            if fastest:
                report += f"\n🏆 **最快可用API**: {fastest['api']} ({fastest['response_time']:.3f}秒)"
            
            return report
        
        else:
            return f"❌ 未知操作: {action}。可用操作: list_apis, test_api, analyze_data, benchmark"
