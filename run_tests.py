# -*- coding: utf-8 -*-
"""无第三方依赖的测试入口：python run_tests.py"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(ROOT, "tests")
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)


def main():
    suite = unittest.TestLoader().discover(TESTS, pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("TOTAL=%d  FAIL=%d  ERROR=%d" %
          (result.testsRun, len(result.failures), len(result.errors)))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
