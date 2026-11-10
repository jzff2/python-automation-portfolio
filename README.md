# Windows / Python 自动化交付件 · Worked Example

一个真实产出、带自动化测试的仓库。模块之间用清楚的接口连，参数外置，每个模块单独能跑、能测、能替换。

## 这个仓库为什么存在

目标岗位（Upwork「Part-time automation developer: Node.js, Python and n8n」）明确要求提交 **one worked example you have already built: a repository or gist with tests**，并写明 *Please do not build anything new for this application*。

所以这里没有为申请临时造的演示项目。它是 2026-11-08 至 11-10 期间实际交付的六个模块的收拢，**业务逻辑零改动**，只补了测试与文档。四个纯标准库模块可完整自动化测试；两个依赖外部环境的模块在文末如实标注未覆盖。

## 目录树

```
portfolio/
├── README.md                  本文件
├── run_tests.py               无第三方依赖的测试入口
├── config.example.json        脱敏后的参数样例（scan / outreach 用）
├── .gitignore                 排除缓存、日志、含第三方 ID 的数据
├── src/
│   ├── jobs.py                工单登记与归因（实收 / 时薪 / 高频问题 / 可复用诊断条目）
│   ├── srt_check.py           AI 字幕验收检查器（只标疑似，不自动改）
│   ├── leads.py               线索发现与过滤（按时间 / 零回复 / 关键词 / 排除词打分）
│   ├── find_customers.py      跨频道找带预算的甲方（付费信号粗筛 + 详情补全）
│   ├── outreach.py            外联草稿、频控发送、成交登记
│   └── fish_pet.pyw           WebView2 桌面壁纸启动器（supervisor 自愈架构）
└── tests/
    ├── _util.py               测试辅助：临时沙箱 + 子进程调用
    ├── test_jobs.py
    ├── test_srt_check.py
    ├── test_leads.py
    └── test_find_customers.py
```

## 模块接口

| 模块 | 输入 | 输出 | 依赖 | 复杂度 / 瓶颈 |
|---|---|---|---|---|
| `jobs.py` | `add k=v...` 或 `report/list/fields` | `jobs.csv`，汇总实收、时薪、高频问题、可复用诊断条目数 | 标准库 | O(n) 扫描；单文件追加写 |
| `srt_check.py` | `.srt` 路径，可选 `--all` | 需人工复核的字幕块清单 | 标准库 | O(行数)；正则逐行，长字幕线性 |
| `leads.py` | `scan/demo/filter/show` | `leads_raw.json` → `leads.json` | 标准库 + 频道 CLI（仅 scan） | scan 为 O(关键词数 × 每页条数) 次网络调用 |
| `find_customers.py` | `scan/demo/show` | `customers_raw.json` | 标准库 + 频道 CLI（仅 scan） | 先粗筛再对候选调详情，接口调用数为 O(候选数) |
| `outreach.py` | `draft/send/close` | `drafts.json`、`sent.json`、`jobs.csv` | 标准库 + 频道 CLI（仅 send） | 逐条发送，间隔与日上限可配 |
| `fish_pet.pyw` | AstrBot 服务 `http://127.0.0.1:6185/fish_house/index.html` | 挂在桌面背景层 WorkerW 的全屏窗口 | pywebview 6.2.1 + 系统 WebView2 + Win32 | 轮询找窗口，最多 120 次 × 1s |

## 快速开始

环境要求：Python 3.11+（开发用 3.13.12），**核心模块零第三方依赖**。

```bash
# 1) 工单记账
python src/jobs.py add 客户=示例 问题=pythonw静默退出 诊断=父窗口被Explorer销毁 实收=300 工时分钟=50 复购=否 渠道=熟人
python src/jobs.py report

# 2) 字幕验收
python src/srt_check.py path/to/subtitle.srt

# 3) 线索流水线（不联网，用内置假数据验证逻辑）
python src/leads.py demo && python src/leads.py filter && python src/leads.py show
python src/find_customers.py demo

# 4) 跑全部测试
python run_tests.py
```

预期输出（实测）：

```
已登记：2026-11-10 | 示例 | 诊断=父窗口被Explorer销毁 | 实收=300
单数=1 实收=300.00 工时=0.8h 时薪=360.00
可复用诊断条目=1 / 1（这些是数字资产原料）
```

`leads.py demo` 的 4 条构造数据里只有 1 条通过过滤（另外 3 条分别因过期、已有回复、命中排除词被淘汰），用于验证打分逻辑而非代表真实命中率。

## 测试

`python run_tests.py` 用 `unittest` 自动发现 `tests/test_*.py`，不需要 pytest。

每个测试把源码复制进临时沙箱再执行子进程，因此：

- 源码零改动即可测真实 CLI 行为；
- 测试产生的 CSV / JSON 全部落在临时目录并在 `tearDown` 清理；
- 不联网、不发私信、不碰真实账号。

覆盖：

| 测试文件 | 断言内容 |
|---|---|
| `test_jobs.py` | 空态、登记与汇总数值（含时薪 300/50min=360）、未知字段拒绝、list 输出、兼容合并 `ledger.csv` |
| `test_srt_check.py` | 数字/金额、英文专名、相邻重复、单行过短、时间轴重叠被标出；正常句不标；坏格式提示 |
| `test_leads.py` | 时间解析、4 类淘汰规则（过期 / 已有回复 / 排除词 / 无关键词）、demo 写文件 |
| `test_find_customers.py` | 付费信号 / 品类词 / 生活噪声三类分类正确、demo 不抛异常 |

## 工程决策与可复现踩坑

这些是实测结论，不是经验之谈：

1. **Win11 桌面背景层的判别**：本机有 20+ 个顶层 `WorkerW`（多为 Chrome/Edge/Electron 创建）。经典做法「选没有 `SHELLDLL_DefView` 子窗口的 WorkerW」会抓到无关窗口；正确规则是 **选父窗口为 `Progman` 的那个**（本机 `WorkerW=68314`）。在 Win10 与 Win11 两种布局都成立。见 `src/fish_pet.pyw:find_desktop_workerw()`。
2. **pywebview 6.2.1 不暴露 `native_window`**，拿 HWND 要用 `EnumWindows` 按窗口标题匹配；`loaded` 事件在该版本下不触发，改用后台轮询线程。见 `find_fish_hwnd()` / `wallpaper_thread()`。
3. **64 位 HWND 必须显式声明 ctypes 的 `argtypes/restype`**；`ctypes.wintypes.LRESULT` 不存在，用 `ctypes.c_longlong`。
4. **进程静默死亡**：Explorer 重启 / WebView2 父窗口销毁会让 pythonw 直接崩且不打日志。解法是 supervisor + child 自愈架构，子进程退出后 3 秒重生，热键退出用标记文件让监管进程一起退。
5. **detached 进程的 `ParentProcessId` 在 wmic 下不可靠**，判断父子关系以进程内记录的 pid 与日志为准。
6. **搜索引擎摘要不可信**：公开接单平台 4 条候选逐页核验全部为 Closed / Completed，摘要却显示「1 分钟前 / Open」。采集流水线必须把逐页状态作为一道独立工序。
7. **AI 字幕约 2% 词错率，错误集中在人名、数字、价格、术语**——所以 `srt_check.py` 只标疑似、不自动改，把判断留在人手里。

## 依赖清单

| 组件 | 版本 / 安装 |
|---|---|
| Python | 3.13.12（`jobs.py` / `srt_check.py` / `leads.py` / `find_customers.py` 纯标准库） |
| pywebview | 6.2.1，仅 `fish_pet.pyw` 需要；`pip install pywebview` |
| WebView2 Runtime | 系统自带（本机 EdgeCore 157.0.4341.42） |
| 腾讯频道 CLI | 仅 `scan` / `send` 需要；路径写在 `config.example.json` |

## 未覆盖 / 未执行

如实列出，避免把演示当实测：

- `fish_pet.pyw` 需要 pywebview + WebView2 + 运行中的 AstrBot 服务，**未纳入自动测试**。本机实测结论为：窗口是 `WorkerW 68314` 的子窗口、`rect=(0,0)-(1920,1080)`、Ctrl+Alt+Q 退出后进程归零。
- `leads.py scan`、`find_customers.py scan`、`outreach.py send --send` 需要外部账号凭据，**测试中未执行**；本仓库只验证其纯逻辑与 dry-run 行为。
- `outreach.py` 的发送开关在 `config.example.json` 中默认为 `false`，默认运行只预演、不发送。
- 真实线索数据（含第三方 `author_id` / `guild_id`）**不放进公开仓库**，仅保留在本机 `leadpipe/customers.json`。本仓库的样例数据全部为构造值。

## 与生产版的差异

`src/` 下**五个文件**是本机生产文件的逐字副本；`leads.py` 有且仅有一处改动，由测试发现：

- **缺陷**：原 `main()` 无条件先读 `config.json`，导致纯查询命令 `show` 在没有配置文件的目录下抛 `FileNotFoundError`。`tests/test_leads.py::test_show_without_filter_does_not_crash` 首次运行即复现。
- **修复**：把配置改为按需加载，`scan` / `demo` / `filter` 各自调用 `load_cfg()`，`show` 不再依赖配置。`scan` / `demo` / `filter` / `do_filter` 等函数体一字未改。
- 生产目录本身有 `config.json`，该缺陷在实际使用中不会触发，因此生产副本未改动；两版差异仅此一处，已在源码注释中标明。

另外两处环境差异：

- `config.example.json` 是脱敏样例，替换了生产配置里的本机绝对路径、真实频道 ID 与报价（示例报价 800，对应公开挂牌可核区间 ¥699–980）；
- 生产目录下另有 `leads_raw.json`、`customers.json` 等运行数据，不入库（见 `.gitignore`）。真实线索含第三方 `author_id` / `guild_id`，不进公开仓库。
