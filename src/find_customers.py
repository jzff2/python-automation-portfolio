# -*- coding: utf-8 -*-
"""
跨频道找「带预算的甲方」（可复跑采集器）

与 leads.py 的区别：leads.py 找「问题」，本脚本找「付费信号」。
先按付费关键词跨频道搜帖（粗筛，返回 feed_id + title），
再对同时命中付费信号与品类词的候选调 get-feed-detail 补全
author_id / create_time / guild_id / comment_count，
最后按「近 30 天 + 零回复 + 品类匹配」过滤。

只读操作，不发私信、不加频道。公开接单平台（Upwork/Freelancer 等）
需浏览器/登录态，不由本脚本抓取，核验结果另存 customers.json。

用法：
    python find_customers.py scan       # 真实采集 -> customers_raw.json
    python find_customers.py show       # 打印合格线索
    python find_customers.py demo       # 内置假数据验证逻辑
"""
import json
import os
import sys
import subprocess
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(BASE, "config.json")
OUT = os.path.join(BASE, "customers_raw.json")

# 付费信号词：只用于粗筛，防止对上百条无关帖逐条调详情接口
PAY_WORDS = ["有偿", "悬赏", "求代做", "付费", "带价来", "报酬", "重金",
             "外包", "报价", "接单", "有偿求助", "求代", "多少钱", "预算"]
# 品类词：与「Windows / Python 自动化与排障」相关的需求
TECH_WORDS = ["脚本", "python", "自动化", "报错", "bug", "程序", "代码",
              "打包", "环境", "爬虫", "批处理", "办公自动化", "api"]
# 生活/作业类噪声：QQ 频道里「有偿」绝大多数指这些
NOISE_WORDS = ["找狗", "找猫", "耳机", "自行车", "外卖", "戒指", "手表",
               "合租", "晾", "画", "美甲", "作业", "考试", "大作业",
               "课程", "论文", "红包", "征文", "免费", "组装", "寄存",
               "找人", "捡到", "丢失", "考研", "补课", "代课"]


def load_cfg():
    with open(CFG, encoding="utf-8") as f:
        return json.load(f)


def run_cli(cfg, args):
    env = dict(os.environ)
    env["NODE_PATH"] = cfg["cli"]["node_path"]
    cmd = [cfg["cli"]["node"], cfg["cli"]["entry"]] + args + ["--json"]
    p = subprocess.run(cmd, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    if p.returncode != 0:
        raise RuntimeError("CLI 退出码 %d: %s" % (p.returncode, p.stderr[:160]))
    d = json.loads(p.stdout.strip())
    if not d.get("success"):
        raise RuntimeError("CLI 返回失败: %s" % str(d.get("error"))[:160])
    return d.get("data", {})


def parse_time(s):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            pass
    return None


def classify(title):
    """返回 (付费命中数, 品类命中数, 噪声命中数)。"""
    t = (title or "").lower()
    return (sum(1 for w in PAY_WORDS if w in t),
            sum(1 for w in TECH_WORDS if w.lower() in t),
            sum(1 for w in NOISE_WORDS if w in t))


def scan(cfg):
    """粗筛后只对候选调详情，控制接口调用次数（复杂度：O(候选数)）。"""
    queries = ["有偿", "悬赏", "求代做", "付费求助", "外包脚本",
               "红包感谢", "带价来", "有偿求助", "求代", "检查bug"]
    coarse = {}
    for q in queries:
        try:
            data = run_cli(cfg, ["manage", "search-guild-content",
                                "--keyword", q, "--scope", "feed"])
        except Exception as e:
            print("  关键词 %s 采集失败: %s" % (q, e))
            continue
        for f in data.get("feeds", []):
            coarse[f["feed_id"]] = f
        print("  %-8s 命中 %d 条" % (q, len(data.get("feeds", []))))
    print("粗筛去重 %d 条" % len(coarse))

    # 只保留标题同时有付费信号与品类词、且无生活噪声的候选
    candidates = []
    for f in coarse.values():
        pay, tech, noise = classify(f.get("title", ""))
        if pay >= 1 and tech >= 1 and noise == 0:
            candidates.append(f)
    print("进入详情补全的候选 %d 条" % len(candidates))

    detailed = []
    for f in candidates:
        try:
            data = run_cli(cfg, ["feed", "get-feed-detail",
                                "--feed-id", f["feed_id"]])
            d = data.get("feed", {})
        except Exception as e:
            print("  详情失败 %s: %s" % (f["feed_id"][:12], e))
            continue
        item = dict(d) if d else dict(f)
        item["_pay"], item["_tech"], item["_noise"] = classify(item.get("title", ""))
        detailed.append(item)

    now = datetime.datetime.now()
    kept, dropped = [], {"过期": 0, "已有回复": 0, "品类不匹配": 0, "时间不可解析": 0}
    for item in detailed:
        t = parse_time(item.get("create_time", ""))
        if t is None:
            dropped["时间不可解析"] += 1
            continue
        age = (now - t).days
        if age > 30:
            dropped["过期"] += 1
            continue
        if int(item.get("comment_count", 0)) > 0:
            dropped["已有回复"] += 1
            continue
        if item["_tech"] < 1:
            dropped["品类不匹配"] += 1
            continue
        item["age_days"] = age
        item["score"] = item["_pay"] * 10 + item["_tech"] * 5 - min(age, 30)
        kept.append(item)
    kept.sort(key=lambda x: -x["score"])

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"generated_at": now.isoformat(),
                   "coarse_total": len(coarse),
                   "detail_total": len(detailed),
                   "dropped": dropped, "leads": kept}, f,
                  ensure_ascii=False, indent=2)
    print("粗筛 %d -> 详情 %d -> 合格 %d" % (len(coarse), len(detailed), len(kept)))
    print("淘汰明细:", dropped)
    return kept


def demo():
    """不联网，验证分类与打分逻辑。"""
    samples = [
        {"title": "有偿找个大佬修一下 Python 打包报错", "create_time":
         (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
         "comment_count": 0, "author_id": "144115200000000001"},
        {"title": "有偿找狗，找到 2000 元酬谢", "create_time":
         (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
         "comment_count": 0, "author_id": "144115200000000002"},
        {"title": "求代做离散数学大作业", "create_time":
         (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
         "comment_count": 0, "author_id": "144115200000000003"},
    ]
    print("=== 分类逻辑验证 ===")
    for s in samples:
        print("  %-28s -> 付费%d 品类%d 噪声%d" %
              (s["title"][:26], *classify(s["title"])))
    return samples


def show():
    if not os.path.exists(OUT):
        print("请先运行 scan")
        return
    with open(OUT, encoding="utf-8") as f:
        d = json.load(f)
    print("合格线索 %d 条（粗筛 %d / 详情 %d）" %
          (len(d["leads"]), d["coarse_total"], d["detail_total"]))
    for x in d["leads"]:
        print("  [%d分] %s | %s | %d天前 | 回复%s" %
              (x["score"], x.get("title"), x.get("author"),
               x["age_days"], x.get("comment_count")))
        print("        author_id=%s guild_id=%s" %
              (x.get("author_id"), x.get("guild_id")))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "scan":
        scan(load_cfg())
    elif cmd == "demo":
        demo()
    elif cmd == "show":
        show()
    else:
        print("可用子命令: scan / demo / show")


if __name__ == "__main__":
    main()
