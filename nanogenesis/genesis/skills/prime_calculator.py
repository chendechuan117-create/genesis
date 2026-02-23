from genesis.core.base import Tool

class PrimeCalculator(Tool):
    """质数计算工具"""
    
    name = "prime_calculator"
    description = "计算指定范围内的所有质数并求和"
    
    def __init__(self):
        super().__init__()
    
    def is_prime(self, n: int) -> bool:
        """判断一个数是否为质数"""
        if n <= 1:
            return False
        if n <= 3:
            return True
        if n % 2 == 0 or n % 3 == 0:
            return False
        
        i = 5
        while i * i <= n:
            if n % i == 0 or n % (i + 2) == 0:
                return False
            i += 6
        return True
    
    def calculate_primes_sum(self, start: int, end: int) -> dict:
        """计算指定范围内的所有质数及其和"""
        primes = []
        total_sum = 0
        
        for num in range(start, end + 1):
            if self.is_prime(num):
                primes.append(num)
                total_sum += num
        
        return {
            "range": f"{start}到{end}",
            "primes": primes,
            "count": len(primes),
            "sum": total_sum,
            "details": f"质数列表: {primes}, 总数: {len(primes)}, 和: {total_sum}"
        }
    
    def execute(self, start: int = 1, end: int = 50) -> dict:
        """执行计算"""
        return self.calculate_primes_sum(start, end)