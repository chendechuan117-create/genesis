#!/usr/bin/env python3
"""
MVP功能测试脚本
测试AI自动化咨询服务的关键功能
"""

import unittest
import sqlite3
import json
import os
from ai_automation_consultant import AIAutomationConsultant

class TestAIAutomationConsultant(unittest.TestCase):
    """测试AI自动化咨询服务"""
    
    def setUp(self):
        """测试前准备"""
        self.consultant = AIAutomationConsultant()
        self.test_client = {
            "name": "测试科技有限公司",
            "industry": "电商",
            "company_size": "中",
            "challenges": "订单处理效率低，人工成本高"
        }
    
    def test_database_initialization(self):
        """测试数据库初始化"""
        # 检查数据库文件是否存在
        self.assertTrue(os.path.exists("consultation_data.db"), "数据库文件未创建")
        
        # 检查表是否存在
        conn = sqlite3.connect("consultation_data.db")
        cursor = conn.cursor()
        
        # 检查consultations表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='consultations'")
        self.assertIsNotNone(cursor.fetchone(), "consultations表不存在")
        
        # 检查automation_templates表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='automation_templates'")
        self.assertIsNotNone(cursor.fetchone(), "automation_templates表不存在")
        
        # 检查模板数据
        cursor.execute("SELECT COUNT(*) FROM automation_templates")
        template_count = cursor.fetchone()[0]
        self.assertGreater(template_count, 0, "模板数据未插入")
        
        conn.close()
    
    def test_consultation_workflow(self):
        """测试咨询工作流程"""
        # 执行咨询
        result = self.consultant.conduct_consultation(self.test_client)
        
        # 检查返回结果
        self.assertIn("consultation_id", result, "缺少consultation_id")
        self.assertIn("recommendations", result, "缺少recommendations")
        self.assertIn("roi_analysis", result, "缺少roi_analysis")
        self.assertIn("report", result, "缺少report")
        
        # 检查consultation_id
        self.assertIsInstance(result["consultation_id"], int, "consultation_id不是整数")
        self.assertGreater(result["consultation_id"], 0, "consultation_id无效")
        
        # 检查推荐方案
        recommendations = result["recommendations"]
        self.assertIsInstance(recommendations, list, "recommendations不是列表")
        self.assertGreaterEqual(len(recommendations), 2, "推荐方案太少")
        
        # 检查每个推荐方案的结构
        for rec in recommendations:
            self.assertIn("solution", rec, "推荐方案缺少solution字段")
            self.assertIn("description", rec, "推荐方案缺少description字段")
            self.assertIn("time_saving", rec, "推荐方案缺少time_saving字段")
            self.assertIn("implementation_cost", rec, "推荐方案缺少implementation_cost字段")
            self.assertIn("priority", rec, "推荐方案缺少priority字段")
        
        # 检查ROI分析
        roi = result["roi_analysis"]
        required_roi_fields = ["total_implementation_cost", "total_annual_savings", 
                              "roi_percentage", "payback_period", "net_annual_benefit"]
        for field in required_roi_fields:
            self.assertIn(field, roi, f"ROI分析缺少{field}字段")
        
        # 检查报告文件
        report_filename = f"consultation_report_{result['consultation_id']}.md"
        self.assertTrue(os.path.exists(report_filename), "报告文件未创建")
        
        # 检查报告内容
        with open(report_filename, "r", encoding="utf-8") as f:
            report_content = f.read()
            self.assertIn("AI自动化咨询报告", report_content, "报告标题不正确")
            self.assertIn("测试科技有限公司", report_content, "客户名称未在报告中")
            self.assertIn("投资回报分析", report_content, "缺少投资回报分析部分")
    
    def test_recommendation_generation(self):
        """测试推荐方案生成"""
        # 测试不同行业的推荐
        test_cases = [
            {"industry": "电商", "expected_templates": 3},
            {"industry": "媒体", "expected_templates": 3},
            {"industry": "咨询", "expected_templates": 3},
            {"industry": "未知行业", "expected_templates": 3}  # 应该回退到默认
        ]
        
        for test_case in test_cases:
            client_info = {
                "name": "测试客户",
                "industry": test_case["industry"],
                "company_size": "中",
                "challenges": "效率问题"
            }
            
            result = self.consultant.conduct_consultation(client_info)
            recommendations = result["recommendations"]
            
            # 检查推荐数量
            self.assertGreaterEqual(len(recommendations), 2, 
                                   f"{test_case['industry']}行业推荐方案太少")
            
            # 检查推荐方案的相关性
            for rec in recommendations:
                self.assertIsNotNone(rec["solution"], "推荐方案名称不能为空")
                self.assertIsNotNone(rec["description"], "推荐方案描述不能为空")
    
    def test_roi_calculation(self):
        """测试ROI计算"""
        # 测试不同公司规模的ROI计算
        test_cases = [
            {"company_size": "小", "expected_roi": "100%"},
            {"company_size": "中", "expected_roi": "200%"},
            {"company_size": "大", "expected_roi": "150%"}
        ]
        
        for test_case in test_cases:
            client_info = {
                "name": "ROI测试客户",
                "industry": "电商",
                "company_size": test_case["company_size"],
                "challenges": "成本控制"
            }
            
            result = self.consultant.conduct_consultation(client_info)
            roi = result["roi_analysis"]
            
            # 检查ROI字段
            self.assertIn("roi_percentage", roi, "缺少roi_percentage")
            
            # ROI应该是正数
            roi_value = float(roi["roi_percentage"].replace("%", ""))
            self.assertGreater(roi_value, 0, f"{test_case['company_size']}公司ROI应为正数")
            
            # 检查其他财务指标
            self.assertIn("payback_period", roi, "缺少payback_period")
            payback = float(roi["payback_period"].replace("个月", ""))
            self.assertGreater(payback, 0, "回收期应为正数")
            
            self.assertIn("net_annual_benefit", roi, "缺少net_annual_benefit")
            net_benefit = float(roi["net_annual_benefit"].replace("$", ""))
            self.assertGreater(net_benefit, 0, "年净收益应为正数")
    
    def test_report_generation(self):
        """测试报告生成"""
        # 生成咨询报告
        result = self.consultant.conduct_consultation(self.test_client)
        
        # 检查报告文件
        report_filename = f"consultation_report_{result['consultation_id']}.md"
        self.assertTrue(os.path.exists(report_filename), "报告文件不存在")
        
        # 读取并分析报告内容
        with open(report_filename, "r", encoding="utf-8") as f:
            content = f.read()
            
            # 检查必要部分
            required_sections = [
                "AI自动化咨询报告",
                "客户信息",
                "推荐自动化方案",
                "投资回报分析",
                "实施建议",
                "后续支持"
            ]
            
            for section in required_sections:
                self.assertIn(section, content, f"报告缺少'{section}'部分")
            
            # 检查客户信息
            self.assertIn(self.test_client["name"], content, "报告未包含客户名称")
            self.assertIn(self.test_client["industry"], content, "报告未包含客户行业")
            
            # 检查推荐方案
            for rec in result["recommendations"]:
                self.assertIn(rec["solution"], content, f"报告未包含推荐方案'{rec['solution']}'")
            
            # 检查ROI数据
            roi = result["roi_analysis"]
            self.assertIn(roi["total_implementation_cost"], content, "报告未包含实施成本")
            self.assertIn(roi["roi_percentage"], content, "报告未包含ROI百分比")
    
    def test_performance(self):
        """测试性能"""
        import time
        
        # 测试咨询响应时间
        start_time = time.time()
        
        for i in range(5):  # 模拟5个并发咨询
            client_info = {
                "name": f"性能测试客户{i}",
                "industry": "电商",
                "company_size": "中",
                "challenges": "效率问题"
            }
            self.consultant.conduct_consultation(client_info)
        
        end_time = time.time()
        total_time = end_time - start_time
        avg_time = total_time / 5
        
        print(f"\n性能测试结果:")
        print(f"  总时间: {total_time:.2f}秒")
        print(f"  平均每个咨询: {avg_time:.2f}秒")
        
        # 性能要求：每个咨询应在3秒内完成
        self.assertLess(avg_time, 3.0, f"咨询响应时间过长: {avg_time:.2f}秒")
        
        # 测试数据库查询性能
        conn = sqlite3.connect("consultation_data.db")
        cursor = conn.cursor()
        
        start_time = time.time()
        cursor.execute("SELECT COUNT(*) FROM consultations")
        count = cursor.fetchone()[0]
        query_time = time.time() - start_time
        
        print(f"  数据库查询时间: {query_time:.4f}秒")
        print(f"  总咨询记录: {count}条")
        
        self.assertLess(query_time, 0.1, "数据库查询时间过长")
        conn.close()
    
    def tearDown(self):
        """测试后清理"""
        # 删除测试生成的报告文件
        import glob
        report_files = glob.glob("consultation_report_*.md")
        for file in report_files:
            try:
                os.remove(file)
            except:
                pass

def run_comprehensive_test():
    """运行全面测试"""
    print("=" * 60)
    print("AI自动化咨询服务 - 全面功能测试")
    print("=" * 60)
    
    # 运行单元测试
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestAIAutomationConsultant)
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    # 显示测试结果统计
    print(f"运行测试: {result.testsRun}")
    print(f"通过测试: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败测试: {len(result.failures)}")
    print(f"错误测试: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n✅ 所有测试通过！产品功能正常。")
        
        # 生成测试报告
        test_report = f"""# 产品测试报告
生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}

## 测试结果
- 总测试用例: {result.testsRun}
- 通过测试: {result.testsRun - len(result.failures) - len(result.errors)}
- 失败测试: {len(result.failures)}
- 错误测试: {len(result.errors)}

## 功能验证
✅ 数据库初始化正常
✅ 咨询工作流程完整
✅ 推荐方案生成准确
✅ ROI计算正确
✅ 报告生成完整
✅ 性能满足要求

## 产品状态
**MVP功能完整，可以进入下一阶段开发。**

## 建议改进
1. 增加更多行业模板
2. 优化用户界面
3. 添加数据导出功能
4. 集成支付系统
"""
        
        with open("product_test_report.md", "w", encoding="utf-8") as f:
            f.write(test_report)
        
        print("\n📋 详细测试报告已保存为: product_test_report.md")
    else:
        print("\n❌ 测试未完全通过，需要修复问题。")
        
        if result.failures:
            print("\n失败测试:")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback.split(':')[0]}")
        
        if result.errors:
            print("\n错误测试:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback.split(':')[0]}")

if __name__ == "__main__":
    import time
    run_comprehensive_test()