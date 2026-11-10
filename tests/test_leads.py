# -*- coding: utf-8 -*-
"""线索过滤：验证时间窗 / 零回复 / 关键词 / 排除词四类淘汰规则。"""
import os
import sys
import json
import shutil
import unittest
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util

CFG = {
    "source": {"guild_id": "1", "guild_name": "示例频道", "queries": []},
    "filter": {
        "max_age_days": 30,
        "require_zero_comment": True,
        "keywords": ["报错", "求助", "失败", "跑不起来", "安装", "打包", "环境", "怎么办"],
        "exclude": ["已解决", "招聘", "广告", "接单", "代做"],
    },
}


def _ts(days):
    return (datetime.datetime.now() - datetime.timedelta(days=days)).strftime(
        "%Y-%m-%d %H:%M:%S")


class TestLeads(unittest.TestCase):

    def setUp(self):
        self.d = _util.sandbox("leads.py")
        self.m = _util.load_module(self.d, "leads")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_parse_time_valid_and_invalid(self):
        self.assertEqual(self.m.parse_time("2026-11-10 12:00:00").year, 2026)
        self.assertEqual(self.m.parse_time("2026-11-10").day, 10)
        self.assertIsNone(self.m.parse_time("不是时间"))

    def test_filter_keeps_only_recent_unanswered(self):
        feeds = [
            {"feed_id": "A", "author": "甲", "author_id": "1",
             "title": "pyinstaller 打包后脚本跑不起来求助",
             "create_time": _ts(2), "comment_count": 0},
            {"feed_id": "B", "author": "乙", "author_id": "2",
             "title": "Python 环境报错怎么解决",
             "create_time": _ts(400), "comment_count": 0},
            {"feed_id": "C", "author": "丙", "author_id": "3",
             "title": "报错求助", "create_time": _ts(1), "comment_count": 12},
            {"feed_id": "D", "author": "丁", "author_id": "4",
             "title": "接单广告：代做脚本", "create_time": _ts(1), "comment_count": 0},
            {"feed_id": "E", "author": "戊", "author_id": "5",
             "title": "今天天气不错", "create_time": _ts(1), "comment_count": 0},
        ]
        _util.write(self.d, "leads_raw.json",
                    json.dumps({"demo": True, "feeds": feeds}, ensure_ascii=False))
        kept = self.m.do_filter(CFG)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["feed_id"], "A")
        with open(os.path.join(self.d, "leads.json"), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["dropped"]["过期"], 1)
        self.assertEqual(data["dropped"]["已有回复"], 1)
        self.assertEqual(data["dropped"]["命中排除词"], 1)
        self.assertEqual(data["dropped"]["无关键词"], 1)

    def test_demo_writes_raw_file(self):
        self.m.demo(CFG)
        self.assertTrue(os.path.isfile(os.path.join(self.d, "leads_raw.json")))
        kept = self.m.do_filter(CFG)
        self.assertEqual(len(kept), 1)

    def test_show_without_filter_does_not_crash(self):
        rc, out = _util.run(self.d, "leads.py", "show")
        self.assertIn("请先运行 filter", out)


if __name__ == "__main__":
    unittest.main()
