import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import json
import re
from datetime import datetime

class WechatWorkFinalReport(Tool):
    @property
    def name(self) -> str:
        return "wechat_work_final_report"
        
    @property
    def description(self) -> str:
        return "生成企业微信配置参数验证的最终报告"
        
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
        report = []
        
        # 报告标题
        report.append("=" * 60)
        report.append("企业微信配置参数验证报告")
        report.append("=" * 60)
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # 1. 参数基本信息
        report.append("一、配置参数基本信息")
        report.append("-" * 40)
        report.append(f"企业ID (CorpId): {corp_id}")
        report.append(f"Secret: {secret[:20]}...{secret[-20:]}")
        report.append(f"AgentId: {agent_id}")
        report.append("")
        
        # 2. 格式验证结果
        report.append("二、格式验证结果")
        report.append("-" * 40)
        
        # Secret格式验证
        secret_valid = self._validate_secret_format(secret)
        report.append("1. Secret格式验证:")
        report.extend([f"   {line}" for line in secret_valid])
        report.append("")
        
        # 企业ID格式验证
        corp_id_valid = self._validate_corp_id_format(corp_id)
        report.append("2. 企业ID格式验证:")
        report.extend([f"   {line}" for line in corp_id_valid])
        report.append("")
        
        # AgentId格式验证
        agent_id_valid = self._validate_agent_id_format(agent_id)
        report.append("3. AgentId格式验证:")
        report.extend([f"   {line}" for line in agent_id_valid])
        report.append("")
        
        # 3. API验证结果
        report.append("三、API验证结果")
        report.append("-" * 40)
        
        # 获取access_token测试
        token_result = await self._test_access_token(corp_id, secret)
        report.append("1. access_token获取测试:")
        report.extend([f"   {line}" for line in token_result])
        report.append("")
        
        # 4. 综合评估
        report.append("四、综合评估与建议")
        report.append("-" * 40)
        
        # 评估参数有效性
        assessment = self._assess_parameters(secret_valid, corp_id_valid, agent_id_valid, token_result)
        report.extend(assessment)
        report.append("")
        
        # 5. 问题与解决方案
        report.append("五、发现的问题与解决方案")
        report.append("-" * 40)
        
        issues = self._identify_issues(secret_valid, corp_id_valid, agent_id_valid, token_result)
        report.extend(issues)
        
        # 6. 最终结论
        report.append("")
        report.append("六、最终结论")
        report.append("-" * 40)
        
        conclusion = self._generate_conclusion(secret_valid, corp_id_valid, agent_id_valid, token_result)
        report.extend(conclusion)
        
        return "\n".join(report)
    
    def _validate_secret_format(self, secret: str) -> list:
        """验证Secret格式"""
        results = []
        
        # 长度检查
        if 32 <= len(secret) <= 64:
            results.append(f"✓ 长度: {len(secret)}字符 (符合32-64字符范围)")
        else:
            results.append(f"✗ 长度: {len(secret)}字符 (不符合32-64字符范围)")
        
        # 字符组成检查
        if re.match(r'^[A-Za-z0-9\-_]+$', secret):
            results.append("✓ 字符组成: 仅包含字母、数字、连字符、下划线")
        else:
            results.append("✗ 字符组成: 包含非法字符")
        
        # 格式检查
        if ' ' in secret:
            results.append("✗ 格式: 包含空格")
        elif secret.startswith('-') or secret.endswith('-'):
            results.append("✗ 格式: 以连字符开头或结尾")
        else:
            results.append("✓ 格式: 符合规范")
        
        return results
    
    def _validate_corp_id_format(self, corp_id: str) -> list:
        """验证企业ID格式"""
        results = []
        
        # 前缀检查
        if corp_id.startswith('ww'):
            results.append("✓ 前缀: 以'ww'开头")
        else:
            results.append("✗ 前缀: 不以'ww'开头")
        
        # 长度检查
        if 8 <= len(corp_id) <= 32:
            results.append(f"✓ 长度: {len(corp_id)}字符 (符合8-32字符范围)")
        else:
            results.append(f"✗ 长度: {len(corp_id)}字符 (不符合8-32字符范围)")
        
        # 字符组成检查
        if re.match(r'^[A-Za-z0-9]+$', corp_id):
            results.append("✓ 字符组成: 仅包含字母和数字")
        else:
            results.append("✗ 字符组成: 包含非法字符")
        
        return results
    
    def _validate_agent_id_format(self, agent_id: str) -> list:
        """验证AgentId格式"""
        results = []
        
        # 数字检查
        if agent_id.isdigit():
            results.append("✓ 格式: 纯数字")
            agent_id_int = int(agent_id)
            
            # 长度检查
            if 1 <= len(agent_id) <= 10:
                results.append(f"✓ 长度: {len(agent_id)}位数字")
            else:
                results.append(f"✗ 长度: {len(agent_id)}位数字 (不符合1-10位范围)")
            
            # 数值范围检查
            if 1 <= agent_id_int <= 10000000:
                results.append(f"✓ 数值范围: {agent_id_int} (符合1-10000000范围)")
            else:
                results.append(f"✗ 数值范围: {agent_id_int} (不符合1-10000000范围)")
        else:
            results.append("✗ 格式: 非纯数字")
        
        return results
    
    async def _test_access_token(self, corp_id: str, secret: str) -> list:
        """测试获取access_token"""
        import requests
        
        results = []
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corp_id}&corpsecret={secret}"
        
        try:
            response = requests.get(token_url, timeout=10)
            result = response.json()
            
            if result.get('errcode') == 0:
                access_token = result.get('access_token')
                expires_in = result.get('expires_in', 7200)
                results.append(f"✓ 获取成功")
                results.append(f"   access_token: {access_token[:20]}...")
                results.append(f"   有效期: {expires_in}秒 ({expires_in/3600:.1f}小时)")
                results.append(f"   说明: Secret参数有效，可以正常获取访问令牌")
            else:
                results.append(f"✗ 获取失败")
                results.append(f"   错误码: {result.get('errcode')}")
                results.append(f"   错误信息: {result.get('errmsg')}")
                
                # 常见错误码解释
                error_explanations = {
                    40001: "Secret错误或已失效",
                    40013: "企业ID无效",
                    41001: "缺少Secret参数",
                    42001: "access_token已过期",
                    44001: "请求包体为空",
                }
                
                errcode = result.get('errcode')
                if errcode in error_explanations:
                    results.append(f"   可能原因: {error_explanations[errcode]}")
                
        except requests.exceptions.Timeout:
            results.append("✗ 请求超时")
            results.append("   可能原因: 网络连接问题或API服务器响应慢")
        except requests.exceptions.ConnectionError:
            results.append("✗ 网络连接错误")
            results.append("   可能原因: 无法连接到企业微信API服务器")
        except Exception as e:
            results.append(f"✗ 请求异常: {str(e)}")
        
        return results
    
    def _assess_parameters(self, secret_valid, corp_id_valid, agent_id_valid, token_result) -> list:
        """综合评估参数"""
        results = []
        
        # 检查格式验证是否全部通过
        format_passed = all(
            line.startswith('✓') for section in [secret_valid, corp_id_valid, agent_id_valid] 
            for line in section
        )
        
        # 检查API验证是否通过
        api_passed = any(line.startswith('✓') for line in token_result)
        
        if format_passed and api_passed:
            results.append("✅ 参数验证通过")
            results.append("   所有参数格式正确，且可以正常获取access_token")
            results.append("   说明: 配置参数基本有效")
        elif format_passed and not api_passed:
            results.append("⚠️ 参数格式正确但API验证失败")
            results.append("   参数格式符合要求，但无法通过API验证")
            results.append("   可能原因: Secret已失效、网络问题或API限制")
        elif not format_passed and api_passed:
            results.append("⚠️ 参数格式有问题但API验证通过")
            results.append("   虽然可以获取access_token，但参数格式不符合规范")
            results.append("   建议: 检查参数格式，可能存在兼容性问题")
        else:
            results.append("❌ 参数验证失败")
            results.append("   参数格式和API验证均未通过")
            results.append("   建议: 重新获取有效的配置参数")
        
        return results
    
    def _identify_issues(self, secret_valid, corp_id_valid, agent_id_valid, token_result) -> list:
        """识别问题并提供解决方案"""
        results = []
        
        # 检查是否有格式问题
        format_issues = []
        for line in secret_valid + corp_id_valid + agent_id_valid:
            if line.startswith('✗'):
                format_issues.append(line)
        
        if format_issues:
            results.append("1. 格式问题:")
            for issue in format_issues:
                results.append(f"   {issue}")
            results.append("   解决方案: 按照企业微信官方文档要求重新获取参数")
            results.append("")
        
        # 检查API问题
        api_issues = []
        for line in token_result:
            if line.startswith('✗') or '错误码: 60020' in line:
                api_issues.append(line)
        
        if api_issues:
            results.append("2. API访问问题:")
            for issue in api_issues:
                if '错误码: 60020' in issue:
                    results.append("   ✗ IP白名单限制 (错误码: 60020)")
                    results.append("      问题: 当前IP不在企业微信的可信IP列表中")
                    results.append("      解决方案:")
                    results.append("      a. 登录企业微信管理后台")
                    results.append("      b. 进入「应用管理」->「自建应用」")
                    results.append("      c. 找到对应应用，配置「企业可信IP」")
                    results.append("      d. 添加当前服务器IP到白名单")
                    results.append("      注意: 如果使用动态IP，建议使用固定IP或VPN")
                elif '错误码: 40001' in issue:
                    results.append("   ✗ Secret无效 (错误码: 40001)")
                    results.append("      问题: Secret可能已过期或被重置")
                    results.append("      解决方案: 重新生成应用的Secret")
                elif '错误码: 40013' in issue:
                    results.append("   ✗ 企业ID无效 (错误码: 40013)")
                    results.append("      问题: 企业ID可能错误")
                    results.append("      解决方案: 确认企业ID是否正确")
        
        if not format_issues and not api_issues:
            results.append("✅ 未发现明显问题")
            results.append("   所有参数格式正确，API访问正常")
        
        return results
    
    def _generate_conclusion(self, secret_valid, corp_id_valid, agent_id_valid, token_result) -> list:
        """生成最终结论"""
        results = []
        
        # 判断格式验证是否全部通过
        format_all_pass = all(
            all(line.startswith('✓') for line in section)
            for section in [secret_valid, corp_id_valid, agent_id_valid]
        )
        
        # 判断API验证是否通过
        api_pass = any('✓ 获取成功' in line for line in token_result)
        
        if format_all_pass and api_pass:
            results.append("✅ 验证结果: 参数有效")
            results.append("")
            results.append("详细说明:")
            results.append("1. 所有参数格式符合企业微信规范")
            results.append("2. Secret有效，可以正常获取access_token")
            results.append("3. 参数可以用于企业微信API调用")
            results.append("")
            results.append("注意事项:")
            results.append("- 需要配置IP白名单才能访问部分API接口")
            results.append("- access_token有效期为2小时，需要定期刷新")
            results.append("- 确保应用已启用并配置了相应权限")
            
        elif format_all_pass and not api_pass:
            results.append("⚠️ 验证结果: 参数格式正确但API访问受限")
            results.append("")
            results.append("详细说明:")
            results.append("1. 参数格式符合规范")
            results.append("2. 但存在API访问限制（通常是IP白名单问题）")
            results.append("")
            results.append("建议:")
            results.append("1. 配置企业可信IP白名单")
            results.append("2. 或使用企业微信提供的其他验证方式")
            
        else:
            results.append("❌ 验证结果: 参数存在问题")
            results.append("")
            results.append("详细说明:")
            results.append("1. 参数格式或API访问存在问题")
            results.append("2. 需要检查并修正配置参数")
            results.append("")
            results.append("建议:")
            results.append("1. 重新获取企业微信配置参数")
            results.append("2. 参考企业微信官方文档检查参数格式")
            results.append("3. 确保应用已正确创建和配置")
        
        return results