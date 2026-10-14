# HANDOFF-M1 交接快照

> 上一里程碑：**M0 骨架**（已完成，2026-10-15）
> 下一里程碑：**M1 数据先行**（新发地快照抓取留档）
> 本快照在 M0 出口落盘，含六节：进度+证据 / 待办 / 既定口径 K 清单 / 环境坑 / 命令速查 / 启动提示词

---

## 一、当前进度与证据（M0 出口状态）

| 项 | 状态 | 证据 |
|---|---|---|
| plan/00–06 全部落盘 | ✅ | plan/00（总览+决策记录+台账+里程碑）、02（口径单一定义点）、03（基准设计）、04（测试验收）、05（发布交付）、06（架构选型） |
| 包骨架可安装可跑 | ✅ | `python -m pip install -e .` 成功；`rcc --version` → `recipe-cost-calculator 0.1.0` |
| 端到端通路 | ✅ | `rcc run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json` 出 5 道菜成本与建议售价 |
| 报告双轨 + 字节确定 | ✅ | `--report out/x` 产 `.md` + `.xlsx`；两次导出 sha256 逐个一致（已实测） |
| 零字面量门禁 | ✅ | `tools/check_literals.py` → `LITERAL_GATE_OK: 扫描面 16 个入口，禁用 token 31 个，0 命中`；`--selftest` → `LITERAL_GATE_SELFTEST_OK` |
| 冻结产物位级一致 | ✅ | `gen_params.py --check` → `FROZEN_PARAMS_OK`；`gen_samples.py --check` → `FROZEN_SAMPLES_OK` |
| 基准（规则驱动层） | ✅ | `rcc bench --only boundary` exit 0（29/29）；`--only reconcile` exit 0（4/4）；样本驱动三套件 `not_enabled` + exit 1（**不冒充通过**） |
| 测试全绿（双解释器） | ✅ | `py -3.12` **129 passed**；`py -3.8` **129 passed**（同一 extras 下计数一致） |
| 守门变异验证 | ✅ | 故意把 F1 除改乘 → **7 个测试变红**（含边界套件、selftest、CLI 通路），还原后全绿 |
| EOL 门 + CI 配置 | ✅ | `.gitattributes`（`* text=auto eol=lf` + 快照 `-text`）；`.github/workflows/ci.yml` 三矩阵 + `fetch-depth: 0` + UTF-8 env；CI 门测试全绿 |
| **CI 真实状态** | ⬜ **未接远端，CI 未跑过** | **诚实口径：本地等价校验通过（双解释器 pytest 129 + 门禁 selftest + 生成器 --check），CI 配置已入仓待首推验证** |

### M0 期实测发现的缺陷（都已修，记此防复现）

1. **`Path.write_text(newline=)` 是 Python 3.10+ 参数**——3.12 全绿、3.8 上 36 个测试 TypeError。
   处置：全部改 `open(..., newline="\n")`；并新增 `tests/guards/test_py38_compat.py`（AST 扫描
   已知 3.9+/3.10+ API 误用，在 3.12 上即可提前发现，不必等 CI 的 win-3.8 作业）。
2. **跨盘符 `os.path.relpath` 抛 `ValueError`**（仓库在 D:、pytest tmp 在 C:）——展示路径
   一律走 `try/except ValueError` 回落绝对路径（`benchmark/runner.py::_display_path`）。
3. **OOXML 命名空间声明本身就是 http URI**——对产物全文做 http 子串扫描会误报；
   正确判据 = 无 `TargetMode="External"` + **剥掉 XML 标签后的文本内容**无 http。
4. **零字面量门禁首跑就抓出真违规**——`benchmark/runner.py` 里硬编码了 `0.1`/`0.9`/`0.5`
   等业务数值（F3 单调性探针）。已改为从参数包实算端点。**门禁不是摆设**。

### M0 数据底座复核（新增结论，已回写 data/README.md §一之二）

- 历史日期查询参数是 **`pubDateStartTime`/`pubDateEndTime`**；**`startDate`/`endDate` 会被静默忽略**并返回最新一期（若按错参数实现，两期快照会退化成同一期——这是 M1 的头号陷阱）。
- 三日期实测大白菜均价与题面一致：2026-08-06=0.55 / 09-06=0.53 / 10-06=0.40 元/斤。
- 品类 id：1186 蔬菜(132) / 1187 水果(86) / 1189 肉禽蛋(141) / 1190 水产(113)（单日记录数，2026-10-14 实测）。
- `prodName`+`prodPcatid` **组合**过滤有效（题面原注记"prodName 无效"据此勘误）。

---

## 二、下一里程碑待办（M1 数据先行）

**DoD**：≥3 个可区分日期版本的新发地快照抓取留档 + 原始 JSON + 抓取日期 + sha256 台账；`--check` 位级一致。

- [ ] 写 `tools/fetch_snapshots.py`：按 `pubDateStartTime`/`pubDateEndTime` + `prodPcatid` 抓取指定日快照；
      **必须**写同目录 `<name>.meta.json`（`captured_date` / `url` / `unit` / `note`）——引擎的
      `io/snapshot.py::load_snapshot` 缺 meta 即抛错（"未挂来源不得进入计算路径"）。
- [ ] 抓 ≥3 个可区分日期（建议 2026-08-06 / 2026-09-06 / 2026-10-06，与题面实测点对齐）；
      每份登记 `抓取日期 + URL + 原始响应文件名 + sha256` 进 `data/snapshots/README.md` 或台账 JSON。
- [ ] 原始响应**只增不改**；`.gitattributes` 已标 `data/snapshots/** -text`（防 EOL 改写字节）。
- [ ] 抓取器加 `--check`（重抓比对 sha256）或至少"不覆盖已有文件"保护。
- [ ] 写 `data/snapshots/` 台账并回写 plan/00 台账状态列。
- [ ] 用真快照跑一次 `rcc run --with-alert --snapshots <旧> <新>`，确认预警通路端到端出数。
- [ ] 收尾：plan/00·05·06 状态回写 → **写 `plan/HANDOFF-M2.md`** → commit。

**注意**：快照是**真实公开批发价**（非合成），这是题面允许的唯一真实数据面（见 data/README §三）。
演示进货单/BOM 仍必须用合成数据 + 假店名白名单。

---

## 三、既定口径 K 清单（动了会打挂基准/测试，改前先读 plan/02）

| 编号 | 口径 | 位置 | 影响面 |
|---|---|---|---|
| K1 | `net_unit_price = purchase / yield_rate`，`yield_rate ∈ (0,1]`，净料单价**必然 ≥ 毛料单价** | `rules/formulas.py::net_unit_price` | 引擎/基准 B4/测试；方向反了 7 个测试变红 |
| K2 | 损耗率**不是独立参数**，`loss_rate = 1 - yield_rate` 只在呈现层导出 | 同上 | 参数包只存 `yield_rate` |
| K3 | `suggested_price` **先量化**（唯一"量化作用于中间量"的例外），F4 据此反算 | `formulas.suggested_price` | 改则 B5 对账与 F4 往返断言全变 |
| K4 | Decimal 全链路（`parse_float=Decimal`），量化 `ROUND_HALF_UP`；精度约定 `0.01`/`0.0001` **豁免零字面量门禁** | `model.py` | 金额/比率字段禁用 float |
| K5 | 参数三态：`verified` 放行 / `pending` **阻断该 scope** / `input_required` **放行但运行时必索** | `rules/params.py` | 门控语义；改则退出码断言全变 |
| K6 | 门控**按 scope 分**（`cost`/`pricing`/`alert`），**不用整包全 verified 当唯一门** | `rules/params.py::effective_params` | 无关 pending 不得阻断核算路径 |
| K7 | 导入三态 `ok`/`invalid`/`unknown`；**异常行一律列清单**，不静默跳过；`unknown ≠ ok` | `io/csv_import.py` | CLI 退出码 1 语义 |
| K8 | 退出码：0 完成 / 1 降级或未达标或 `not_enabled` / 2 输入不可用或用法错误 / 3 缺可选依赖 | `cli.py` + `benchmark/runner.py` | 锁进测试，重构不漂移 |
| K9 | 基准门槛**随 `data/truth/manifest.json` 下发**（数据非代码），缺失即 `ConfigError`(exit 2)，**不回落默认值** | `benchmark/runner.py::load_thresholds` | 别把门槛写进代码 |
| K10 | 真值对账语义**单一实现源** `benchmark/cases.py`（`observed_nonpass`/`compare_nonpass`），真值库测试与基准共用 | `benchmark/cases.py` | 防双口径漂移 |
| K11 | 报告章节**单一渲染源** `report/sections.py`，MD 与 XLSX 同源 → "内容一致"是结构性质 | `report/sections.py` | 别各写各的组装逻辑 |
| K12 | 机读产物逐字节可复现：`ZIP_STORED` + `create_system=0` + 固定 `date_time=(1980,1,1,0,0,0)` + 条目排序 | `report/export.py` | 引第三方库会破坏此承诺 |
| K13 | 零字面量门禁 token **运行时实算自参数包**，源码零词面；扫描面含 docstring/注释 | `tools/check_literals.py` | 新增交付形态要问"该不该进扫描面" |
| K14 | 确定性生成：**禁 stdlib random、禁 set 迭代序、禁系统时钟**；写盘 `newline="\n"` | `tools/detrng.py` + 各生成器 | 冻结件必须跨机位级一致 |
| K15 | 分层：GUI 只消费 `engine/pipeline`，**零算术、零业务数值、不 import 规则层**（AST 三条齐上） | `tests/guards/test_gates.py` | 三条缺一漏一半 |
| K16 | 所有会打印的可执行入口（CLI + tools 有 main 的脚本）**必须**调 `ensure_utf8_stdio()` | `tests/guards/test_repo_gates.py` | 新增脚本漏守即红 |

**修正纪律**：改口径前先判是"**校验方式不自洽**"（只改谓词）还是"**口径本身定错**"（引擎与真值同源修正，两边一起改）；共同验收门 = `gen_params.py --check` + `gen_samples.py --check` 仍输出 `OK`。

---

## 四、本机环境坑（全部本轮实测）

| 坑 | 症状 | 处置 |
|---|---|---|
| 本机有 **3.8.8 与 3.12.10** 两条通道 | 用 3.12 全绿但 3.8 会挂一批 API | 开工先 `py -0p`；**改动后双解释器都跑**（本轮实测 `Path.write_text(newline=)` 只在 3.8 炸） |
| `python` 可能是商店占位符 | `python -m venv` 失败 | 用 `py -3.12` / `py -3.8`；venv 内用 `python` |
| `core.autocrlf=true`（本机全局） | 新 clone 会把 LF 翻成 CRLF，冻结件 sha256 失配 | `.gitattributes` `* text=auto eol=lf` + 快照 `-text` + EOL 门守门 |
| **git 全局 user.email 是真实个人邮箱** | 发布期脱敏硬门 | M6 用 `git filter-repo` 全历史改写为 GitHub noreply；**未推送窗口零成本** |
| 跨盘符 `os.path.relpath` | `ValueError: path is on mount 'C:', start on 'D:'` | 展示路径 `try/except ValueError` 回落绝对路径 |
| pip 代理污染 | `https://127.0.0.1:xxxx` 连接失败 | `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>` |
| 中文控制台编码 | `UnicodeEncodeError` | 跑脚本一律 `py -X utf8`；入口守卫是另一层（CI/用户机器） |
| pyc 偶发损坏 | 随机 FAIL / unknown opcode | 全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__` |
| pytest `tmp_path` 在 C: 盘 | 与仓库 D: 跨盘 | 同"跨盘符 relpath"条 |
| 测试多时分批跑 | 单批偶发崩溃 | 分批 ≤50、批间 sleep；单批失败只重跑该批 |

**gh 认证状态**（M0 实测）：登录 `yuluo554`，token scopes = `gist, read:org, repo`（**无 workflow**）
→ 建仓必须走 `gh repo create --public ... --source . --remote origin`（**不带 `--push`**）+ 切 SSH
remote 后 push（SSH 不受 OAuth scope 限制，携带 workflow 文件也能触发 CI）。

---

## 五、关键命令速查

```bash
# 双解释器全量测试（收尾必跑）
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest -q
PYTHONDONTWRITEBYTECODE=1 py -3.8  -X utf8 -m pytest -q

# 冻结产物位级一致（改数据后必跑）
py -3.12 -X utf8 tools/gen_params.py --check      # FROZEN_PARAMS_OK
py -3.12 -X utf8 tools/gen_samples.py --check     # FROZEN_SAMPLES_OK

# 零字面量门禁（新增源码后必跑）
py -3.12 -X utf8 tools/check_literals.py --selftest
py -3.12 -X utf8 tools/check_literals.py          # LITERAL_GATE_OK

# 端到端 + 报告
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json --report out/report

# 基准（boundary/reconcile 应 exit 0；样本驱动套件未生成时 exit 1 属明示语义）
py -3.12 -X utf8 -m rcc.cli bench
py -3.12 -X utf8 -m rcc.cli bench --only boundary

# 自检
py -3.12 -X utf8 -m rcc.cli selftest

# 收集数对账（"dev 与干净环境同 extras 下应一致"）
py -3.12 -X utf8 -m pytest --collect-only -q | tail -1

# 重新生成冻结产物（改体例后整目录重生成，禁手改）
py -3.12 -X utf8 tools/gen_params.py
py -3.12 -X utf8 tools/gen_samples.py

# git 链三核对（防 cwd 被劫持）
pwd && git log --oneline -1 && git remote -v
```

---

## 六、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M1.md" 继续完成任务
```

（入库的本文件用相对路径 `plan/HANDOFF-M1.md`；启动命令由用户侧拼绝对路径。）

**M1 目标一句话**：抓 ≥3 期新发地快照并留档（含抓取日期与 sha256），写抓取器与台账，跑通带预警的端到端通路。
