import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import requests
import json
import re
from typing import Dict, Any, Tuple

class WechatWorkValidator(Tool):
    @property
    def name(self) -> str:
        return "wechat_work_validator"
        
    @property
    def description(self) -> str:
        return "验证企业微信配置参数（企业ID、Secret、AgentId）的有效性"
        
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
        
        # 1. 验证Secret格式
        results.append("=== Secret格式验证 ===")
        secret_validation = self._validate_secret(secret)
        results.append(secret_validation)
        
        # 2. 验证企业ID格式
        results.append("\n=== 企业ID格式验证 ===")
        corp_id_validation = self._validate_corp_id(corp_id)
        results.append(corp_id_validation)
        
        # 3. 验证AgentId格式
        results.append("\n=== AgentId格式验证 ===")
        agent_id_validation = self._validate_agent_id(agent_id)
        results.append(agent_id_validation)
        
        # 4. API验证
        results.append("\n=== API验证 ===")
        api_results = await self._validate_api(corp_id, secret, agent_id)
        results.append(api_results)
        
        return "\n".join(results)
    
    def _validate_secret(self, secret: str) -> str:
        """验证Secret格式"""
        lines = []
        lines.append(f"Secret值: {secret}")
        lines.append(f"长度: {len(secret)} 字符")
        
        # 检查长度
        if 32 <= len(secret) <= 64:
            lines.append("✓ 长度检查: 通过 (32-64字符)")
        else:
            lines.append(f"✗ 长度检查: 失败 (当前长度: {len(secret)}字符)")
        
        # 检查字符组成
        if re.match(r'^[A-Za-z0-9\-_]+$', secret):
            lines.append("✓ 字符组成: 通过 (仅包含字母、数字、连字符、下划线)")
        else:
            lines.append("✗ 字符组成: 失败 (包含非法字符)")
        
        # 检查是否有明显的格式问题
        if ' ' in secret:
            lines.append("✗ 格式检查: 失败 (包含空格)")
        elif secret.startswith('-') or secret.endswith('-'):
            lines.append("✗ 格式检查: 失败 (以连字符开头或结尾)")
        else:
            lines.append("✓ 格式检查: 通过")
        
        return "\n".join(lines)
    
    def _validate_corp_id(self, corp_id: str) -> str:
        """验证企业ID格式"""
        lines = []
        lines.append(f"企业ID值: {corp_id}")
        lines.append(f"长度: {len(corp_id)} 字符")
        
        # 检查是否以"ww"开头
        if corp_id.startswith('ww'):
            lines.append("✓ 前缀检查: 通过 (以'ww'开头)")
        else:
            lines.append("✗ 前缀检查: 失败 (不以'ww'开头)")
        
        # 检查长度
        if 8 <= len(corp_id) <= 32:
            lines.append("✓ 长度检查: 通过 (8-32字符)")
        else:
            lines.append(f"✗ 长度检查: 失败 (当前长度: {len(corp_id)}字符)")
        
        # 检查字符组成
        if re.match(r'^[A-Za-z0-9]+$', corp_id):
            lines.append("✓ 字符组成: 通过 (仅包含字母和数字)")
        else:
            lines.append("✗ 字符组成: 失败 (包含非法字符)")
        
        return "\n".join(lines)
    
    def _validate_agent_id(self, agent_id: str) -> str:
        """验证AgentId格式"""
        lines = []
        lines.append(f"AgentId值: {agent_id}")
        
        # 检查是否为数字
        if agent_id.isdigit():
            lines.append("✓ 数字检查: 通过 (纯数字)")
            agent_id_int = int(agent_id)
            
            # 检查长度
            if 1 <= len(agent_id) <= 10:
                lines.append("✓ 长度检查: 通过 (1-10位数字)")
            else:
                lines.append(f"✗ 长度检查: 失败 (当前长度: {len(agent_id)}位)")
            
            # 检查数值范围
            if 1 <= agent_id_int <= 10000000:
                lines.append("✓ 数值范围: 通过 (1-10000000)")
            else:
                lines.append(f"✗ 数值范围: 失败 (当前值: {agent_id_int})")
        else:
            lines.append("✗ 数字检查: 失败 (非纯数字)")
        
        return "\n".join(lines)
    
    async def _validate_api(self, corp_id: str, secret: str, agent_id: str) -> str:
        """通过API验证参数"""
        lines = []
        
        # 1. 获取access_token
        lines.append("1. 获取access_token:")
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corp_id}&corpsecret={secret}"
        
        try:
            response = requests.get(token_url, timeout=10)
            result = response.json()
            
            lines.append(f"   请求URL: {token_url}")
            lines.append(f"   响应状态码: {response.status_code}")
            lines.append(f"   响应内容: {json.dumps(result, ensure_ascii=False)}")
            
            if result.get('errcode') == 0:
                access_token = result.get('access_token')
                lines.append(f"   ✓ 获取access_token成功")
                lines.append(f"   access_token: {access_token[:20]}...")
                
                # 2. 验证AgentId对应的应用
                lines.append("\n2. 验证AgentId对应的应用:")
                app_url = f"https://qyapi.weixin.qq.com/cgi-bin/agent/get?access_token={access_token}&agentid={agent_id}"
                
                app_response = requests.get(app_url, timeout=10)
                app_result = app_response.json()
                
                lines.append(f"   请求URL: {app_url}")
                lines.append(f"   响应状态码: {app_response.status_code}")
                lines.append(f"   响应内容: {json.dumps(app_result, ensure_ascii=False)}")
                
                if app_result.get('errcode') == 0:
                    lines.append(f"   ✓ AgentId验证成功")
                    lines.append(f"   应用名称: {app_result.get('name', '未知')}")
                    lines.append(f"   应用状态: {'已启用' if app_result.get('allow_userinfos', {}).get('user', []) else '未配置用户'}")
                else:
                    lines.append(f"   ✗ AgentId验证失败")
                    lines.append(f"   错误码: {app_result.get('errcode')}")
                    lines.append(f"   错误信息: {app_result.get('errmsg')}")
                    
            else:
                lines.append(f"   ✗ 获取access_token失败")
                lines.append(f"   错误码: {result.get('errcode')}")
                lines.append(f"   错误信息: {result.get('errmsg')}")
                
        except requests.exceptions.Timeout:
            lines.append("   ✗ 请求超时")
        except requests.exceptions.ConnectionError:
            lines.append("   ✗ 网络连接错误")
        except Exception as e:
            lines.append(f"   ✗ 请求异常: {str(e)}")
        
        return "\n".join(lines)