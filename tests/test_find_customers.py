# -*- coding: utf-8 -*-
"""付费信号分类：验证能区分技术付费需求与校园生活悬赏。"""
import os
import sys
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util


class TestFindCustomers(unittest.TestCase):

    def setUp(self):
        self.d = _util.sandbox("find_customers.py")
        self.m = _util.load_module(self.d, "find_customers")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_tech_paid_request(self):
        pay, tech, noise = self.m.classify("有偿找个大佬修一下 Python 打包报错")
        self.assertGreaterEqual(pay, 1)
        self.assertGreaterEqual(tech, 2)
        self.assertEqual(noise, 0)

    def test_life_reward_is_noise(self):
        pay, tech, noise = self.m.classify("有偿找狗，找到 2000 元酬谢")
        self.assertGreaterEqual(pay, 1)
        self.assertEqual(tech, 0)
        self.assertGreaterEqual(noise, 1)

    def test_homework_is_noise(self):
        pay, tech, noise = self.m.classify("求代做离散数学大作业")
        self.assertGreaterEqual(pay, 1)
        self.assertGreaterEqual(noise, 1)

    def test_plain_chat_has_no_signal(self):
        pay, tech, noise = self.m.classify("今天群里好热闹")
        self.assertEqual((pay, tech, noise), (0, 0, 0))

    def test_parse_time(self):
        self.assertEqual(self.m.parse_time("2025-12-07 20:48:00").year, 2025)
        self.assertIsNone(self.m.parse_time(""))

    def test_demo_runs(self):
        rc, out = _util.run(self.d, "find_customers.py", "demo")
        self.assertEqual(rc, 0)
        self.assertIn("分类逻辑验证", out)


if __name__ == "__main__":
    unittest.main()
