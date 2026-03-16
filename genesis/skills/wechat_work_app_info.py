import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import requests
import json

class WechatWorkAppInfo(Tool):
    @property
    def name(self) -> str:
        return "wechat_work_app_info"
        
    @property
    def description(self) -> str:
        return "获取企业微信应用信息，尝试绕过IP限制"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "corp_id": {"type": "string", "description": "企业ID"},
                "secret": {"type": "string", "description": "应用Secret"},
                "agent_id": {"type": "string", "description": "应用AgentId"}
            },
            "required": ["corp_id", "secret", "agent_id"]
        }
        
    async def execute(self, corp_id: str, secret: str, agent_id: str) -> str:
        results = []
        
        # 1. 获取access_token
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corp_id}&corpsecret={secret}"
        
        try:
            response = requests.get(token_url, timeout=10)
            result = response.json()
            
            if result.get('errcode') == 0:
                access_token = result.get('access_token')
                results.append("✓ access_token获取成功")
                results.append(f"access_token: {access_token[:20]}...")
                
                # 2. 尝试获取应用列表
                results.append("\n=== 尝试获取应用列表 ===")
                list_url = f"https://qyapi.weixin.qq.com/cgi-bin/agent/list?access_token={access_token}"
                
                list_response = requests.get(list_url, timeout=10)
                list_result = list_response.json()
                
                results.append(f"响应状态码: {list_response.status_code}")
                results.append(f"响应内容: {json.dumps(list_result, ensure_ascii=False, indent=2)}")
                
                if list_result.get('errcode') == 0:
                    results.append("\n✓ 应用列表获取成功")
                    apps = list_result.get('agentlist', [])
                    results.append(f"总应用数: {len(apps)}")
                    
                    # 查找指定AgentId的应用
                    target_app = None
                    for app in apps:
                        if str(app.get('agentid')) == agent_id:
                            target_app = app
                            break
                    
                    if target_app:
                        results.append(f"\n✓ 找到AgentId为 {agent_id} 的应用:")
                        results.append(f"   应用名称: {target_app.get('name', '未知')}")
                        results.append(f"   应用ID: {target_app.get('agentid')}")
                        results.append(f"   应用状态: {'已启用' if target_app.get('allow_userinfos', {}).get('user', []) else '未配置用户'}")
                        results.append(f"   应用描述: {target_app.get('description', '无')}")
                    else:
                        results.append(f"\n✗ 未找到AgentId为 {agent_id} 的应用")
                        results.append("可用的应用列表:")
                        for app in apps[:5]:  # 只显示前5个
                            results.append(f"   - {app.get('name')} (AgentId: {app.get('agentid')})")
                        if len(apps) > 5:
                            results.append(f"   ... 还有 {len(apps)-5} 个应用")
                else:
                    results.append(f"\n✗ 应用列表获取失败")
                    results.append(f"错误码: {list_result.get('errcode')}")
                    results.append(f"错误信息: {list_result.get('errmsg')}")
                    
                    # 3. 尝试获取企业信息
                    results.append("\n=== 尝试获取企业信息 ===")
                    corp_info_url = f"https://qyapi.weixin.qq.com/cgi-bin/corp/get?access_token={access_token}"
                    
                    corp_response = requests.get(corp_info_url, timeout=10)
                    corp_result = corp_response.json()
                    
                    results.append(f"响应状态码: {corp_response.status_code}")
                    results.append(f"响应内容: {json.dumps(corp_result, ensure_ascii=False, indent=2)}")
                    
            else:
                results.append("✗ access_token获取失败")
                results.append(f"错误码: {result.get('errcode')}")
                results.append(f"错误信息: {result.get('errmsg')}")
                
        except Exception as e:
            results.append(f"✗ 请求异常: {str(e)}")
        
        return "\n".join(results)