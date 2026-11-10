# -*- coding: utf-8 -*-
"""
外联与成交登记（变现链路第 2、3 段）

draft 生成私信草稿；send 默认预演、不发送，只有 config.send.enabled=true
且命令行带 --send 才真正调用 CLI 发私信；close 把成交写进 jobs.csv。

用法：
    python outreach.py draft
    python outreach.py send                  # 预演（默认，不发送）
    python outreach.py send --send           # 真发（需 config.send.enabled=true）
    python outreach.py close --lead=ID --amount=200 --minutes=50 --problem=描述
"""
import json
import os
import sys
import csv
import time
import subprocess
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(BASE, "config.json")
LEADS = os.path.join(BASE, "leads.json")
DRAFTS = os.path.join(BASE, "drafts.json")
SENT = os.path.join(BASE, "sent.json")
JOBS = os.path.join(os.path.dirname(BASE), "jobs.csv")

JOB_FIELDS = ["日期", "客户", "问题", "环境", "诊断", "复现", "修复", "验收",
              "工时分钟", "报价", "实收", "复购", "渠道"]


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cfg():
    return load_json(CFG)


def draft():
    """按 config 里的服务/报价生成私信，写 drafts.json。只生成，不发送。"""
    c = cfg()
    d = load_json(LEADS)
    if not d or not d["leads"]:
        print("无合格线索，跳过草稿生成")
        return []
    o = c["offer"]
    items = []
    for x in d["leads"]:
        text = (
            "你好，看到你在「%s」发的《%s》。我做 %s，交付 %s，"
            "单次 %s 元，%s。如果这个问题还没解决，可以把完整报错和环境信息发我，"
            "我先判断能不能接。联系方式：%s。"
        ) % (c["source"]["guild_name"], x["title"], o["service"],
             o["deliverables"], o["price"], o["revision"], o["contact"])
        items.append({
            "feed_id": x["feed_id"],
            "author": x["author"],
            "peer_tiny_id": x["author_id"],
            "source_guild_id": c["source"]["guild_id"],
            "text": text,
        })
    with open(DRAFTS, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print("生成 %d 条草稿 -> drafts.json" % len(items))
    for it in items:
        print("  -> %s: %s..." % (it["author"], it["text"][:60]))
    return items


def send(real):
    """预演或真发。真发有去重、间隔、日上限三重约束。"""
    c = cfg()
    items = load_json(DRAFTS, [])
    if not items:
        print("无草稿，先运行 draft")
        return
    if real and not c["send"]["enabled"]:
        print("config.json 中 send.enabled=false，未发送（改 true 后再执行 --send）")
        return
    sent = load_json(SENT, [])
    done = {s["feed_id"] for s in sent}
    s = c["send"]
    n = 0
    for it in items:
        if it["feed_id"] in done:
            print("  跳过已发:", it["feed_id"])
            continue
        if n >= s["daily_cap"]:
            print("达到日上限 %d，停止" % s["daily_cap"])
            break
        if n >= s["max_total"]:
            print("达到总量上限 %d，停止" % s["max_total"])
            break
        args = ["manage", "push-group-dm-msg",
                "--peer-tiny-id", it["peer_tiny_id"],
                "--source-guild-id", it["source_guild_id"],
                "--text", it["text"]]
        cmd = [c["cli"]["node"], c["cli"]["entry"]] + args + ["--json"]
        if not real:
            print("  [预演] %s | peer=%s | guild=%s" %
                  (it["author"], it["peer_tiny_id"], it["source_guild_id"]))
            print("        text=%s" % it["text"])
            print("        cmd=%s" % " ".join(cmd))
            n += 1
            continue
        env = dict(os.environ)
        env["NODE_PATH"] = c["cli"]["node_path"]
        p = subprocess.run(cmd, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        print("  已发 %s -> %s" % (it["author"], p.stdout.strip()[:140]))
        sent.append({"feed_id": it["feed_id"],
                     "sent_at": datetime.datetime.now().isoformat()})
        with open(SENT, "w", encoding="utf-8") as f:
            json.dump(sent, f, ensure_ascii=False, indent=2)
        n += 1
        time.sleep(s["interval_seconds"])  # 频控：按配置间隔逐条发
    print("本次处理 %d 条；real=%s" % (n, real))


def close(kv):
    """成交登记：写进上一轮交付的 jobs.csv，实收由调用方给。"""
    c = cfg()
    row = {k: "" for k in JOB_FIELDS}
    row["日期"] = datetime.date.today().isoformat()
    row["客户"] = kv.get("lead", "未指定")
    row["问题"] = kv.get("problem", "未填写")
    row["报价"] = c["offer"]["price"]
    row["实收"] = kv.get("amount", "0")
    row["工时分钟"] = kv.get("minutes", "0")
    row["复购"] = "否"
    row["渠道"] = c["source"]["guild_name"]
    row["验收"] = kv.get("accept", "脚本可运行、问题不复现")
    new = not os.path.exists(JOBS)
    with open(JOBS, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=JOB_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    print("已登记成交 -> %s | 实收=%s" % (JOBS, row["实收"]))


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "draft"
    if cmd == "draft":
        draft()
    elif cmd == "send":
        send("--send" in args)
    elif cmd == "close":
        kv = {}
        for a in args[1:]:
            if a.startswith("--") and "=" in a:
                k, v = a[2:].split("=", 1)
                kv[k] = v
        close(kv)
    else:
        print("可用子命令: draft / send / send --send / close --lead=X --amount=X --minutes=X")


if __name__ == "__main__":
    main()
