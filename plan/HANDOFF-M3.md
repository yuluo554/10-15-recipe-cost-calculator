# HANDOFF-M3 交接快照

> 上一里程碑：**M2 导入**（已完成，2026-10-15）
> 下一里程碑：**M3 核算引擎**（净料换算 F1 / BOM 汇总 F2 / 毛利率 F3·F4 / 口径单一定义落地 / 参数门控三 scope）
> 本快照在 M2 出口落盘，含六节：进度+证据 / 待办 / 既定口径 K 清单 / 环境坑 / 命令速查 / 启动提示词

---

## 一、当前进度与证据（M2 出口状态）

| 项 | 状态 | 证据 |
|---|---|---|
| **Excel 归属定夺** | ✅ | **CSV 首期，Excel 列扩展项**（用户明确选择）。口径冲突（README"仅 CSV" vs plan/00·01"CSV/Excel"）已归一：回写 plan/00 决策记录 + plan/01 模块①·扩展项 + plan/06 决策记录 + README 限制节 |
| **三态语义补齐** | ✅ | plan/02 §5 早写"整行结构不可解析"但实现未落地 → 已补。**两处 unknown 的行可用性是分开口径**：表头级（未登记列名）**行仍可用**；行级（字段数多于表头）**行不入库**（列对齐不可信） |
| **三态显式测试矩阵** | ✅ | `tests/unit/test_csv_import.py` **39 项**（原 12 项）。矩阵每格具用例：`ok` / `invalid`（5 种触发参数化）/ `unknown` 三触发 / 计数一致性 |
| **异常代码机读化** | ✅ | 6 个 `ISSUE_*` 常量（`mapping_uncertain` / `structure_unparsable` / `required_empty` / `not_numeric` / `negative` / `unit_unregistered`）；测试断言 code 而非匹配中文散文 |
| **失败路径补齐** | ✅ | 形态失败（空文件 / 仅空白 / 只有表头 / 缺必填列 / 非 UTF-8 / CSV 结构错）→ 一律抛错（exit 2），**不进逐行清单**。CLI 集成测试参数化覆盖 5 类 |
| **编码口径** | ✅ | **只接受 UTF-8（含 BOM，`utf-8-sig`），不做编码猜测**。GBK 件实测被拒并报"不是 UTF-8"；附反面自证测试（断言 GBK 字节确实无法被 UTF-8 读成原字） |
| **BOM 表头** | ✅ | `utf-8-sig` 吃下 BOM，实测"日期"列名未被 BOM 污染、未变未登记列 |
| **列顺序 / 多余空列** | ✅ | 列乱序按列名映射（实测单价未与金额串位）；无列名的多余空列不产生 unknown |
| **`check`/`run` 共用分派点** | ✅ | 新守门 `tests/guards/test_import_dispatch.py` **8 项**，三层判据：①AST 断言 `pipeline` 内无第二份列名映射；②**行为计数探针**断言两条通路真调用同一 `parse_purchases`；③同一输入下两通路异常清单**逐条等同** |
| **分派点门变异验证** | ✅ | 实测两次：①在 `pipeline` 塞第二份列名映射 → 门红；②让 `check` 悄悄过滤 `structure_unparsable` → 门红。已恢复并复验绿 |
| **食材库语义登记** | ✅ | `build_food_library` docstring 显式写"**取最后一条价**"（同品名多批次进货的取舍口径，不写就是隐性第二口径）；新增 `duplicate_names()` 使重复**可观测**，`run`/`check` 输出都列出重复品名 |
| **零可用行报错指向** | ✅ | 新 `pipeline._require_usable_rows`：全行异常时 `run` exit 2 且点名"进货单无任何可用行"；`check` 记为 issue 并显式声明"已跳过 BOM 交叉核对"。**修复了"把进货单的问题报成 BOM 的问题"**（原会报"BOM 引用了食材库中不存在的食材"，把用户引向改错文件） |
| **异常清单真被打印** | ✅ | 实测缺陷：非 JSON 通路输出只有摘要 + "异常 N 条（见清单）"，而清单**从未打印**（摘要指向空处）。处置 = `pipeline.render_issues()` 单一渲染源，`run` 与 `check` 两条非 JSON 通路都调它 |
| **样例扩到覆盖全部异常类** | ✅ | `gen_samples.py` 注入从 2 条扩到 6 条（invalid 三种 + unknown 表头级/行级/单位）+ 1 条**重复品名**（非异常，演示取舍）；走生成器整目录重生成，`--check` → `FROZEN_SAMPLES_OK` |
| **样例覆盖度锁进测试** | ✅ | `test_demo_sample_covers_every_state_and_anomaly_class` 断言 6 个异常码全在样例里 + 有重复品名 → **删掉任一注入行即变红**（样例不会被悄悄简化成"只有正常行"） |
| **样例可复现性** | ✅ | `test_demo_sample_is_reproducible_by_generator` 断言磁盘样例 == 生成器输出（防手改）；CLI 集成测试断言同输入两次 JSON 输出**逐字节一致**、异常清单两次**逐条相同** |
| **金额列口径** | ✅ | **首期不校验数值性**（不参与计算）——显式登记为口径而非遗漏，配测试 `test_non_numeric_amount_does_not_invalidate_row` |
| **测试全绿（双解释器）** | ✅ | `py -3.12` **201 passed**；`py -3.8` **201 passed**（同 extras 下计数一致） |
| 零字面量门禁 | ✅ | `LITERAL_GATE_OK: 扫描面 16 个入口，禁用 token 31 个，0 命中`；`--selftest` → `LITERAL_GATE_SELFTEST_OK` |
| 冻结产物位级一致 | ✅ | `gen_params.py --check` → `FROZEN_PARAMS_OK`；`gen_samples.py --check` → `FROZEN_SAMPLES_OK` |
| 快照位级一致 + 自检 | ✅ | `fetch_snapshots.py --check` → `SNAPSHOT_CHECK_OK`；`--selftest` → `SNAPSHOT_SELFTEST_OK` |
| 脱敏审计 | ✅ | `--selftest` → `AUDIT_SELFTEST_OK`；全模式 → `DESENSITIZE_AUDIT_OK: HARD 0 / REVIEW 0 / advisory 33`（advisory 全为台账/提交信息里的 sha256 长 hex，属文档化功能） |
| 基准（规则驱动层） | ✅ | `bench --only boundary` exit 0；`--only reconcile` exit 0；样本驱动三套件仍 `not_enabled` + exit 1（**不冒充通过**） |
| **干净环境验证（M2）** | ✅ | `git ls-files` 导出树（无 `.git`）+ 全新 `py -3.12 -m venv` + `pip install -e ".[dev]"`：**199 passed / 2 skipped**（2 项为无 `.git` 的声明式跳过，收集数 201 与开发机一致）。**README 九步退出码全部符合明示语义**（`run`/`alert run`/`report`/`check`/`bench` = 1、`selftest` = 0、`gui` = 3）；`fetch_snapshots --check/--selftest` 在导出树里均 exit 0；M2 新失败路径在导出树里实测 `run 空文件` = 2、`check 全行异常` = 1、带 BOM 表头 = 0 |
| CI 真实状态 | ⬜ **未接远端，CI 未跑过** | **诚实口径：本地等价校验通过（双解释器 pytest 201 + 门禁 selftest + 生成器 --check + 快照 --check + 干净环境逐条），CI 配置已入仓待首推验证** |

### M2 期实测发现的缺陷与陷阱（都已处置，记此防复现）

1. **异常清单"承诺了却从未打印"**（M2 头号缺陷）：非 JSON 通路的输出是摘要 + "异常 N 条（**见清单**，未静默跳过）"，而清单**只存在于返回的 dict 里**，`--json` 之外根本看不到。这是"承诺可见性"与"实际可见性"脱节——**摘要指向空处**。处置 = `pipeline.render_issues()` 单一渲染源 + 两条通路都调。
   **判别口诀：凡是文案里出现"见 X"的地方，都要问一句"X 真的被输出了吗"。**
2. **错误指向错误的对象**：全行异常 → 食材库为空 → 下游报"菜品「醋溜白菜」引用了食材库中不存在的食材: 大白菜"，**报错指向 BOM**。用户会照着提示去改 BOM，而真因在进货单。处置 = `_require_usable_rows`（run exit 2 点名进货单；check 记 issue + 显式声明跳过 BOM 核对）。
   **这类故障比沉默更坏：沉默只是没帮上，误导是帮倒忙。**
3. **测试夹具与被测对象不匹配导致的假红**：我最初用小进货单（1-2 行）配仓库样例 BOM（引用 10 种食材），于是三个测试的失败原因都变成"BOM 引用了库里没有的食材"——**测的就不是被测的那件事了**。处置 = 新增 `_bom_for()` 按需生成最小 BOM，**小进货单配小 BOM**。
4. **结构错行的处置有两种自圆其说的选项**：字段数多于表头时，多余值会进 DictReader 的 `restkey`（`None` 键）。可以"忽略多余值、保留该行"，也可以"整行丢弃"。我选**丢弃**——列对齐已不可信时，把错位的值当成对的比少一行危险。**这条必须登记，否则下一个人会"修好"成另一种。**
5. **GBK 字节在 UTF-8 下会解成乱码但不报错**（取决于字节序列）：实测本机样例 GBK 件被 `utf-8` 硬读时抛 `UnicodeDecodeError`（报错是好事），但**并非所有非 UTF-8 件都会抛**——某些字节序列能被 UTF-8 静默接受成乱码字符。所以"解码报错"不能当编码正确的证据，必须**显式限定编码**（`utf-8-sig`）+ 拒绝其余。
6. **管道吞退出码**（HANDOFF-M2 已记，本次又踩一次）：`cmd 2>&1 | head -2; echo $?` 拿到的是 `head` 的退出码（0），不是 `cmd` 的。**核验退出码必须 `> /dev/null 2>&1` 单独跑**，不接管道。

---

## 二、下一里程碑待办（M3 核算引擎）

**DoD**：公式与注记同源一致（口径单一定义点）；零字面量门禁绿；参数门控按 scope 分作用域。

**M3 起点状态（已核实，别重做）**：`src/rcc/rules/formulas.py`（F1–F6）与 `src/rcc/engine/pipeline.py`（`compute_costcard` / `compute_pricing` / `compute_alert`）**已实现且已被端到端跑通**（M1 带预警端到端 141 项超阈值、4 道菜受影响）。M3 **不是从零写引擎**，是补缺口：

- [ ] **口径单一定义点核对**：plan/02 是全部数值口径的唯一定义点。核对 `formulas.py` 的每个公式与 plan/02 §一 表格**逐条同源**——特别是 F1 的方向注记（净料单价必然 ≥ 毛料单价）在**代码注释与 docstring 里是否也遵守**（plan/02 禁止任何地方手写第二份口径，**含 docstring 与注释里的示例数值**）。
- [ ] **零字面量门禁扫描面复核**：现扫描面含 `engine/` `alert/` `rules/` `cli.py` `report/` `gui/` `benchmark/`（16 个入口）。M3 若新增源码文件，先问"**这个文件里会出现任何禁用数值形态的字符串吗？**"（plan/02 §四）。
- [ ] **参数门控三 scope 复核**：`effective_params(scope)` 的 `cost`/`pricing`/`alert` 各只校验自己引用的条目。核对**不存在"整包全 verified"当唯一门**的残留；核对 `pending` 阻断**该 scope**、`input_required` 放行但运行时必索（缺失 exit 2，**不静默取默认值**）三条语义各有测试。
- [ ] **`source` 门控复核**：每个进入计算路径的参数必须挂 `source`；缺失或 `kind` 未登记 → 引擎入口门控拒绝（`source_missing`）。核对 `validate_source` 在**每条**参数路径上都真被调用（不只是 `make_source` 时校验）。
- [ ] **边界与失败路径**（plan/04 §三）：`target_margin = 1.0` → 拒绝（**非除零**）；`old_price = 0` → 拒绝（**非除零**）；`yield_rate` 越界 `∉ (0,1]` → 该行 `invalid` 并入清单（**不静默取 0/1**）。
- [ ] **BOM 失败路径**：BOM 缺 `dishes` 数组 / 空数组 / 菜品缺 `name` / 引用不存在的食材——四条各有测试与退出码断言。
- [ ] **量化例外核对**：F3 `suggested_price` 是**唯一"量化作用于中间量"的例外**（先 quantize 再据此算 F4）。核对实现与 plan/02 §一之3 的声明一致，且 F4 往返断言在基准 B5 里。
- [ ] 收尾：plan/00·04·05·06 状态回写 → **写 `plan/HANDOFF-M4.md`** → commit。

**M3 开工前建议先读**：plan/02 §一（六条公式 + 5 条语义注记）、plan/02 §三（参数三态 + scope 分作用域）、plan/03（B4/B5 规则驱动与双向对账的设计，M3 实现要能过它）。

**M3 无待定夺项**（M2 已把唯一的 Excel 冲突定夺掉）。

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
| K17 | 快照**期间标识 = `data_date`**（数据日），`captured_date` 另存；**两期数据日相同必须拒绝**（exit 2） | `io/snapshot.py` + `engine/pipeline.py::compute_alert` | 改回去 = "两期退化成同一期"回归 |
| K18 | 快照台账与说明**同源渲染**（`ledger.json` + `README.md` 皆由抓取器产出，禁手改）；`--check` 必须**重算** sha256 而非读台账 | `tools/fetch_snapshots.py` | 手改台账/说明即被检出 |
| K19 | 快照原始件 `-text` 冻结；"标了属性"不算数，**须比对工作树与 `git cat-file blob` 的 sha256 相等** | `.gitattributes` + `tests/guards/test_snapshot_ledger.py` | 字节漂移则 sha256 全失配 |
| **K20（M2 新增）** | 导入**形态失败**（空/坏编码/缺表头/缺必填列/CSV 结构错）→ 抛错 exit 2，**不进逐行清单**；**行级失败** → 进清单 exit 1 | `io/csv_import.py` + `cli.py` | 混淆两者 = 读者去改错的东西 |
| **K21（M2 新增）** | 进货单**只接受 UTF-8（含 BOM）**，**不做编码猜测**；非 UTF-8 显式拒绝 | `io/csv_import.py::_read_text` | 猜测会把 GBK 静默解成乱码品名 |
| **K22（M2 新增）** | 两处 `unknown` 行可用性**分开**：表头级（未登记列名）**行可用**；行级（字段数多于表头）**行不入库** | `io/csv_import.py::parse_purchases` | 一律"都丢弃"或"都保留"都是错的 |
| **K23（M2 新增）** | 食材库同品名**取最后一条价**；重复**必须可观测**（`duplicate_names`，两条通路都列出） | `io/csv_import.py::build_food_library` | 隐性覆盖 = 读者无从知道取舍发生过 |
| **K24（M2 新增）** | 零可用行报错**必须指向进货单**，不得由下游报"BOM 引用不存在的食材" | `engine/pipeline.py::_require_usable_rows` | 错误指向错误的对象比沉默更坏 |
| **K25（M2 新增）** | `check` 与 `run` **共用同一分派点**（`csv_import.parse_purchases`）；无第二份列名映射/判定逻辑 | `engine/pipeline.py` + `tests/guards/test_import_dispatch.py` | 三道门：AST + 行为计数 + 结论等同 |
| **K26（M2 新增）** | 金额列**不校验数值性**（不参与计算）——登记过的口径，非遗漏 | `io/csv_import.py` docstring + 测试 | 若改须同改 docstring 与该测试 |
| **K27（M2 新增）** | 摘要写"见清单"则**必须真打印清单**（`pipeline.render_issues` 单一渲染源） | `engine/pipeline.py` + `cli.py` | 同"未启用章节显式写出"：承诺可见性就必须真可见 |
| **K28（M2 新增）** | **行级代码与文件级代码不混用**：文件级结论（零可用行）用 `ISSUE_NO_USABLE_ROWS`（`line=0`），**不得**借用行级 `required_empty` | `io/csv_import.py` + `engine/pipeline.py` | 借行级代码会让下游按行号定位到一个不存在的问题行 |

**修正纪律**：改口径前先判是"**校验方式不自洽**"（只改谓词）还是"**口径本身定错**"（引擎与真值同源修正，两边一起改）；共同验收门 = `gen_params.py --check` + `gen_samples.py --check` 仍输出 `OK`。

---

## 四、本机环境坑（M0/M1/M2 实测）

| 坑 | 症状 | 处置 |
|---|---|---|
| 本机有 **3.8.8 与 3.12.10** 两条通道 | 用 3.12 全绿但 3.8 会挂一批 API | 开工先 `py -0p`；**改动后双解释器都跑** |
| `python` 可能是商店占位符 | `python -m venv` 失败 | 用 `py -3.12` / `py -3.8`；venv 内用 `python` |
| `core.autocrlf=true`（本机全局） | 新 clone 会把 LF 翻成 CRLF，冻结件 sha256 失配 | `.gitattributes` `* text=auto eol=lf` + 快照 `-text` + EOL 门守门 |
| git 全局 user.email | 发布期脱敏硬门 | **M0 已全历史改写为 noreply**；后续每次 `git commit --amend` 都要显式带 `GIT_COMMITTER_EMAIL=<noreply>` |
| 跨盘符 `os.path.relpath` | `ValueError: path is on mount 'C:', start on 'D:'` | 展示路径 `try/except ValueError` 回落绝对路径 |
| pip 代理污染 | `https://127.0.0.1:xxxx` 连接失败 | `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>` |
| 中文控制台编码 | `UnicodeEncodeError` | 跑脚本一律 `py -X utf8`；入口守卫是另一层 |
| pyc 偶发损坏 | 随机 FAIL / unknown opcode | 全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__` |
| pytest `tmp_path` 在 C: 盘 | 与仓库 D: 跨盘 | 同"跨盘符 relpath"条 |
| 测试多时分批跑 | 单批偶发崩溃 | 分批 ≤50、批间 sleep；单批失败只重跑该批 |
| **新发地接口偶发 503** | 抓取随机失败 | 抓取器内置退避重试（4 次，间隔递增）；批量抓取间 sleep 1s |
| **`out/` 目录在 `.gitignore` 里** | 往 `out/` 写验证产物会"看着成功其实没写" | 验证产物一律写**仓库树外**（`$TEMP`）；仓库内 `out/` 属忽略区 |
| **管道吞退出码**（M2 又踩） | `cmd \| head; echo $?` 拿到的是 `head` 的退出码 0 | 核验退出码必须 `> /dev/null 2>&1` **单独跑**，不接管道 |
| **测试夹具与被测对象不匹配**（M2 新记） | 小进货单配大 BOM → 失败原因变成"BOM 缺食材"，**测错了对象** | 小进货单配小 BOM（`_bom_for()` 按需生成） |

**gh 认证状态**（M0 实测）：登录 `yuluo554`，token scopes = `gist, read:org, repo`（**无 workflow**）
→ 建仓必须走 `gh repo create --public ... --source . --remote origin`（**不带 `--push`**）+ 切 SSH
remote 后 push（SSH 不受 OAuth scope 限制，携带 workflow 文件也能触发 CI）。**当前仍无远端。**

---

## 五、关键命令速查

```bash
# 双解释器全量测试（收尾必跑）
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest -q    # 201 passed
PYTHONDONTWRITEBYTECODE=1 py -3.8  -X utf8 -m pytest -q    # 201 passed

# 脱敏审计（新增文档/提交前必跑；**单独跑，别接管道**）
py -3.12 -X utf8 tools/audit_desensitize.py --selftest     # AUDIT_SELFTEST_OK
py -3.12 -X utf8 tools/audit_desensitize.py                # DESENSITIZE_AUDIT_OK

# 冻结产物位级一致（改数据后必跑）
py -3.12 -X utf8 tools/gen_params.py --check      # FROZEN_PARAMS_OK
py -3.12 -X utf8 tools/gen_samples.py --check     # FROZEN_SAMPLES_OK

# 快照位级一致 + 自检（离线；改了快照/台账必跑）
py -3.12 -X utf8 tools/fetch_snapshots.py --check       # SNAPSHOT_CHECK_OK
py -3.12 -X utf8 tools/fetch_snapshots.py --selftest    # SNAPSHOT_SELFTEST_OK
py -3.12 -X utf8 tools/fetch_snapshots.py --refetch-check   # 联网重抓比对（SNAPSHOT_REFETCH_OK）

# 零字面量门禁（新增源码后必跑）
py -3.12 -X utf8 tools/check_literals.py --selftest
py -3.12 -X utf8 tools/check_literals.py          # LITERAL_GATE_OK

# 端到端 + 报告（退出码 1 = 有异常行，明示语义）
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json --report out/report

# 带预警端到端（两期真实快照；exit 1 = 有异常行）
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json --with-alert --snapshots data/snapshots/xinfadi-2026-08-06.json data/snapshots/xinfadi-2026-10-06.json

# 导入三态/失败路径手验（M2）
py -3.12 -X utf8 -m rcc.cli check --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json   # exit 1 + 逐条清单
# 形态失败一律 exit 2：空文件 / 仅空白 / 只有表头 / 缺必填列 / 非 UTF-8

# 基准（boundary/reconcile 应 exit 0；样本驱动套件未生成时 exit 1 属明示语义）
py -3.12 -X utf8 -m rcc.cli bench
py -3.12 -X utf8 -m rcc.cli bench --only boundary

# 自检
py -3.12 -X utf8 -m rcc.cli selftest

# 收集数对账（"dev 与干净环境同 extras 下应一致"）
py -3.12 -X utf8 -m pytest --collect-only -q | tail -1

# 分派点门变异验证（实测两次已通过；改 pipeline 后可复跑）
# ① 在 pipeline 塞 SECOND_COLUMN_MAP → test_pipeline_has_no_second_column_map 必红
# ② 让 check 过滤 structure_unparsable → test_both_paths_agree_on_three_state_verdict 必红

# 退出码核验（**别接管道**）
py -3.12 -X utf8 -m rcc.cli run --purchases <bad>.csv --bom <bom> > /dev/null 2>&1; echo $?

# git 链三核对（防 cwd 被劫持）
pwd && git log --oneline -1 && git remote -v
```

---

## 六、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M3.md" 继续完成任务
```

（入库的本文件用相对路径 `plan/HANDOFF-M3.md`；启动命令由用户侧拼绝对路径。）

**M3 目标一句话**：把核算引擎的公式与注记锁成"口径单一定义点"（plan/02 是唯一定义点，含 docstring/注释禁手写第二份口径），
并复核参数门控按 `cost`/`pricing`/`alert` 三 scope 分作用域——引擎本体已实现且端到端跑通，是补缺口与加固，不是重写。
