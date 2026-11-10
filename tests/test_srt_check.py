# -*- coding: utf-8 -*-
"""AI 字幕验收：验证只标疑似、不自动改，且各类风险被正确识别。"""
import os
import sys
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util

SRT = """1
00:00:00,000 --> 00:00:03,500
今天给大家讲一下 2026 年的报价

2
00:00:03,200 --> 00:00:06,000
这个 CapCut Pro 每月 9.99 美元

3
00:00:06,000 --> 00:00:09,000
我们我们 先看看效果

4
00:00:09,000 --> 00:00:12,000
嗯

5
00:00:12,000 --> 00:00:15,000
普通的一句话不需要核对
"""


class TestSrtCheck(unittest.TestCase):

    def setUp(self):
        self.d = _util.sandbox("srt_check.py")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_flags_all_four_risk_blocks(self):
        _util.write(self.d, "sample.srt", SRT)
        rc, out = _util.run(self.d, "srt_check.py", "sample.srt")
        self.assertEqual(rc, 0)
        self.assertIn("字幕块=5", out)
        self.assertIn("需人工复核=4", out)
        self.assertIn("含数字/金额/百分比", out)
        self.assertIn("含英文专名或缩写", out)
        self.assertIn("相邻重复", out)
        self.assertIn("与上一条时间轴重叠", out)
        self.assertIn("单行过短", out)
        # 正常句不应被标出
        self.assertNotIn("普通的一句话", out)

    def test_no_autocorrection(self):
        """检查器只输出疑似清单，不改写源文件。"""
        _util.write(self.d, "sample.srt", SRT)
        before = open(os.path.join(self.d, "sample.srt"), encoding="utf-8").read()
        _util.run(self.d, "srt_check.py", "sample.srt")
        after = open(os.path.join(self.d, "sample.srt"), encoding="utf-8").read()
        self.assertEqual(before, after)

    def test_malformed_input(self):
        _util.write(self.d, "bad.srt", "这不是字幕文件\n")
        rc, out = _util.run(self.d, "srt_check.py", "bad.srt")
        self.assertIn("未解析到有效字幕块", out)

    def test_show_all_flag(self):
        _util.write(self.d, "sample.srt", SRT)
        rc, out = _util.run(self.d, "srt_check.py", "sample.srt", "--all")
        self.assertIn("=== 全部字幕 ===", out)
        self.assertIn("普通的一句话不需要核对", out)


if __name__ == "__main__":
    unittest.main()
