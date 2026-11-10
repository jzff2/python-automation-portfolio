# -*- coding: utf-8 -*-
"""
AI 字幕验收检查器（AI 剪辑流水线里唯一必须先做的那一步）

依据：2026 语音转写顶级模型词错率约 2%，60 秒 / 150 词仍约错 3 词，
且错误集中在人名、数字、价格、产品名、技术术语——恰好是最不能错的地方。
本脚本只标疑似、不自动改，把「判断」留在人手里。纯标准库，无外部依赖。

用法：
    python srt_check.py input.srt
    python srt_check.py input.srt --all    # 附带打印全部字幕行

疑似规则：
- 含数字 / 金额 / 百分号 / 英文专名或缩写 -> 必人工核对
- 相邻重复（口吃误转写）-> 疑似
- 单行过长或过短 -> 疑似断句错误
- 时间轴非正向、与上一条重叠 -> 结构错误
"""
import re
import sys

RISK_NUM = re.compile(r"\d|[%％￥$€£]")
RISK_ENG = re.compile(r"[A-Za-z]{2,}")
REPEAT_EN = re.compile(r"\b(\w{2,})\s+\1\b")
REPEAT_CN = re.compile(r"(.{2,4})\1")
TIME = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)


def parse(path):
    """解析 SRT，返回 [(序号, 起始秒, 结束秒, 文本)]。"""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        raw = f.read().strip()
    rows = []
    for block in re.split(r"\n\s*\n", raw):
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        m = re.match(r"\s*(\d+)\s*$", lines[0])
        t = TIME.search(lines[1])
        if not m or not t:
            continue
        g = [int(x) for x in t.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        rows.append((int(m.group(1)), start, end, " ".join(lines[2:]).strip()))
    return rows


def check(rows):
    """返回 {序号: (起始秒, 文本, [疑似原因...])}，同一条合并原因。"""
    flags = {}

    def add(idx, start, text, reason):
        if idx not in flags:
            flags[idx] = (start, text, [])
        flags[idx][2].append(reason)

    for idx, start, end, text in rows:
        if RISK_NUM.search(text):
            add(idx, start, text, "含数字/金额/百分比")
        if RISK_ENG.search(text):
            add(idx, start, text, "含英文专名或缩写")
        if REPEAT_EN.search(text) or REPEAT_CN.search(text):
            add(idx, start, text, "相邻重复（疑口吃误转写）")
        n = len(text)
        if n > 42:
            add(idx, start, text, "单行过长(%d字)疑断句错误" % n)
        if 0 < n < 3:
            add(idx, start, text, "单行过短(%d字)疑漏字" % n)
        if end <= start:
            add(idx, start, text, "时间轴非正向")

    for prev, cur in zip(rows, rows[1:]):
        if cur[1] < prev[2] - 0.001:
            add(cur[0], cur[1], cur[3], "与上一条时间轴重叠")
    return flags


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    rows = parse(sys.argv[1])
    if not rows:
        print("未解析到有效字幕块：检查文件编码与时间轴格式")
        return
    flags = check(rows)
    n = len(flags)
    print("字幕块=%d  需人工复核=%d  占比=%.1f%%" % (len(rows), n, 100.0 * n / len(rows)))
    print("（只标疑似、不自动改；错误集中在名字/数字/价格/术语）\n")
    for idx, (start, text, reasons) in flags.items():
        print("[%02d] %06.2fs  %s" % (idx, start, text))
        print("     -> " + "；".join(reasons))
    if "--all" in sys.argv:
        print("\n=== 全部字幕 ===")
        for idx, start, end, text in rows:
            print("[%02d] %s" % (idx, text))


if __name__ == "__main__":
    main()
