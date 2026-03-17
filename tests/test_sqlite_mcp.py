#!/usr/bin/env python3
"""
测试SQLite MCP服务器配置
"""
import subprocess
import time
import os

def test_sqlite_mcp_server():
    """测试SQLite MCP服务器是否能正常启动"""
    print("测试SQLite MCP服务器...")
    
    # 检查数据库文件
    db_path = "/home/chendechusn/Genesis/Genesis/runtime/genesis_v4.db"
    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在: {db_path}")
        return False
    
    print(f"数据库文件存在: {db_path}")
    
    # 检查数据库内容
    try:
        result = subprocess.run(
            ["sqlite3", db_path, "SELECT COUNT(*) FROM test;"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            count = result.stdout.strip()
            print(f"数据库中有 {count} 条测试记录")
        else:
            print(f"查询数据库失败: {result.stderr}")
    except Exception as e:
        print(f"查询数据库时出错: {e}")
    
    # 测试MCP服务器启动
    print("\n测试MCP服务器启动...")
    try:
        # 启动服务器并等待几秒钟
        proc = subprocess.Popen(
            ["/home/chendechusn/.npm-global/bin/mcp-server-sqlite", 
             "--db-path", db_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 等待一会儿让服务器启动
        time.sleep(2)
        
        # 检查进程是否还在运行
        if proc.poll() is None:
            print("✓ MCP服务器成功启动并运行")
            proc.terminate()
            proc.wait(timeout=2)
            return True
        else:
            stdout, stderr = proc.communicate()
            print(f"✗ MCP服务器启动失败")
            print(f"标准输出: {stdout[:200]}")
            print(f"标准错误: {stderr[:200]}")
            return False
            
    except Exception as e:
        print(f"启动MCP服务器时出错: {e}")
        return False

def check_windsurf_config():
    """检查Windsurf MCP配置文件"""
    print("\n检查Windsurf MCP配置文件...")
    config_path = "/home/chendechusn/.codeium/windsurf/mcp_config.json"
    
    if not os.path.exists(config_path):
        print(f"错误: 配置文件不存在: {config_path}")
        return False
    
    print(f"配置文件存在: {config_path}")
    
    try:
        with open(config_path, 'r') as f:
            content = f.read()
            if '"sqlite"' in content and 'genesis_v4.db' in content:
                print("✓ SQLite MCP配置已正确添加")
                return True
            else:
                print("✗ SQLite MCP配置未找到或配置不正确")
                return False
    except Exception as e:
        print(f"读取配置文件时出错: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("SQLite MCP服务器配置测试")
    print("=" * 50)
    
    config_ok = check_windsurf_config()
    server_ok = test_sqlite_mcp_server()
    
    print("\n" + "=" * 50)
    print("测试结果:")
    print(f"配置文件检查: {'通过' if config_ok else '失败'}")
    print(f"服务器测试: {'通过' if server_ok else '失败'}")
    
    if config_ok and server_ok:
        print("\n✓ 所有测试通过！SQLite MCP服务器已成功配置。")
        print("现在可以在Windsurf中使用SQLite MCP功能了。")
    else:
        print("\n✗ 测试失败，请检查配置。")