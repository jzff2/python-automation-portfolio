# -*- coding: utf-8 -*-
"""
线索发现与过滤（变现链路第 1 段）

真实模式调用本机 tencent-channel-cli 搜频道内求助帖；
demo 模式用内置假数据验证流水线，不接触真实账号。

用法：
    python leads.py scan      # 真实搜索 -> leads_raw.json
    python leads.py demo      # 内置假数据 -> leads_raw.json
    python leads.py filter    # 按 config 过滤打分 -> leads.json
    python leads.py show      # 打印合格线索
"""
import json
import os
import sys
import subprocess
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(BASE, "config.json")
RAW = os.path.join(BASE, "leads_raw.json")
OUT = os.path.join(BASE, "leads.json")


def load_cfg():
    with open(CFG, encoding="utf-8") as f:
        return json.load(f)


def run_cli(cfg, args):
    """调用频道 CLI，返回 data 段；失败抛异常，不静默吞掉。"""
    env = dict(os.environ)
    env["NODE_PATH"] = cfg["cli"]["node_path"]
    cmd = [cfg["cli"]["node"], cfg["cli"]["entry"]] + args + ["--json"]
    p = subprocess.run(cmd, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    if p.returncode != 0:
        raise RuntimeError("CLI 退出码 %d: %s" % (p.returncode, p.stderr[:200]))
    d = json.loads(p.stdout.strip())
    if not d.get("success"):
        raise RuntimeError("CLI 返回失败: %s" % str(d.get("error"))[:200])
    return d.get("data", {})


def scan(cfg):
    """多关键词搜索，按 feed_id 去重。前提：账号已加入目标频道。"""
    src = cfg["source"]
    rows = {}
    for q in src["queries"]:
        try:
            data = run_cli(cfg, ["feed", "search-guild-feeds",
                                "--guild-id", src["guild_id"], "--query", q])
        except Exception as e:
            print("  查询 %s 失败: %s" % (q, e))
            continue
        feeds = data.get("guild_feeds", [])
        for f in feeds:
            rows[f["feed_id"]] = f
        print("  查询 %-10s 命中 %d 条" % (q, len(feeds)))
    out = list(rows.values())
    with open(RAW, "w", encoding="utf-8") as f:
        json.dump({"source": src, "demo": False,
                   "fetched_at": datetime.datetime.now().isoformat(),
                   "feeds": out}, f, ensure_ascii=False, indent=2)
    print("去重后 %d 条 -> leads_raw.json" % len(out))
    return out


def demo(cfg):
    """四条构造数据：近期零回复 / 旧帖 / 已有回复 / 广告帖。"""
    now = datetime.datetime.now()

    def ts(days):
        return (now - datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    feeds = [
        {"feed_id": "DEMO-NEW", "author": "示例甲", "author_id": "144115200000000001",
         "title": "pyinstaller 打包后脚本跑不起来求助", "create_time": ts(2), "comment_count": 0},
        {"feed_id": "DEMO-OLD", "author": "示例乙", "author_id": "144115200000000002",
         "title": "Python 环境报错怎么解决", "create_time": ts(400), "comment_count": 3},
        {"feed_id": "DEMO-ANS", "author": "示例丙", "author_id": "144115200000000003",
         "title": "报错求助", "create_time": ts(1), "comment_count": 12},
        {"feed_id": "DEMO-AD", "author": "示例丁", "author_id": "144115200000000004",
         "title": "接单广告：代做脚本", "create_time": ts(1), "comment_count": 0},
    ]
    with open(RAW, "w", encoding="utf-8") as f:
        json.dump({"source": cfg["source"], "demo": True,
                   "fetched_at": now.isoformat(), "feeds": feeds}, f,
                  ensure_ascii=False, indent=2)
    print("demo 假数据 4 条 -> leads_raw.json")
    return feeds


def parse_time(s):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            pass
    return None


def do_filter(cfg):
    """只保留「近期 + 无人回复 + 含求助关键词 + 非广告」的线索。"""
    if not os.path.exists(RAW):
        print("请先运行 scan 或 demo")
        return []
    with open(RAW, encoding="utf-8") as f:
        raw = json.load(f)
    flt = cfg["filter"]
    now = datetime.datetime.now()
    kept = []
    dropped = {"过期": 0, "已有回复": 0, "命中排除词": 0,
               "无关键词": 0, "时间不可解析": 0}
    for feed in raw["feeds"]:
        t = parse_time(feed.get("create_time", ""))
        if t is None:
            dropped["时间不可解析"] += 1
            continue
        age = (now - t).days
        if age > flt["max_age_days"]:
            dropped["过期"] += 1
            continue
        if flt["require_zero_comment"] and int(feed.get("comment_count", 0)) > 0:
            dropped["已有回复"] += 1
            continue
        title = feed.get("title", "")
        if any(w in title for w in flt["exclude"]):
            dropped["命中排除词"] += 1
            continue
        hits = sum(1 for w in flt["keywords"] if w in title)
        if hits == 0:
            dropped["无关键词"] += 1
            continue
        item = dict(feed)
        item["age_days"] = age
        item["score"] = hits * 10 - min(age, 30)  # 越新、命中越多越优先
        kept.append(item)
    kept.sort(key=lambda x: -x["score"])
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now.isoformat(), "total_raw": len(raw["feeds"]),
                   "demo": raw.get("demo", False), "dropped": dropped,
                   "leads": kept}, f, ensure_ascii=False, indent=2)
    print("原始 %d 条 -> 合格 %d 条" % (len(raw["feeds"]), len(kept)))
    print("淘汰明细:", dropped)
    return kept


def show():
    if not os.path.exists(OUT):
        print("请先运行 filter")
        return
    with open(OUT, encoding="utf-8") as f:
        d = json.load(f)
    print("合格线索 %d 条：" % len(d["leads"]))
    for x in d["leads"]:
        print("  [%d分] %s | %s | %d天前 | 回复%d" %
              (x["score"], x["title"], x["author"], x["age_days"],
               x.get("comment_count", 0)))
        print("        author_id=%s" % x["author_id"])


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    # 配置按需加载：show 是纯查询，不应因目录里没有 config.json 而崩溃。
    # 该缺陷由 tests/test_leads.py 的 test_show_without_filter_does_not_crash 发现。
    if cmd == "scan":
        scan(load_cfg())
    elif cmd == "demo":
        demo(load_cfg())
    elif cmd == "filter":
        do_filter(load_cfg())
    elif cmd == "show":
        show()
    else:
        print("可用子命令: scan / demo / filter / show")


if __name__ == "__main__":
    main()
