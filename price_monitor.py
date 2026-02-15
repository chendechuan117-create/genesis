import time
import random
from datetime import datetime
import json

class RealPriceMonitor:
    def __init__(self, config_file='products.json'):
        self.products = []
        self.config_file = config_file
        self.load_config()
        
    def load_config(self):
        default_products = [
            {'name': 'NVIDIA RTX 4090', 'category': '显卡', 'base_price': 12999},
            {'name': 'iPhone 15 Pro', 'category': '手机', 'base_price': 7999},
            {'name': 'PS5 Slim', 'category': '游戏机', 'base_price': 3499},
            {'name': 'Air Jordan 1', 'category': '球鞋', 'base_price': 1299},
            {'name': 'MacBook Pro M3', 'category': '笔记本', 'base_price': 12999}
        ]
        
        try:
            with open(self.config_file, 'r') as f:
                self.products = json.load(f)
        except:
            self.products = default_products
            self.save_config()
    
    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.products, f, indent=2)
    
    def simulate_market(self):
        alerts = []
        
        for product in self.products:
            change = random.uniform(-0.05, 0.03)
            old_price = product.get('current_price', product['base_price'])
            new_price = round(old_price * (1 + change), 2)
            
            product['current_price'] = new_price
            product['last_update'] = datetime.now().isoformat()
            
            if change < -0.03:
                alert = {
                    'product': product['name'],
                    'category': product['category'],
                    'old_price': old_price,
                    'new_price': new_price,
                    'discount_pct': round(abs(change)*100, 1),
                    'savings': round(old_price - new_price, 2),
                    'timestamp': datetime.now().isoformat(),
                    'opportunity': 'BUY' if change < -0.05 else 'WATCH'
                }
                alerts.append(alert)
        
        self.save_config()
        return alerts
    
    def generate_report(self, alerts):
        if not alerts:
            return '📊 市场稳定，无显著价格波动'
        
        report = ['🚨 **价格监控报告** 🚨', '']
        total_savings = 0
        
        for alert in alerts:
            report.append(f'**{alert["product"]}** ({alert["category"]})')
            report.append(f'  📉 降价: {alert["discount_pct"]}%')
            report.append(f'  💰 价格: ¥{alert["old_price"]} → ¥{alert["new_price"]}')
            report.append(f'  💸 节省: ¥{alert["savings"]}')
            report.append(f'  🎯 建议: {alert["opportunity"]}')
            report.append('')
            total_savings += alert['savings']
        
        report.append(f'**总计节省机会**: ¥{total_savings}')
        report.append(f'**监控时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        
        return '\n'.join(report)
    
    def run(self, interval=60):
        print(f'🔍 启动价格监控系统 (间隔: {interval}秒)')
        print(f'📋 监控产品: {len(self.products)}个')
        print('---')
        
        cycle = 0
        while True:
            cycle += 1
            print(f'🔄 第{cycle}次检查 ({datetime.now().strftime("%H:%M:%S")})')
            
            alerts = self.simulate_market()
            
            if alerts:
                report = self.generate_report(alerts)
                print(report)
                print('---')
                
                with open('price_alerts.log', 'a') as f:
                    f.write(f'\n=== 警报批次 {cycle} ===\n')
                    for alert in alerts:
                        f.write(json.dumps(alert) + '\n')
            
            time.sleep(interval)

if __name__ == '__main__':
    monitor = RealPriceMonitor()
    for i in range(5):
        alerts = monitor.simulate_market()
        if alerts:
            print(monitor.generate_report(alerts))
        else:
            print(f'周期 {i+1}: 市场价格稳定')
        time.sleep(2)
