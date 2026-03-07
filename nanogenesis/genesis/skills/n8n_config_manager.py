import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import json
import requests
import subprocess
import os
import sys
from typing import Dict, List, Optional, Any

class N8nConfigManager(Tool):
    @property
    def name(self) -> str:
        return "n8n_config_manager"
        
    @property
    def description(self) -> str:
        return "n8n配置管理器，用于设置API密钥、配置n8n服务和解决连接问题"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["setup_api_key", "check_config", "restart_service", "create_default_key", "test_access", "get_status"],
                    "description": "要执行的操作"
                },
                "api_key": {
                    "type": "string",
                    "description": "API密钥（对于setup_api_key操作）"
                },
                "base_url": {
                    "type": "string",
                    "description": "n8n基础URL",
                    "default": "http://localhost:5678"
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, api_key: Optional[str] = None, 
                     base_url: str = "http://localhost:5678") -> str:
        
        try:
            if action == "setup_api_key":
                return await self._setup_api_key(api_key, base_url)
            elif action == "check_config":
                return await self._check_config(base_url)
            elif action == "restart_service":
                return await self._restart_service()
            elif action == "create_default_key":
                return await self._create_default_key(base_url)
            elif action == "test_access":
                return await self._test_access(base_url)
            elif action == "get_status":
                return await self._get_status(base_url)
            else:
                return f"❌ 不支持的操作: {action}"
                
        except Exception as e:
            return f"❌ 执行失败: {str(e)}"
    
    async def _setup_api_key(self, api_key: str, base_url: str) -> str:
        """设置API密钥到环境变量"""
        if not api_key:
            return "❌ 需要提供api_key参数"
        
        # 设置环境变量
        os.environ['N8N_API_KEY'] = api_key
        
        # 保存到临时文件
        config_dir = os.path.expanduser('~/.n8n')
        os.makedirs(config_dir, exist_ok=True)
        
        config_file = os.path.join(config_dir, 'config.json')
        config = {"api_key": api_key}
        
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        # 测试API密钥
        test_result = await self._test_api_key(api_key, base_url)
        
        result = [
            "✅ API密钥设置完成！",
            f"🔑 密钥: {api_key[:10]}...",
            f"📁 配置文件: {config_file}",
            f"🌐 环境变量: N8N_API_KEY={api_key[:10]}...",
            "",
            "🧪 测试结果:"
        ]
        
        if test_result:
            result.append("✅ API密钥有效！")
        else:
            result.append("❌ API密钥无效或权限不足")
        
        return "\n".join(result)
    
    async def _check_config(self, base_url: str) -> str:
        """检查n8n配置"""
        result = ["🔍 n8n配置检查报告:", "=" * 40]
        
        # 1. 检查服务状态
        try:
            response = requests.get(f"{base_url}/healthz", timeout=5)
            result.append(f"✅ 服务状态: 运行正常 (HTTP {response.status_code})")
        except Exception as e:
            result.append(f"❌ 服务状态: 无法连接 - {str(e)}")
            return "\n".join(result)
        
        # 2. 检查API密钥配置
        api_key = os.environ.get('N8N_API_KEY')
        if api_key:
            result.append(f"✅ 环境变量: N8N_API_KEY已设置 ({api_key[:10]}...)")
        else:
            result.append("❌ 环境变量: N8N_API_KEY未设置")
        
        # 3. 检查配置文件
        config_file = os.path.expanduser('~/.n8n/config.json')
        if os.path.exists(config_file):
            result.append(f"✅ 配置文件: 存在 ({config_file})")
        else:
            result.append(f"❌ 配置文件: 不存在 ({config_file})")
        
        # 4. 测试API访问
        if api_key:
            test_result = await self._test_api_key(api_key, base_url)
            if test_result:
                result.append("✅ API访问: 正常")
            else:
                result.append("❌ API访问: 失败 - 密钥无效或权限不足")
        else:
            result.append("⚠️ API访问: 未测试（缺少API密钥）")
        
        # 5. 检查进程
        try:
            proc_result = subprocess.run(['pgrep', '-f', 'n8n'], 
                                       capture_output=True, text=True)
            if proc_result.returncode == 0:
                pids = proc_result.stdout.strip().split('\n')
                result.append(f"✅ 进程状态: 运行中 (PID: {', '.join(pids)})")
            else:
                result.append("❌ 进程状态: 未找到n8n进程")
        except Exception as e:
            result.append(f"⚠️ 进程检查失败: {str(e)}")
        
        result.append("=" * 40)
        result.append("💡 建议:")
        
        if not api_key:
            result.append("1. 使用 setup_api_key 设置API密钥")
        else:
            result.append("1. API密钥已配置，可以开始使用n8n工作流管理器")
        
        return "\n".join(result)
    
    async def _restart_service(self) -> str:
        """重启n8n服务"""
        try:
            # 查找并杀死n8n进程
            subprocess.run(['pkill', '-f', 'n8n'], capture_output=True)
            
            # 等待进程结束
            import time
            time.sleep(2)
            
            # 启动n8n服务
            # 注意：这里假设n8n是通过systemd或类似方式管理的
            # 如果没有，我们可以尝试直接启动
            
            result = ["🔄 n8n服务重启:"]
            
            # 尝试通过systemd重启
            systemd_result = subprocess.run(['systemctl', '--user', 'restart', 'n8n'], 
                                          capture_output=True, text=True)
            
            if systemd_result.returncode == 0:
                result.append("✅ 通过systemd重启成功")
            else:
                # 尝试直接启动
                result.append("⚠️ systemd重启失败，尝试直接启动")
                
                # 查找n8n可执行文件
                n8n_paths = [
                    '/usr/local/bin/n8n',
                    '/usr/bin/n8n',
                    os.path.expanduser('~/.n8n/node_modules/.bin/n8n')
                ]
                
                n8n_found = False
                for path in n8n_paths:
                    if os.path.exists(path):
                        # 在后台启动n8n
                        import subprocess as sp
                        sp.Popen([path, 'start'], 
                                stdout=subprocess.DEVNULL, 
                                stderr=subprocess.DEVNULL)
                        result.append(f"✅ 直接启动: {path}")
                        n8n_found = True
                        break
                
                if not n8n_found:
                    result.append("❌ 找不到n8n可执行文件")
            
            # 等待服务启动
            time.sleep(5)
            
            # 检查服务状态
            try:
                response = requests.get('http://localhost:5678/healthz', timeout=5)
                if response.status_code == 200:
                    result.append("✅ 服务已启动并运行正常")
                else:
                    result.append(f"⚠️ 服务启动但状态异常: HTTP {response.status_code}")
            except:
                result.append("❌ 服务启动后无法连接")
            
            return "\n".join(result)
            
        except Exception as e:
            return f"❌ 重启服务失败: {str(e)}"
    
    async def _create_default_key(self, base_url: str) -> str:
        """创建默认API密钥（如果n8n允许）"""
        result = ["🔑 创建默认API密钥:"]
        
        # 尝试通过n8n的API创建密钥（如果配置允许）
        try:
            # 首先检查是否已经有API密钥
            test_url = f"{base_url}/api/v1/settings"
            response = requests.get(test_url, timeout=5)
            
            if response.status_code == 200:
                settings = response.json()
                result.append("✅ 可以访问设置API")
                
                # 尝试创建或获取API密钥
                # 注意：实际实现取决于n8n的配置
                result.append("⚠️ 需要手动在Web界面创建API密钥")
                result.append("   1. 访问 http://localhost:5678")
                result.append("   2. 登录n8n")
                result.append("   3. 进入 Settings → API")
                result.append("   4. 点击 'Generate New Key'")
                result.append("   5. 复制生成的密钥")
                
            else:
                result.append(f"❌ 无法访问设置API: HTTP {response.status_code}")
                
        except Exception as e:
            result.append(f"❌ 连接失败: {str(e)}")
        
        result.append("")
        result.append("💡 替代方案：")
        result.append("1. 检查n8n是否运行在无认证模式")
        result.append("2. 查看n8n日志获取更多信息")
        result.append("3. 检查n8n配置文件中的认证设置")
        
        return "\n".join(result)
    
    async def _test_access(self, base_url: str) -> str:
        """测试n8n访问权限"""
        result = ["🧪 n8n访问权限测试:", "=" * 40]
        
        # 测试1: 健康检查
        try:
            response = requests.get(f"{base_url}/healthz", timeout=5)
            result.append(f"✅ 健康检查: HTTP {response.status_code}")
        except Exception as e:
            result.append(f"❌ 健康检查: 失败 - {str(e)}")
            return "\n".join(result)
        
        # 测试2: Web界面
        try:
            response = requests.get(base_url, timeout=5)
            if "n8n" in response.text:
                result.append("✅ Web界面: 可访问")
            else:
                result.append("⚠️ Web界面: 可访问但内容异常")
        except Exception as e:
            result.append(f"❌ Web界面: 无法访问 - {str(e)}")
        
        # 测试3: API访问（无认证）
        try:
            response = requests.get(f"{base_url}/api/v1/workflows", timeout=5)
            if response.status_code == 401:
                result.append("✅ API认证: 已启用（需要API密钥）")
            elif response.status_code == 200:
                result.append("⚠️ API认证: 未启用（无需API密钥）")
            else:
                result.append(f"⚠️ API认证: 状态异常 - HTTP {response.status_code}")
        except Exception as e:
            result.append(f"❌ API测试: 失败 - {str(e)}")
        
        # 测试4: 使用环境变量中的API密钥
        api_key = os.environ.get('N8N_API_KEY')
        if api_key:
            test_result = await self._test_api_key(api_key, base_url)
            if test_result:
                result.append("✅ API密钥测试: 有效")
            else:
                result.append("❌ API密钥测试: 无效")
        else:
            result.append("⚠️ API密钥测试: 未设置环境变量")
        
        result.append("=" * 40)
        return "\n".join(result)
    
    async def _get_status(self, base_url: str) -> str:
        """获取n8n状态报告"""
        result = ["📊 n8n状态报告:", "=" * 50]
        
        # 服务状态
        try:
            response = requests.get(f"{base_url}/healthz", timeout=5)
            result.append(f"🏥 服务健康: ✅ (HTTP {response.status_code})")
        except:
            result.append("🏥 服务健康: ❌ (无法连接)")
            return "\n".join(result)
        
        # 进程信息
        try:
            proc_result = subprocess.run(['ps', 'aux', '|', 'grep', 'n8n', '|', 'grep', '-v', 'grep'], 
                                       shell=True, capture_output=True, text=True)
            if proc_result.stdout:
                lines = proc_result.stdout.strip().split('\n')
                result.append(f"🔄 运行进程: {len(lines)}个")
                for line in lines[:2]:  # 只显示前2个进程
                    parts = line.split()
                    if len(parts) >= 11:
                        pid = parts[1]
                        cpu = parts[2]
                        mem = parts[3]
                        cmd = ' '.join(parts[10:])[:50]
                        result.append(f"   PID {pid}: CPU {cpu}%, MEM {mem}% - {cmd}")
            else:
                result.append("🔄 运行进程: 未找到")
        except:
            result.append("🔄 运行进程: 检查失败")
        
        # 配置状态
        api_key = os.environ.get('N8N_API_KEY')
        config_file = os.path.expanduser('~/.n8n/config.json')
        
        if api_key:
            result.append(f"🔑 API密钥: ✅ 已设置 ({api_key[:10]}...)")
        else:
            result.append("🔑 API密钥: ❌ 未设置")
        
        if os.path.exists(config_file):
            result.append(f"📁 配置文件: ✅ 存在")
        else:
            result.append("📁 配置文件: ❌ 不存在")
        
        # 工作流数量（如果API密钥可用）
        if api_key:
            try:
                headers = {"X-N8N-API-KEY": api_key, "Content-Type": "application/json"}
                response = requests.get(f"{base_url}/api/v1/workflows", 
                                      headers=headers, timeout=5)
                if response.status_code == 200:
                    workflows = response.json().get("data", [])
                    result.append(f"📋 工作流数量: {len(workflows)}个")
                else:
                    result.append(f"📋 工作流数量: ❌ 无法获取 (HTTP {response.status_code})")
            except:
                result.append("📋 工作流数量: ❌ 查询失败")
        else:
            result.append("📋 工作流数量: ⚠️ 需要API密钥")
        
        result.append("=" * 50)
        result.append("💡 下一步:")
        
        if not api_key:
            result.append("1. 使用 setup_api_key 设置API密钥")
            result.append("2. 或访问 http://localhost:5678 生成密钥")
        else:
            result.append("1. 使用 n8n_workflow_manager 管理工作流")
            result.append("2. 使用 n8n_optimizer 优化性能")
        
        return "\n".join(result)
    
    async def _test_api_key(self, api_key: str, base_url: str) -> bool:
        """测试API密钥是否有效"""
        try:
            headers = {
                "Content-Type": "application/json",
                "X-N8N-API-KEY": api_key
            }
            response = requests.get(f"{base_url}/api/v1/workflows", 
                                  headers=headers, timeout=5)
            return response.status_code == 200
        except:
            return False