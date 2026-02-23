import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class PrimeNumberCalculator(Tool):
    def __init__(self):
        super().__init__()
        self.name = 'prime_number_calculator'
        self.description = 'Calculates prime numbers within a given range and their sum.'
        self.parameters = {
            'type': 'object',
            'properties': {
                'start': {'type': 'integer', 'description': 'Start of the range (inclusive)'},
                'end': {'type': 'integer', 'description': 'End of the range (inclusive)'}
            },
            'required': ['start', 'end']
        }

    def is_prime(self, n):
        if n <= 1:
            return False
        if n == 2:
            return True
        if n % 2 == 0:
            return False
        for i in range(3, int(n**0.5) + 1, 2):
            if n % i == 0:
                return False
        return True

    def execute(self, params):
        start = params.get('start')
        end = params.get('end')
        primes = []
        for num in range(start, end + 1):
            if self.is_prime(num):
                primes.append(num)
        sum_primes = sum(primes)
        return {
            'prime_list': primes,
            'sum_of_primes': sum_primes,
            'calculation': ' + '.join(map(str, primes)) + ' = ' + str(sum_primes)
        }