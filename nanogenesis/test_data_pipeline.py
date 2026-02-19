#!/usr/bin/env python3
"""
测试数据管道功能
"""

import requests
import json
from bs4 import BeautifulSoup
import csv
from datetime import datetime
import os

def test_news_scraper():
    """测试新闻抓取功能"""
    print("=== 测试新闻抓取功能 ===")
    
    url = "https://news.ycombinator.com"
    
    try:
        # 发送请求
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # 解析HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 提取标题和分数
        headlines = []
        title_elements = soup.select('.titleline > a')
        score_elements = soup.select('.score')
        
        for i, title_elem in enumerate(title_elements[:10]):  # 只取前10个
            headline = {
                'title': title_elem.get_text(strip=True),
                'url': title_elem.get('href', ''),
                'score': score_elements[i].get_text(strip=True) if i < len(score_elements) else '0',
                'timestamp': datetime.now().isoformat()
            }
            headlines.append(headline)
        
        # 保存结果
        output_dir = './data_output'
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, f'hackernews_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(headlines, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 成功抓取 {len(headlines)} 条新闻标题")
        print(f"✓ 数据已保存到: {output_file}")
        
        # 显示前3条结果
        print("\n前3条新闻:")
        for i, item in enumerate(headlines[:3]):
            print(f"  {i+1}. {item['title'][:60]}... (分数: {item['score']})")
        
        return True, output_file, len(headlines)
        
    except Exception as e:
        print(f"✗ 抓取失败: {str(e)}")
        return False, None, 0

def test_mock_api():
    """测试模拟API数据抓取"""
    print("\n=== 测试模拟API数据抓取 ===")
    
    # 使用公开的测试API
    url = "https://jsonplaceholder.typicode.com/posts"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # 提取关键信息
        posts = []
        for item in data[:5]:  # 只取前5个
            post = {
                'id': item['id'],
                'title': item['title'],
                'body': item['body'][:100] + '...' if len(item['body']) > 100 else item['body'],
                'user_id': item['userId']
            }
            posts.append(post)
        
        # 保存为CSV
        output_dir = './data_output'
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, f'posts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['id', 'title', 'body', 'user_id'])
            writer.writeheader()
            writer.writerows(posts)
        
        print(f"✓ 成功抓取 {len(posts)} 条帖子数据")
        print(f"✓ 数据已保存到: {output_file}")
        
        return True, output_file, len(posts)
        
    except Exception as e:
        print(f"✗ API抓取失败: {str(e)}")
        return False, None, 0

def main():
    """主测试函数"""
    print("数据管道服务 - 功能验证测试")
    print("=" * 50)
    
    # 测试1: 新闻抓取
    news_success, news_file, news_count = test_news_scraper()
    
    # 测试2: API数据抓取
    api_success, api_file, api_count = test_mock_api()
    
    # 总结
    print("\n" + "=" * 50)
    print("测试总结:")
    print(f"  新闻抓取: {'✓ 成功' if news_success else '✗ 失败'} ({news_count} 条数据)")
    print(f"  API抓取: {'✓ 成功' if api_success else '✗ 失败'} ({api_count} 条数据)")
    
    total_success = (1 if news_success else 0) + (1 if api_success else 0)
    
    if total_success >= 1:
        print(f"\n✓ 数据管道核心功能验证通过 ({total_success}/2 项测试成功)")
        print("  下一步: 可以开始寻找实际的数据需求场景")
    else:
        print("\n✗ 功能验证失败，需要调试")

if __name__ == "__main__":
    main()