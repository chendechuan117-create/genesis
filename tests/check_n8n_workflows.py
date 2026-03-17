#!/usr/bin/env python3
import sqlite3
import json
import sys

def check_n8n_database(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 列出所有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print("数据库中的表:")
        for table in tables:
            print(f"  - {table[0]}")
        
        # 检查工作流相关表
        workflow_tables = [table[0] for table in tables if 'workflow' in table[0].lower()]
        print("\n工作流相关表:")
        for table in workflow_tables:
            print(f"  - {table}")
            
            # 查看表结构
            cursor.execute(f"PRAGMA table_info({table});")
            columns = cursor.fetchall()
            print(f"    表结构: {[col[1] for col in columns]}")
            
            # 查看数据量
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            print(f"    记录数: {count}")
            
            # 如果是workflow_entity表，查看具体内容
            if table == 'workflow_entity':
                cursor.execute("SELECT id, name, active FROM workflow_entity LIMIT 10;")
                workflows = cursor.fetchall()
                print("\n    工作流列表 (前10个):")
                for wf in workflows:
                    print(f"      ID: {wf[0]}, 名称: {wf[1]}, 激活状态: {wf[2]}")
                    
                    # 获取工作流详细配置
                    cursor.execute("SELECT nodes FROM workflow_entity WHERE id = ?;", (wf[0],))
                    nodes_data = cursor.fetchone()
                    if nodes_data and nodes_data[0]:
                        try:
                            nodes = json.loads(nodes_data[0])
                            print(f"      节点数: {len(nodes)}")
                            # 检查是否有早报相关关键词
                            keywords = ['newsletter', '早报', 'news', 'rss', 'email', 'summary', '摘要', 'ai', 'chatgpt']
                            wf_name = wf[1].lower()
                            if any(keyword in wf_name for keyword in keywords):
                                print(f"      ⭐ 发现早报相关工作流: {wf[1]}")
                                # 显示节点类型
                                node_types = set()
                                for node in nodes:
                                    if 'type' in node:
                                        node_types.add(node['type'])
                                print(f"      使用的节点类型: {node_types}")
                        except json.JSONDecodeError:
                            pass
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"错误: {e}")
        return False

if __name__ == "__main__":
    db_path = "/home/node/.n8n/database.sqlite"
    print(f"检查n8n数据库: {db_path}")
    check_n8n_database(db_path)