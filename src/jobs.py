# -*- coding: utf-8 -*-
"""
排障工单登记 + 归因（编程变现第 0 档最小件）

用途：把「判断」变成可核验的记录。每一单既是收款凭证，
也是日后打包成诊断手册 / 模板 / 工具（数字资产）的原料。

用法（字段用 key=value，顺序随意，未填字段留空）：
    python jobs.py add 客户=张三 问题=pythonw静默退出 环境=Win11 \
        诊断=WebView2父窗口被Explorer销毁 复现=重启Explorer 修复=supervisor自愈 \
        验收=3秒内窗口恢复 工时分钟=50 报价=300 实收=300 复购=否 渠道=熟人

    python jobs.py report     # 汇总：单数、实收、工时、时薪、高频问题
    python jobs.py list       # 列出全部诊断结论（数字资产原料）
    python jobs.py fields     # 打印可用字段

数据落在脚本同目录 jobs.csv；若同目录存在上一轮的 ledger.csv，
report 会把它的实收一并计入，两轮的账接得上。
"""
import csv
import os
import sys
import datetime
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
JOBS = os.path.join(BASE, "jobs.csv")
LEDGER = os.path.join(BASE, "ledger.csv")

FIELDS = [
    "日期", "客户", "问题", "环境", "诊断", "复现", "修复", "验收",
    "工时分钟", "报价", "实收", "复购", "渠道",
]


def _read(path):
    """读 CSV，文件不存在返回空列表。"""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _num(v):
    """把金额/工时安全转数字，空值或非数字按 0 处理。"""
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return 0.0


def cmd_add(pairs):
    """登记一单。key=value 解析，未知字段直接报错，避免顺序错位。"""
    row = {k: "" for k in FIELDS}
    row["日期"] = datetime.date.today().isoformat()
    for p in pairs:
        if "=" not in p:
            print("参数格式错误（应为 key=value）：%s" % p)
            return
        k, v = p.split("=", 1)
        k = k.strip()
        if k not in FIELDS or k == "日期":
            print("未知字段：%s（可用字段见 python jobs.py fields）" % k)
            return
        row[k] = v.strip()

    new = not os.path.exists(JOBS)
    with open(JOBS, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    print("已登记：%s | %s | 诊断=%s | 实收=%s" %
          (row["日期"], row["客户"], row["诊断"] or "(空)", row["实收"] or "(空)"))


def cmd_report():
    """汇总工单账，并兼容合并上一轮 ledger.csv 的实收。"""
    rows = _read(JOBS)
    old = _read(LEDGER)
    if not rows and not old:
        print("暂无记录。先跑一条：python jobs.py add 客户=示例 问题=示例 实收=100 工时分钟=60")
        return

    total = sum(_num(r.get("实收")) for r in rows)
    mins = sum(_num(r.get("工时分钟")) for r in rows)
    old_total = sum(_num(r.get("实收")) for r in old)
    grand = total + old_total

    print("=== 工单 ===")
    print("单数=%d 实收=%.2f 工时=%.1fh 时薪=%.2f" %
          (len(rows), total, mins / 60, total / (mins / 60) if mins else 0))
    if old:
        print("合并 ledger.csv：额外 %d 单 / 实收 %.2f" % (len(old), old_total))
        print("总实收=%.2f" % grand)

    # 高频问题 = 最值得固化成模板/工具的诊断类别
    probs = Counter((r.get("问题") or "").strip() for r in rows if (r.get("问题") or "").strip())
    if probs:
        print("\n=== 高频问题（可产品化优先级）===")
        for name, n in probs.most_common():
            print("  %2d 次  %s" % (n, name))

    diag = [r for r in rows if (r.get("诊断") or "").strip()]
    print("\n可复用诊断条目=%d / %d（这些是数字资产原料）" % (len(diag), len(rows)))


def cmd_list():
    """列出全部诊断结论，供打包成手册 / Skill / 模板时取用。"""
    rows = _read(JOBS)
    if not rows:
        print("暂无记录")
        return
    for i, r in enumerate(rows, 1):
        print("[%d] %s | %s | %s" % (i, r.get("日期"), r.get("问题"), r.get("环境")))
        print("    诊断: %s" % (r.get("诊断") or "(空)"))
        print("    修复: %s" % (r.get("修复") or "(空)"))
        print("    验收: %s" % (r.get("验收") or "(空)"))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "add":
        cmd_add(sys.argv[2:])
    elif cmd == "report":
        cmd_report()
    elif cmd == "list":
        cmd_list()
    elif cmd == "fields":
        print(" ".join(FIELDS[1:]))
    else:
        print("未知命令：%s（可用 add / report / list / fields）" % cmd)


if __name__ == "__main__":
    main()
