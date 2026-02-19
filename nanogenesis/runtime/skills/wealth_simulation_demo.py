import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

from typing import Dict, Any
import random
from datetime import datetime

class WealthSimulationDemo:
    """财富模拟演示工具 - 展示AI在数字世界中的分析与规划能力"""
    
    def __init__(self):
        self.name = "wealth_simulation_demo"
        self.description = "模拟商业概念分析，展示AI的数字规划能力"
        self.parameters = {
            "business_concept": "str: 商业概念描述，如'卖柠檬水'、'在线课程'、'电商店铺'"
        }
    
    def execute(self, business_concept: str) -> Dict[str, Any]:
        """执行商业概念分析模拟"""
        
        # 模拟数据生成
        concept = business_concept.lower()
        
        # 根据概念类型生成不同的模拟数据
        if "柠檬水" in concept or "饮料" in concept:
            return self._lemonade_stand_simulation()
        elif "课程" in concept or "教育" in concept:
            return self._online_course_simulation()
        elif "电商" in concept or "店铺" in concept:
            return self._ecommerce_simulation()
        else:
            return self._generic_business_simulation(concept)
    
    def _lemonade_stand_simulation(self) -> Dict[str, Any]:
        """柠檬水摊模拟"""
        base_customers = random.randint(50, 150)
        weather_factor = random.uniform(0.7, 1.3)
        price_per_cup = 2.5
        cost_per_cup = 0.8
        
        daily_customers = int(base_customers * weather_factor)
        daily_revenue = daily_customers * price_per_cup
        daily_cost = daily_customers * cost_per_cup
        daily_profit = daily_revenue - daily_cost
        
        return {
            "business_type": "柠檬水摊",
            "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "simulation_results": {
                "daily_customers": daily_customers,
                "price_per_unit": price_per_cup,
                "cost_per_unit": cost_per_cup,
                "daily_revenue": round(daily_revenue, 2),
                "daily_cost": round(daily_cost, 2),
                "daily_profit": round(daily_profit, 2),
                "monthly_profit": round(daily_profit * 30, 2),
                "profit_margin": round((daily_profit / daily_revenue) * 100, 1)
            },
            "key_insights": [
                "天气对销量影响显著（±30%）",
                "建议增加附加产品（如饼干）提高客单价",
                "周末销量通常是工作日的1.5倍"
            ],
            "ai_capabilities_demonstrated": [
                "市场数据分析",
                "财务模型构建",
                "盈利预测",
                "业务优化建议"
            ]
        }
    
    def _online_course_simulation(self) -> Dict[str, Any]:
        """在线课程模拟"""
        course_price = random.choice([99, 199, 299, 499])
        conversion_rate = random.uniform(0.02, 0.05)
        monthly_visitors = random.randint(1000, 5000)
        
        monthly_sales = int(monthly_visitors * conversion_rate)
        monthly_revenue = monthly_sales * course_price
        platform_fee = monthly_revenue * 0.1
        content_cost = 500  # 固定成本
        monthly_profit = monthly_revenue - platform_fee - content_cost
        
        return {
            "business_type": "在线课程",
            "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "simulation_results": {
                "course_price": course_price,
                "monthly_visitors": monthly_visitors,
                "conversion_rate": round(conversion_rate * 100, 2),
                "monthly_sales": monthly_sales,
                "monthly_revenue": monthly_revenue,
                "platform_fee": round(platform_fee, 2),
                "content_cost": content_cost,
                "monthly_profit": round(monthly_profit, 2),
                "roi": round((monthly_profit / content_cost) * 100, 1)
            },
            "key_insights": [
                "定价在199-299元区间转化率最高",
                "SEO优化可提升访客量30-50%",
                "邮件营销可将转化率提升至0.08%"
            ],
            "ai_capabilities_demonstrated": [
                "定价策略分析",
                "转化率建模",
                "ROI计算",
                "营销渠道优化"
            ]
        }
    
    def _ecommerce_simulation(self) -> Dict[str, Any]:
        """电商店铺模拟"""
        avg_order_value = random.randint(150, 400)
        monthly_orders = random.randint(100, 500)
        product_cost_rate = random.uniform(0.4, 0.6)
        shipping_cost = 15
        platform_fee_rate = 0.05
        
        monthly_revenue = monthly_orders * avg_order_value
        product_cost = monthly_revenue * product_cost_rate
        shipping_total = monthly_orders * shipping_cost
        platform_fee = monthly_revenue * platform_fee_rate
        monthly_profit = monthly_revenue - product_cost - shipping_total - platform_fee
        
        return {
            "business_type": "电商店铺",
            "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "simulation_results": {
                "avg_order_value": avg_order_value,
                "monthly_orders": monthly_orders,
                "monthly_revenue": monthly_revenue,
                "product_cost": round(product_cost, 2),
                "shipping_cost": round(shipping_total, 2),
                "platform_fee": round(platform_fee, 2),
                "monthly_profit": round(monthly_profit, 2),
                "profit_margin": round((monthly_profit / monthly_revenue) * 100, 1)
            },
            "key_insights": [
                "客单价提升50元可增加利润35%",
                "批量采购可降低产品成本10-15%",
                "优化物流可节省运费20%"
            ],
            "ai_capabilities_demonstrated": [
                "供应链成本分析",
                "定价优化",
                "物流效率计算",
                "利润率最大化"
            ]
        }
    
    def _generic_business_simulation(self, concept: str) -> Dict[str, Any]:
        """通用商业模拟"""
        investment = random.randint(5000, 20000)
        monthly_revenue = random.randint(3000, 15000)
        monthly_cost = monthly_revenue * random.uniform(0.5, 0.8)
        monthly_profit = monthly_revenue - monthly_cost
        break_even_months = investment / monthly_profit if monthly_profit > 0 else float('inf')
        
        return {
            "business_type": f"概念: {concept}",
            "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "simulation_results": {
                "initial_investment": investment,
                "monthly_revenue": monthly_revenue,
                "monthly_cost": round(monthly_cost, 2),
                "monthly_profit": round(monthly_profit, 2),
                "break_even_months": round(break_even_months, 1),
                "annual_profit": round(monthly_profit * 12, 2),
                "roi_first_year": round((monthly_profit * 12 - investment) / investment * 100, 1)
            },
            "key_insights": [
                "建议先进行小规模市场测试",
                "关注现金流管理",
                "考虑数字化营销降低获客成本"
            ],
            "ai_capabilities_demonstrated": [
                "投资回报分析",
                "现金流预测",
                "风险评估",
                "商业模式验证"
            ]
        }