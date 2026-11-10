# -*- coding: utf-8 -*-
"""
大肥鱼的小屋 —— 真·桌面壁纸启动器（supervisor 自愈版）

把 fish-house 的独立壁纸页 (http://127.0.0.1:6185/fish_house/index.html)
用 WebView2 渲染，并塞进 Windows 桌面背景层（WorkerW），实现
「铺满整屏 + 盖在桌面图标后面」的真·壁纸效果。

架构（自愈关键）：
- 本脚本被 VBS 拉起时，作为【监管进程 supervisor】运行：
  等待 AstrBot 服务 -> 循环拉起【子进程 child】-> 子进程退出后，
  若收到退出标记就一起退，否则 3 秒后自动重生子进程。
- 子进程负责真正创建 WebView2 窗口、挂到桌面背景层、轮询铺满全屏；
  它一旦因 Explorer 重启 / WebView2 崩溃而挂掉，监管进程会把它拉起来，
  壁纸自动恢复，无需人工重跑 VBS。
- 退出热键 Ctrl+Alt+Q：由子进程捕获，写退出标记文件后自杀；
  监管进程看到标记即退出循环，整体关闭（含开机自启场景下的干净退出）。

Win32 挂背景层要点：
- 本机 Win11 布局有 20+ 顶层 WorkerW（多为 Chrome/Edge/Electron 建），
  「没有 SHELLDLL_DefView 子窗口」的判法会抓错窗口；
  正确做法是选【父窗口是 Progman】的那个 WorkerW（承载图标层的桌面容器）。
"""
import os
import sys
import time
import threading
import subprocess
import urllib.request
import ctypes
from ctypes import wintypes

import webview

FISH_URL = "http://127.0.0.1:6185/fish_house/index.html"
POLL_TIMEOUT = 300                # 等服务起来的最长时间（秒）
WALLPAPER_MODE = True             # True=铺满全屏盖在图标后；False=浮动小桌宠
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEBUG_LOG = os.path.join(BASE_DIR, "fish_pet_debug.log")
QUIT_MARKER = os.path.join(BASE_DIR, ".fishpet_quit")   # 热键退出标记
DETACHED = 0x00000008             # CREATE_DETACHED_PROCESS

# ---- Win32 原型声明（HWND 在 64 位下是 64 位，必须显式声明避免截断）----
user32 = ctypes.windll.user32
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                       wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                       ctypes.POINTER(wintypes.DWORD)]
user32.SendMessageTimeoutW.restype = ctypes.c_longlong  # LRESULT (64 位)
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = wintypes.HWND
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.EnumChildWindows.argtypes = [wintypes.HWND, EnumWindowsProc, wintypes.LPARAM]
user32.EnumChildWindows.restype = wintypes.BOOL
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = wintypes.LONG
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWindowLongPtrW.restype = wintypes.LONG
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetParent.restype = wintypes.HWND
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int


def log(msg):
    """pythonw 没有控制台，关键信息写进 debug 日志便于排查。"""
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "  " + msg + "\n")
    except Exception:
        pass


def server_up():
    try:
        with urllib.request.urlopen(FISH_URL, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def wait_server(timeout=POLL_TIMEOUT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server_up():
            return True
        time.sleep(1.5)
    return False


# ===================== 子进程（真正渲染窗口）=====================

class PetApi:
    def close(self):
        try:
            webview.windows[0].destroy()
        except Exception:
            pass
        os._exit(0)


def find_desktop_workerw():
    """找到桌面背景容器 WorkerW：父窗口是 Progman 的那个（Win10/Win11 通用）。"""
    progman = user32.FindWindowW("Progman", None)
    res = wintypes.DWORD(0)
    user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, ctypes.byref(res))

    cand_progman_child = [0]   # 父窗口是 Progman 的 WorkerW（首选）
    cand_no_defview = [0]      # 没有 SHELLDLL_DefView 子窗口的 WorkerW（兜底）

    def enum_cb(h, lp):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if buf.value == "WorkerW":
            if user32.GetParent(h) == progman:
                cand_progman_child[0] = h
            if user32.FindWindowExW(h, None, "SHELLDLL_DefView", None) == 0:
                cand_no_defview[0] = h
        return True

    user32.EnumWindows(EnumWindowsProc(enum_cb), 0)
    return cand_progman_child[0] or cand_no_defview[0]


def find_fish_hwnd():
    """按标题『大肥鱼的小屋』枚举拿到窗口 HWND（pywebview 6.x 无稳定 native_window）。"""
    found = [0]
    def cb(h, l):
        if not user32.IsWindowVisible(h):
            return True
        n = user32.GetWindowTextLengthW(h)
        if n == 0:
            return True
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, b, n + 1)
        if "大肥鱼" in b.value:
            found[0] = h
        return True
    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found[0]


def reparent_behind_desktop(hwnd=None):
    """把窗口挂到桌面背景层，实现「图标后面的真壁纸」。返回是否成功。"""
    try:
        if not hwnd:
            for _ in range(25):
                hwnd = find_fish_hwnd()
                if hwnd:
                    break
                time.sleep(0.2)
        if not hwnd:
            log("找不到鱼窗口 HWND，跳过挂背景层")
            return False
        workerw = find_desktop_workerw()
        if not workerw:
            log("未找到桌面背景 WorkerW，退回普通全屏窗口")
            return False
        WS_CHILD = 0x40000000
        style = user32.GetWindowLongPtrW(hwnd, -16)
        user32.SetWindowLongPtrW(hwnd, -16, style | WS_CHILD)
        user32.SetParent(hwnd, workerw)
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        # HWND_BOTTOM=1, SWP_NOACTIVATE=0x10, SWP_SHOWWINDOW=0x40
        user32.SetWindowPos(hwnd, 1, 0, 0, sw, sh, 0x10 | 0x40)
        log("已挂到桌面背景层 WorkerW=%d，铺满 %dx%d" % (workerw, sw, sh))
        return True
    except Exception as e:
        log("reparent 失败: %r" % e)
        return False


def force_fullscreen(hwnd):
    """无论 pywebview 给了什么尺寸，强制铺满整屏并置底。"""
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    user32.SetWindowPos(hwnd, 1, 0, 0, sw, sh, 0x10 | 0x40)
    return sw, sh


def wallpaper_thread():
    """不依赖 loaded 事件：轮询直到找到鱼窗口，挂到桌面背景层并铺满全屏。"""
    if not WALLPAPER_MODE:
        return
    for i in range(120):  # 最多等 2 分钟（页面/WebView2 冷启动较慢）
        hwnd = find_fish_hwnd()
        if hwnd:
            ok = reparent_behind_desktop(hwnd)
            if ok:
                sw, sh = force_fullscreen(hwnd)
                log("壁纸线程完成：已挂在图标后并铺满 %dx%d" % (sw, sh))
                return
        time.sleep(1)
    hwnd = find_fish_hwnd()
    if hwnd:
        sw, sh = force_fullscreen(hwnd)
        log("兜底：未能挂背景层，已强制全屏铺满 %dx%d（窗口在图标前方）" % (sw, sh))


def hotkey_quit():
    """轮询 Ctrl+Alt+Q 退出（窗口在图标后面，✕ 点不到）。写标记通知监管进程一起退。"""
    VK_CONTROL, VK_MENU, VK_Q = 0x11, 0x12, 0x51
    while True:
        try:
            if (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000 and
                    user32.GetAsyncKeyState(VK_MENU) & 0x8000 and
                    user32.GetAsyncKeyState(VK_Q) & 0x8000):
                try:
                    open(QUIT_MARKER, "w").close()
                except Exception:
                    pass
                try:
                    webview.windows[0].destroy()
                except Exception:
                    pass
                os._exit(0)
        except Exception:
            pass
        time.sleep(0.12)


def run_child():
    """子进程：创建窗口 + 挂背景层 + 热键线程 + 进入 webview 主循环。"""
    log("子进程启动：FISH_CHILD=%r pid=%d 等待 AstrBot 服务 %s" %
        (os.environ.get("FISH_CHILD"), os.getpid(), FISH_URL))
    if not wait_server():
        log("子进程等待超时：AstrBot 5 分钟内未就绪，退出")
        return
    log("服务就绪，创建桌宠窗口")

    api = PetApi()
    if WALLPAPER_MODE:
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        win = webview.create_window(
            "大肥鱼的小屋", url=FISH_URL, frameless=True,
            transparent=True, on_top=False, width=sw, height=sh,
        )
    else:
        w = int(os.environ.get("FISH_PET_W", "1024"))
        h = int(os.environ.get("FISH_PET_H", "720"))
        win = webview.create_window(
            "大肥鱼的小屋", url=FISH_URL, frameless=True,
            transparent=True, on_top=True, width=w, height=h,
        )
    log("窗口对象已创建，准备进入 webview 主循环")

    threading.Thread(target=wallpaper_thread, daemon=True).start()
    threading.Thread(target=hotkey_quit, daemon=True).start()

    webview.start()
    log("子进程 webview.start 返回（窗口已关闭）")


# ===================== 监管进程（看门狗）=====================

def run_supervisor():
    # 单例保护：命名互斥量，防止监管进程多开
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, "Global\\FishHousePetSingleton")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        log("已有桌宠实例在运行，本次退出（防止多开）")
        sys.exit(0)

    log("监管进程启动：开始等待 AstrBot 服务 %s" % FISH_URL)
    if not wait_server():
        log("监管进程等待超时：AstrBot 5 分钟内未就绪，退出")
        sys.exit(1)
    log("监管进程：服务就绪，进入子进程看护循环")

    child = None
    try:
        while True:
            # 热键已请求退出？
            if os.path.exists(QUIT_MARKER):
                try:
                    os.remove(QUIT_MARKER)
                except Exception:
                    pass
                log("监管进程：检测到退出标记，整体退出")
                break

            # 构造子进程环境（剔除 WorkBuddy 注入的 PYTHONPATH，避免污染）
            child_env = dict(os.environ)
            child_env.pop("PYTHONPATH", None)
            child_env["FISH_CHILD"] = "1"
            log("监管进程：准备拉起子进程，FISH_CHILD=%r" % child_env.get("FISH_CHILD"))

            child = subprocess.Popen(
                [sys.executable, os.path.abspath(__file__)],
                env=child_env,
                creationflags=DETACHED,
                close_fds=True,
            )
            log("监管进程：拉起子进程 pid=%d" % child.pid)
            child.wait()
            log("监管进程：子进程退出 code=%s" % child.returncode)
            child = None

            # 子进程退出后再次检查退出标记（热键走的是这条路径）
            if os.path.exists(QUIT_MARKER):
                try:
                    os.remove(QUIT_MARKER)
                except Exception:
                    pass
                log("监管进程：子进程带退出标记退出，整体退出")
                break

            log("监管进程：子进程异常退出，3 秒后自动重生（自愈）")
            time.sleep(3)
    finally:
        # 若因异常跳出且仍有子进程，尝试清理
        if child is not None:
            try:
                child.kill()
            except Exception:
                pass


def main():
    if os.environ.get("FISH_CHILD") == "1":
        run_child()
    else:
        run_supervisor()


if __name__ == "__main__":
    main()
