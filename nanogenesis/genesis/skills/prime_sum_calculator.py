import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class PrimeSumCalculator(Tool):
    @property
    def name(self) -> str:
        return "prime_sum_calculator"
        
    @property
    def description(self) -> str:
        return "Calculate the sum of prime numbers within a specified range."
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "start": {"type": "integer", "description": "The start of the range (inclusive)."},
                "end": {"type": "integer", "description": "The end of the range (inclusive)."}
            },
            "required": ["start", "end"]
        }
        
    async def execute(self, start: int, end: int) -> str:
        def is_prime(n):
            if n <= 1:
                return False
            for i in range(2, int(n**0.5)+1):
                if n % i == 0:
                    return False
            return True

        prime_sum = 0
        primes_in_range = []
        for num in range(start, end + 1):
            if is_prime(num):
                primes_in_range.append(num)
                prime_sum += num

        return f"Prime numbers between {start} and {end}: {primes_in_range}. Sum: {prime_sum}"
