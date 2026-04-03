import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(TESTS),
        pattern="*_regression.py",
        top_level_dir=str(TESTS),
    )
    if suite.countTestCases() == 0:
        print("No regression tests found.")
        raise SystemExit(1)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
