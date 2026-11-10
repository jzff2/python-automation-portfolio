# -*- coding: utf-8 -*-
"""工单登记与归因：验证真实 CLI 行为与数值计算。"""
import os
import sys
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util


class TestJobs(unittest.TestCase):

    def setUp(self):
        self.d = _util.sandbox("jobs.py")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _add(self, **kv):
        args = ["add"] + ["%s=%s" % (k, v) for k, v in kv.items()]
        return _util.run(self.d, "jobs.py", *args)

    def test_empty_report(self):
        rc, out = _util.run(self.d, "jobs.py", "report")
        self.assertEqual(rc, 0)
        self.assertIn("暂无记录", out)

    def test_fields_command(self):
        rc, out = _util.run(self.d, "jobs.py", "fields")
        self.assertIn("工时分钟", out)
        self.assertIn("实收", out)

    def test_add_and_report_numbers(self):
        rc, out = self._add(客户="示例甲", 问题="pythonw静默退出",
                            诊断="父窗口被Explorer销毁", 实收="300",
                            工时分钟="50", 复购="否", 渠道="熟人")
        self.assertEqual(rc, 0)
        self.assertIn("已登记", out)

        rc, out = _util.run(self.d, "jobs.py", "report")
        self.assertIn("单数=1", out)
        self.assertIn("实收=300.00", out)
        self.assertIn("工时=0.8h", out)
        self.assertIn("时薪=360.00", out)  # 300 / (50/60)
        self.assertIn("可复用诊断条目=1 / 1", out)

    def test_unknown_field_rejected(self):
        rc, out = self._add(不存在的字段="x")
        self.assertIn("未知字段", out)

    def test_list_contains_diagnosis(self):
        self._add(客户="示例乙", 问题="打包失败", 诊断="缺少隐式依赖", 实收="100")
        rc, out = _util.run(self.d, "jobs.py", "list")
        self.assertIn("缺少隐式依赖", out)

    def test_merge_legacy_ledger(self):
        """上一轮的 ledger.csv 实收应被合并进汇总。"""
        _util.write(self.d, "ledger.csv",
                    "日期,客户,品类,报价,实收,工时分钟,复购,渠道\n"
                    "2026-11-10,旧账,写作,100,100,60,否,熟人\n")
        rc, out = _util.run(self.d, "jobs.py", "report")
        self.assertIn("合并 ledger.csv", out)
        self.assertIn("总实收=100.00", out)

    def test_high_frequency_problem_ranking(self):
        for i in range(3):
            self._add(客户="客%d" % i, 问题="pythonw静默退出", 诊断="自愈", 实收="10")
        self._add(客户="客9", 问题="打包失败", 诊断="缺依赖", 实收="10")
        rc, out = _util.run(self.d, "jobs.py", "report")
        self.assertIn("3 次  pythonw静默退出", out)


if __name__ == "__main__":
    unittest.main()
