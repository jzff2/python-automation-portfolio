# -*- coding: utf-8 -*-
"""测试辅助：把源码复制进临时沙箱再执行，源码零改动、数据不落仓库。"""
import os
import sys
import shutil
import tempfile
import subprocess
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
PY = sys.executable


def sandbox(*files):
    """复制指定源码到临时目录，返回目录路径。"""
    d = tempfile.mkdtemp(prefix="portfolio-test-")
    for f in files:
        shutil.copy2(os.path.join(SRC, f), os.path.join(d, f))
    return d


def run(d, script, *args):
    """在沙箱中以子进程运行脚本，返回 (退出码, 合并输出)。"""
    p = subprocess.run(
        [PY, os.path.join(d, script)] + list(args),
        cwd=d, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def write(d, name, text):
    """往沙箱写文本文件。"""
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        f.write(text)


def load_module(d, name):
    """从沙箱目录加载模块，使模块级数据路径指向沙箱而非仓库。"""
    spec = importlib.util.spec_from_file_location(name, os.path.join(d, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
