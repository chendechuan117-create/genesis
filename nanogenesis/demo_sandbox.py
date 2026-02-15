
import sys
import asyncio
import logging
from pathlib import Path

# 添加 nanabot 路径
# 添加路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nanogenesis.tools.shell_tool import ShellTool

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("demo_sandbox")

async def main():
    print("🛡️ NanoGenesis Docker 沙箱安全演示")
    print("=" * 60)

    # 1. 初始化带沙箱的 Shell 工具
    workspace = str(Path.cwd() / "sandbox_workspace")
    print(f"初始化沙箱工具 (工作目录: {workspace})...")
    
    # 创建工作目录
    Path(workspace).mkdir(parents=True, exist_ok=True)
    
    tool = ShellTool(use_sandbox=True, workspace_path=workspace)
    
    # 2. 检查环境 (证明是在 Docker 里)
    print("\n[测试 1] 检查操作系统版本")
    print("-" * 60)
    result = await tool.execute("cat /etc/os-release")
    print(result)
    
    # 3. 检查文件系统隔离
    print("\n[测试 2] 检查文件系统隔离 (应该看不到宿主机的敏感文件)")
    print("-" * 60)
    # 尝试读取宿主机的 /etc/shadow (如果成功则说明隔离失败，如果是在容器里则只能看到容器的)
    result = await tool.execute("ls -la /etc/shadow") 
    print(result)
    
    # 4. 测试写入文件
    print("\n[测试 3] 测试文件写入与持久化")
    print("-" * 60)
    await tool.execute("echo 'Hello from NanoGenesis Sandbox!' > test.txt")
    result = await tool.execute("cat test.txt")
    print(result)
    
    # 验证宿主机是否能看到该文件
    host_file = Path(workspace) / "test.txt"
    if host_file.exists():
        print(f"\n[验证] 宿主机路径 {host_file} 存在文件: ✅")
        print(f"内容: {host_file.read_text().strip()}")
    else:
        print(f"\n[验证] 宿主机路径 {host_file} 不存在文件: ❌")

    print("\n" + "=" * 60)
    print("✅ 沙箱演示完成")

if __name__ == "__main__":
    asyncio.run(main())
