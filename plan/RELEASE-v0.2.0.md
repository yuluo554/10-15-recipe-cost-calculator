# RELEASE-v0.2.0 — 发布面回填：随包数据进 wheel + `requires-python` 抬到 3.12

> 上一版：`v0.1.0`（2026-10-15）。
> 触发来源：轨 I（发布物一致性）I-1 —— `v0.1.0` 之后 `src/` 有 **18 个文件**的改动
> （数据迁入包内 + 数据定位改走包内相对路径 + `bench` 的 import 期异常收进退出码契约），
> 这些改动**从未随任何 tag 发布过**。下载 `v0.1.0` 的人拿到的是旧布局。

## 一、相对 v0.1.0 改了什么

| 类别 | 内容 | 用户能否感知 |
|---|---|---|
随包数据 | `data/{rules,samples,snapshots,truth}/` → `src/rcc/data/`（7 个 `R100` 重命名） | **能**：wheel 里**首次**真的带数据 |
`src/rcc/packaging.py` | `find_data_dir()` 新增「**包内优先**」分支（在 `repo_root()` 之前）；新增 `package_data_dir()` / `PACKAGE_DATA_REL` 单一事实源；`build_datas()` 源改为包内目录 | **能**：`pip install` 后 `selftest`/`bench`/`run` 不再 `FileNotFoundError` |
`src/rcc/cli.py` | `cmd_bench` 把 `from benchmark import runner` 的 **import 期** `FileNotFoundError` 收进 `EXIT_USAGE`（原本是裸 traceback + exit 1） | **能（行为修正）**：数据目录缺失时给「输入不可用: …」+ exit 2，而不是 traceback |
`requires-python` | `>=3.8` → **`>=3.12`** | **能（破坏性）**：3.8–3.11 装不上 |
`build-system` | `setuptools>=61` → **`>=77`**（PEP 639 `license` SPDX + `license-files` 的下限） | 构建期 |
测试 | `[dev]` 口径下 **329 收集**（GUI 交互 1 项声明式跳过）；README 目录树那一行有自指守门 | 开发期 |

**没有改**：计算公式、参数包数值（`params.json` 逐字节），基准门槛，退出码语义（0/1/2/3），
CLI 子命令名与旗标，报告格式，exe 的 `_internal/data` 布局。

## 二、为什么版本号是 0.2.0 而不是 0.1.1

`requires-python` 由 3.8 抬到 3.12 是**不兼容变更**：0.x 阶段按 semver 惯例走 minor。
把它当补丁发会让「锁了 0.1.x 的人在 py3.8 上突然装不上」变成静默事故。

## 三、验证

| 项 | 命令 / 位置 | 结果 |
|---|---|---|
| 全量测试（`[dev]` 口径，与 README 计数一致） | `.venv/Scripts/python.exe -m pytest -q` | **329 passed, 1 skipped** |
| 收集数（自指守门） | `--collect-only -q` | **329**（README 写 329，守门绿） |
| EOL 门 | `tests/guards/test_eol_gate.py` | 4 passed（`.gitignore` 曾被本机 CRLF 污染，已按 `git checkout` 恢复为 LF） |
| HEAD 的 CI | `commits/9a87e40/check-runs` | 发布前 `9a87e40` 全 `success` |
| **冻结态验收（中立目录）** | 见 §五 | 四条全过 |

## 四、附件与三方对撞

见 `plan/DIST-sha256-v0.2.0.txt`。

- 附件：`rcc-v0.2.0-win64.zip` — **125,446,906 B** / 182 条目
- sha256 `01050f85e3cedc8ec15b41467744d06a2405f4ec9743f1566d38ac5ad8e44317`
- 四方一致：本地构建 / `gh release download` 落盘件 / GitHub asset digest / Release 正文

**可复现边界（沿用 v0.1.0 的诚实口径，未放松）**：
- ✅ **同 `dist/` → 同 zip 逐字节一致**（`make_release.py` 保证：`ZIP_STORED` + 路径排序 + 固定时间戳）
- ❌ **exe 构建本身不承诺跨机字节一致**（PyInstaller 产物受 bootloader / 依赖版本 / 路径影响）

## 五、冻结态验收（中立目录实测）

在 `%TEMP%\rcc-neutral\`（**仓库树之外**，避免源码态从 CWD 上溯命中仓库 `data/`）：

```
rcc/rcc.exe --version              -> recipe-cost-calculator 0.2.0
rcc/rcc.exe selftest               -> ok=true，逐项全 true（含 frozen_data_inside_dist）
rcc/rcc.exe bench                  -> 总判 达标，exit 0
                                      alert 7/7（1.0）、boundary 29/29、reconcile 4/4
rcc/rcc-gui.exe --selftest <file>  -> exit 0，ok=true
```

## 六、历史结论是否需重跑

**不需要。** 计算公式与参数包数值**逐字节未改**，基准门槛未改，判定结论（五套件全达标）
与 `v0.1.0` 一致。改的是**数据在磁盘上的位置**与**装态能否找到它**，不改变任何判定。
唯一要改的是：如果你按旧文档用 `repo_root()/data` 定位数据，请改用
`rcc.packaging.find_data_dir()`（源码态与装态走同一条路）。
