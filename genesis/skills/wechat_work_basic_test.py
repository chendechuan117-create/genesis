import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import requests
import json
import time

class WechatWorkBasicTest(Tool):
    @property
    def name(self) -> str:
        return "wechat_work_basic_test"
        
    @property
    def description(self) -> str:
        return "企业微信基础功能测试，验证参数有效性"
        
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
        results.append("=== 基础验证测试 ===")
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corp_id}&corpsecret={secret}"
        
        try:
            response = requests.get(token_url, timeout=10)
            result = response.json()
            
            if result.get('errcode') == 0:
                access_token = result.get('access_token')
                expires_in = result.get('expires_in', 7200)
                results.append("✓ access_token获取成功")
                results.append(f"   access_token: {access_token[:20]}...")
                results.append(f"   有效期: {expires_in}秒 ({expires_in/3600:.1f}小时)")
                
                # 2. 测试发送消息（不需要IP白名单的接口）
                results.append("\n=== 消息发送测试 ===")
                message_result = self._test_send_message(access_token, agent_id)
                results.append(message_result)
                
                # 3. 测试获取用户信息（基础接口）
                results.append("\n=== 用户信息测试 ===")
                user_result = self._test_user_info(access_token)
                results.append(user_result)
                
                # 4. 验证access_token的有效性
                results.append("\n=== access_token有效性验证 ===")
                token_valid_result = self._validate_token(access_token)
                results.append(token_valid_result)
                
            else:
                results.append("✗ access_token获取失败")
                results.append(f"   错误码: {result.get('errcode')}")
                results.append(f"   错误信息: {result.get('errmsg')}")
                
        except Exception as e:
            results.append(f"✗ 请求异常: {str(e)}")
        
        return "\n".join(results)
    
    def _test_send_message(self, access_token: str, agent_id: str) -> str:
        """测试发送消息（文本消息）"""
        try:
            url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
            
            # 构建测试消息
            message_data = {
                "touser": "@all",
                "msgtype": "text",
                "agentid": int(agent_id),
                "text": {
                    "content": "企业微信配置验证测试消息\n发送时间: " + time.strftime("%Y-%m-%d %H:%M:%S")
                },
                "safe": 0
            }
            
            response = requests.post(url, json=message_data, timeout=10)
            result = response.json()
            
            if result.get('errcode') == 0:
                return f"✓ 消息发送测试成功\n   消息ID: {result.get('msgid')}"
            elif result.get('errcode') == 60020:
                return f"⚠️ 消息发送测试: IP限制 (错误码: 60020)\n   说明: 参数有效，但需要配置IP白名单"
            elif result.get('errcode') == 60011:
                return f"⚠️ 消息发送测试: 权限不足 (错误码: 60011)\n   说明: AgentId可能没有消息发送权限"
            else:
                return f"⚠️ 消息发送测试: 其他错误\n   错误码: {result.get('errcode')}\n   错误信息: {result.get('errmsg')}"
                
        except Exception as e:
            return f"✗ 消息发送测试异常: {str(e)}"
    
    def _test_user_info(self, access_token: str) -> str:
        """测试获取用户信息"""
        try:
            # 获取部门列表
            dept_url = f"https://qyapi.weixin.qq.com/cgi-bin/department/list?access_token={access_token}"
            dept_response = requests.get(dept_url, timeout=10)
            dept_result = dept_response.json()
            
            if dept_result.get('errcode') == 0:
                departments = dept_result.get('department', [])
                if departments:
                    first_dept_id = departments[0].get('id')
                    # 获取部门成员
                    user_url = f"https://qyapi.weixin.qq.com/cgi-bin/user/list?access_token={access_token}&department_id={first_dept_id}"
                    user_response = requests.get(user_url, timeout=10)
                    user_result = user_response.json()
                    
                    if user_result.get('errcode') == 0:
                        users = user_result.get('userlist', [])
                        return f"✓ 用户信息获取成功\n   部门数: {len(departments)}\n   第一个部门成员数: {len(users)}"
                    else:
                        return f"⚠️ 用户列表获取失败\n   错误码: {user_result.get('errcode')}\n   错误信息: {user_result.get('errmsg')}"
                else:
                    return "⚠️ 无部门信息"
            elif dept_result.get('errcode') == 60020:
                return f"⚠️ 部门信息获取: IP限制 (错误码: 60020)"
            else:
                return f"⚠️ 部门信息获取失败\n   错误码: {dept_result.get('errcode')}\n   错误信息: {dept_result.get('errmsg')}"
                
        except Exception as e:
            return f"✗ 用户信息测试异常: {str(e)}"
    
    def _validate_token(self, access_token: str) -> str:
        """验证access_token有效性"""
        try:
            # 使用获取企业信息的接口验证token
            url = f"https://qyapi.weixin.qq.com/cgi-bin/get_api_domain_ip?access_token={access_token}"
            response = requests.get(url, timeout=10)
            result = response.json()
            
            if result.get('errcode') == 0:
                return f"✓ access_token验证成功\n   API服务器IP: {result.get('ip_list', [])}"
            elif result.get('errcode') == 40014:
                return "✗ access_token已过期"
            else:
                return f"⚠️ access_token验证: {result.get('errmsg')}"
                
        except Exception as e:
            return f"✗ token验证异常: {str(e)}"