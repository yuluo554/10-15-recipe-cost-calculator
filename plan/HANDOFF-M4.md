# HANDOFF-M4 交接快照

> 上一里程碑：**M3 核算引擎**（已完成，2026-10-15）
> 下一里程碑：**M4 基准**（五套件 B1–B5 达标 / 探活全红通过 / 覆盖度双登记回填 / 门槛随 manifest 下发）
> 本快照在 M3 出口落盘，含六节：进度+证据 / 待办 / 既定口径 K 清单 / 环境坑 / 命令速查 / 启动提示词

---

## 一、当前进度与证据（M3 出口状态）

| 项 | 状态 | 证据 |
|---|---|---|
| **公式原文锚定进 docstring** | ✅ | plan/02 §一 表格的每条公式原文（`net_unit_price = purchase_unit_price / yield_rate` 等 5 条）被 `rules/formulas.py` 对应函数的 docstring **逐字复述**；新守门 `tests/guards/test_formula_single_source.py` 断言两处字符串一致 |
| **守门当场抓出真实缺陷** | ✅ | `alert/threshold.py:101` 原手写 `delta / old_cost` = **第二份 F5 实现**。门红 → 改为调用 `formulas.change_rate`。**实测 `compute_alert` 输出与 M1 记录逐值一致（141 项超阈值 / 4 道菜受影响），证明重构行为等价** |
| **扫描面内无双份公式实现** | ✅ | 同一守门第三条：扫描面内除法 `BinOp` **只准出现在 `formulas.py` 与 `benchmark/runner.py`**（后者按 B5 设计独立重算，属"两条独立路径互验"）。变异验证：在 alert 里手写第二份 F5 → 门红 |
| **零字面量扫描面改整包** | ✅ | 原先逐目录枚举漏掉了 `selftest.py`——它带着手写的公式探针数值（F1 的 `Decimal("0.8")`、F3 的 `Decimal("0.6")`）待在面外。**改为整包 `src/rcc` + `benchmark`**，扫描面从 16 → **24 个入口**；`selftest.py` 的探针数值改为**从参数包实算**（`probe_name = sorted(cost_params)[0]`） |
| **词边界收紧** | ✅ | 尾边界排除 `\.[0-9]`，防版本号 `0.1.0` 被误判成业务数值 `0.1`（扫描面纳入 `__init__.py` 后会命中）。`--selftest` 新增**版本号形态对照**；变异验证：边界退回旧形态 → 门红（版本号刷屏） |
| **门禁仍零命中** | ✅ | `LITERAL_GATE_OK: 扫描面 24 个入口，禁用 token 31 个，0 命中`；`--selftest` → `LITERAL_GATE_SELFTEST_OK` |
| **门控三 scope 各有测试** | ✅ | `tests/unit/test_params_gate.py` 新增参数化：**三个 scope 各自**的 `pending` 阻断（只拦自己，其余两个照常放行）与 `input_required` 放行 |
| **`input_required` 语义修正** | ✅ | plan/02 §三 与 plan/04 §三 早写"**放行门控**，运行时必索"，实现却与 `pending` 同形（整域抛错）——**声明与实现矛盾且过度阻断**。已改：`effective_params` 放行、其 `value` **不进可用集**；索取在取数点（`pipeline.yield_rate_for` 抛 `ParamsInputRequired` → exit 2）。变异验证：值混入可用集 → 门红 |
| **source 门控覆盖每条路径** | ✅ | 三个 scope 各有 `source` 缺失测试；**来源校验移到消费点**（`pipeline._sourced` 显式调 `validate_source`——构造期校验只守"自己造的那一半"，来自解析后外部文件的来源对象不经过 `make_source`）；**`qty` 补挂来源**（plan/02 §二 早已列入参数表，实现却没挂）→ `_load_bom` 文件级挂 `kind=user` |
| **`SourceMissing` 逃逸修复** | ✅ | 原先继承裸 `Exception` → 不被 CLI 的 `except (ParamsError, ValueError)` 捕获 → **逃逸成未捕获 traceback**。改继承 `ValueError` + 机读 `code = "source_missing"`。CLI 集成测试断言 `"Traceback" not in err`。变异验证：退回裸 `Exception` → 门红 |
| **`yield_rate` 越界处置粒度** | ✅ | plan/02 §一 早写"越界一律判该行 `invalid` 并列入清单"，实现却是整单抛错。已改：`compute_costcard` 记行级 issue（`yield_rate_out_of_range`）并**排除整道菜**（成本是各行之和，丢行求和 = 把偏低数字当成对的），其余菜品照常出数 → exit 1；**全部排除** → 成本卡为空 → 文件级 `no_usable_dishes`（line=0，与行级代码不混用，同 K28）→ exit 2。变异验证：改成整单抛错 → 门红 |
| **"缺条目"与"值越界"分开** | ✅ | 缺条目（本不由参数包承载）→ 缺输入 → exit 2；值越界 → 该行 invalid → exit 1。**"没给"与"给了但不对"是两回事** |
| **BOM 形态失败四条** | ✅ | 缺 `dishes` / 空数组 / 菜品缺 `name` / 引用不存在的食材 → 各有单元测试 + CLI 退出码断言（参数化 4 例，全 exit 2） |
| **`target_margin = 1.0` / `old_price = 0`** | ✅ | 单元层断言"拒绝（**非除零**）"；CLI 集成层实测 exit 2。**`old_price = 0` 测试特意选被 BOM 引用的食材（大白菜）置零**——否则 F5 不被触发，测试变成"恒真假门"（此坑已在测试 docstring 登记） |
| **F3 量化例外钉住** | ✅ | 新测试断言 F4 用**挂牌价（量化后）**而非原始比值价；对照测试断言 `dish_cost` 仍**全精度**（量化只作用于对外呈现）。端到端断言 `actual_margin` 由「挂牌价 + 全精度成本」反算 |
| **行级 issue 定位不冒充行号** | ✅ | 成本卡行不是 CSV 行，无行号可指 → `_line_issue` 用 `where = "菜品「X」·食材「Y」"`、`line = None`；`render_issues` 三种定位形态（正整数行号 / line=0 文件级 / None+where 成本卡行）**互不冒充**（同 K28 旨） |
| **报告参数来源块补 `qty`** | ✅ | `report/sections.py` 的来源块新增"用量·<食材>"行——plan/02 §六 要求每项参数的来源都渲染 |
| **来源报错点名参数** | ✅ | `_sourced(source, label)` 的报错含参数名（如"参数「净料率」的来源标记不合法"）——只报"参数未挂来源"会让用户不知道该补哪个（同 K24：错误必须指向正确的对象） |
| **测试全绿（双解释器）** | ✅ | `py -3.12` **255 passed**；`py -3.8` **255 passed**（收集数 255，与开发机一致） |
| 冻结产物位级一致 | ✅ | `gen_params.py --check` → `FROZEN_PARAMS_OK`；`gen_samples.py --check` → `FROZEN_SAMPLES_OK`（本次未改数据，仍绿） |
| 快照位级一致 | ✅ | `fetch_snapshots.py --check` → `SNAPSHOT_CHECK_OK`（3 份快照位级一致，台账与磁盘同源） |
| 脱敏审计 | ✅ | `--selftest` → `AUDIT_SELFTEST_OK`；全模式 → `DESENSITIZE_AUDIT_OK: HARD 0 / REVIEW 0 / advisory 43`（advisory 全为 sha256 长 hex，属文档化功能） |
| 基准（规则驱动层） | ✅ | `bench --only boundary` exit 0；`--only reconcile` exit 0；样本驱动三套件仍 `not_enabled` + exit 1（**不冒充通过**） |
| **变异验证（M3 新增六条）** | ✅ | 逐条实测弄坏被测行为 → 门必红：①公式 docstring 去原文 ②alert 手写第二份 F5 ③门禁边界退回旧形态 ④`input_required` 值混入可用集 ⑤yield 越界改整单抛错 ⑥`SourceMissing` 退回裸 `Exception`。**六条全红**（脚本在临时副本上做，工作树无残留） |
| CI 真实状态 | ⬜ **未接远端，CI 未跑过** | **诚实口径：本地等价校验通过（双解释器 pytest 255 + 门禁 selftest + 生成器 --check + 快照 --check + 六条变异验证），CI 配置已入仓待首推验证** |

### M3 期实测发现的缺陷与陷阱（都已处置，记此防复现）

1. **"口径单一定义点"只有文档声明时不会自己生效**（M3 头号发现）：plan/02 自称"数值口径唯一定义点"且禁手写第二份，但**没有任何机制**阻止第二份实现长出来——`alert/threshold.py` 就手写了 `delta / old_cost`（第二份 F5）。**处置 = 把 plan/02 的公式原文锚定进 docstring + 守门断言同源**，门当场抓出该缺陷。
   **判别口诀：凡是文档声明"只此一处"的事实，都要问一句"有什么机制能让第二处变红"。**
2. **枚举式扫描面的失效模式是"漏一个文件而不自知"**：原零字面量扫描面逐目录枚举 7 个路径，漏掉了 `selftest.py`——它带着手写的公式探针数值（F1/F3 的示例值）待在面外，**悄悄长出了第二份口径**。处置 = 改**整包扫描**（"漏一个"变成"不可能漏"）。
   **这条与上一条同源：白名单式的"我要守哪些"永远会漏；"除了例外全都要守"才不会漏。**
3. **声明与实现矛盾且无人察觉**：`input_required` 的文档（plan/02 §三、plan/04 §三）两处都写"**放行门控**"，实现却与 `pending` 同形（整域抛错）。**矛盾藏了很久**，因为测试也只照实现写（`test_input_required_passes_gate_but_must_be_asked` 断言的是"抛错"——测试名与断言相反）。处置 = 修正实现 + 重写该测试。
   **判别口诀：测试名说"放行"而断言 `pytest.raises` 时，先怀疑实现而非怀疑文档。**
4. **异常基类选错会让"该报的错"变成"崩了"**：`SourceMissing` 继承裸 `Exception`，而 CLI 只 catch `(ParamsError, ValueError)` → 缺 source 的参数包会**逃逸成未捕获 traceback**。plan/04 §三 明明把它列为失败路径（exit 2）。处置 = 改继承 `ValueError`。
   **判别口诀：凡是"明示的失败路径"，都要核对它的异常类型真能被调用方的 catch 列表接住。**
5. **"缺条目"与"值越界"被混为一谈**：净料率缺失（本不由参数包承载）与净料率越界（给了但不对）本是两种故障，原实现都走"整单抛错"。处置 = 分开：缺 → exit 2（缺输入）；越界 → 该行 invalid → exit 1（输入不对但可降级）。
   **这类"两种故障同一种处置"比沉默更坏：用户拿到的处置建议是错的。**
6. **"丢了再求和"是个能自圆其说的错误**：行级问题发生时，可以"丢该行、其余照加"，也可以"整道菜排除"。我选**整道菜排除**——成本是各行之和，丢一行再报一个"看起来完整"的合计，等于把自洽但偏低的数字当成对的。**这条必须登记**，否则下一个人会"修好"成另一种。
7. **测试的"恒真假门"**：`old_price = 0` 的端到端测试若选一个 BOM 不引用的食材置零，F5 根本不被触发，测试就恒绿。处置 = 特意选**被 BOM 引用**的食材（大白菜），并**在测试里断言该前提成立**（`assert target in bom_foods`）。
   **判别口诀：端到端测试里的 `if` 分支（"若触发了则断言 X"）几乎总是假门——把前提断言出来，别让分支吞掉它。**
8. **测试自己也可能编码错误的口径**：我最初写的量化测试断言"F4 用量化后的**成本**"，跑红了——真口径是"只有**价**是量化例外，成本保持全精度"（plan/02 §一 注记 3）。**实现是对的，测试是错的**。处置 = 改测试并补一条对照测试把边界钉住。
   **判别口诀：新写的测试红了，先问"是实现错了还是我的测试错了"，不要直接改实现。**

---

## 二、下一里程碑待办（M4 基准）

**DoD**：五套件基准达标；探活全红通过；覆盖度双登记回填；门槛随 manifest 下发。

**M4 起点状态（已核实，别重做）**：`benchmark/runner.py`（五套件 runner + 门槛随 manifest）与 `benchmark/cases.py`（对账语义单一实现源）**已实现**；`suite_boundary`（B4）与 `suite_reconcile`（B5）**已跑通 exit 0**；`data/truth/manifest.json` 已含五套件门槛。M4 是**补缺口**：

- [ ] **真值库生成器 `tools/gen_truth.py` 尚不存在**（plan/02 §七、plan/03 §二 都引用了它）。B1/B2/B3 三套件读 `data/truth/<suite>.json`，文件不存在时走 `not_enabled`。M4 要写生成器 + 产三份真值库 + `--check` 位级一致守门（`FROZEN_TRUTH_OK`）。
  > **注意 plan/02 §七 与 plan/03 §二 对"共同验收门"的表述不同**：plan/02 写 `gen_truth.py --check` 输出 `FROZEN_TRUTH_OK`，而现有生成器（`gen_params`/`gen_samples`）的守门输出名是各自的 `FROZEN_*_OK`。M4 实现时**统一到 `FROZEN_TRUTH_OK`**（plan/02 是口径来源）并回写 plan/03。
- [ ] **覆盖度双登记回填**：`data/truth/manifest.json` 的 `coverage` 段现全是 0 与占位。M4 要填**分母（形态总数）与分子（采样数）**，只写分子即假覆盖（plan/03 §四）。**每个"达标"分支先问"分母为 0 时它会怎样？"**
- [ ] **探活全红**：plan/03 §七 给每套件列了注入缺陷（B1 篡改真值 / B2 破坏 F1 方向 / B3 篡改排序 / B4 篡改端点 / B5 篡改量化方向）。现只有 B4/B5 的探活在 `tests/benchmark/test_runner.py`（且 B4 的量化探活写得偏弱——只断言了坏实现本身给出不同结果，**没断言套件报未达标**，M4 应补硬）。B1–B3 探活要等真值库生成后补。
- [ ] **门槛随 manifest 下发已实现**，但 `max_duration_seconds` 字段在 `_check_thresholds` 里**未被校验也未使用**——M4 要么实现时长判定，要么显式登记"首期不判时长"（**登记比沉默好**）。
- [ ] **`--only` 部分运行**：现 `partial` 标志已置，但 plan/03 §八 说"部分运行不判定未测指标"——核对实现是否真如此（`run_suites` 只对跑了的套件做门槛判定，已符合）。
- [ ] 收尾：plan/00·03·04·05·06 状态回写 → **写 `plan/HANDOFF-M5.md`** → commit。

**M4 开工前建议先读**：plan/03（全文，尤其 §二 真值语义 / §四 覆盖度双登记 / §五 B4 边界清单 / §七 探活表）、plan/02 §七（口径变更纪律与共同验收门）、`benchmark/runner.py` 的 `_sample_suite` 与 `_suite_not_enabled`。

**M4 无待定夺项**。

---

## 三、既定口径 K 清单（动了会打挂基准/测试，改前先读 plan/02）

| 编号 | 口径 | 位置 | 影响面 |
|---|---|---|---|
| K1 | `net_unit_price = purchase_unit_price / yield_rate`，`yield_rate ∈ (0,1]`，净料单价**必然 ≥ 毛料单价** | `rules/formulas.py::net_unit_price` | 引擎/基准 B4/测试；方向反了 7 个测试变红 |
| K2 | 损耗率**不是独立参数**，`loss_rate = 1 - yield_rate` 只在呈现层导出 | 同上 | 参数包只存 `yield_rate` |
| K3 | `suggested_price` **先量化**（唯一"量化作用于中间量"的例外），F4 据此反算；`dish_cost` 保持全精度 | `formulas.suggested_price` + `pipeline.compute_pricing` | 改则 B5 对账与 F4 往返断言全变；**M3 新增对照测试钉住"成本不量化"** |
| K4 | Decimal 全链路（`parse_float=Decimal`），量化 `ROUND_HALF_UP`；精度约定 `0.01`/`0.0001` **豁免零字面量门禁** | `model.py` | 金额/比率字段禁用 float |
| K5 | 参数三态：`verified` 放行 / `pending` **阻断该 scope** / `input_required` **放行门控、值不进可用集、运行时必索** | `rules/params.py` | 门控语义；改则退出码断言全变。**M3 修正了 input_required 的落地**（原与 pending 同形） |
| K6 | 门控**按 scope 分**（`cost`/`pricing`/`alert`），**不用整包全 verified 当唯一门** | `rules/params.py::effective_params` | 无关 pending 不得阻断核算路径 |
| K7 | 导入三态 `ok`/`invalid`/`unknown`；**异常行一律列清单**，不静默跳过；`unknown ≠ ok` | `io/csv_import.py` | CLI 退出码 1 语义 |
| K8 | 退出码：0 完成 / 1 降级或未达标或 `not_enabled` / 2 输入不可用或用法错误 / 3 缺可选依赖 | `cli.py` + `benchmark/runner.py` | 锁进测试，重构不漂移 |
| K9 | 基准门槛**随 `data/truth/manifest.json` 下发**（数据非代码），缺失即 `ConfigError`(exit 2)，**不回落默认值** | `benchmark/runner.py::load_thresholds` | 别把门槛写进代码 |
| K10 | 真值对账语义**单一实现源** `benchmark/cases.py`（`observed_nonpass`/`compare_nonpass`），真值库测试与基准共用 | `benchmark/cases.py` | 防双口径漂移 |
| K11 | 报告章节**单一渲染源** `report/sections.py`，MD 与 XLSX 同源 → "内容一致"是结构性质 | `report/sections.py` | 别各写各的组装逻辑。**M3 补了 `qty` 来源行** |
| K12 | 机读产物逐字节可复现：`ZIP_STORED` + `create_system=0` + 固定 `date_time=(1980,1,1,0,0,0)` + 条目排序 | `report/export.py` | 引第三方库会破坏此承诺 |
| K13 | 零字面量门禁 token **运行时实算自参数包**，源码零词面；扫描面含 docstring/注释 | `tools/check_literals.py` | **M3 扫描面改整包 `src/rcc` + `benchmark`**（原逐目录枚举漏 `selftest.py`）；词边界尾端排除 `\.[0-9]` |
| K14 | 确定性生成：**禁 stdlib random、禁 set 迭代序、禁系统时钟**；写盘 `newline="\n"` | `tools/detrng.py` + 各生成器 | 冻结件必须跨机位级一致 |
| K15 | 分层：GUI 只消费 `engine/pipeline`，**零算术、零业务数值、不 import 规则层**（AST 三条齐上） | `tests/guards/test_gates.py` | 三条缺一漏一半 |
| K16 | 所有会打印的可执行入口（CLI + tools 有 main 的脚本）**必须**调 `ensure_utf8_stdio()` | `tests/guards/test_repo_gates.py` | 新增脚本漏守即红 |
| K17 | 快照**期间标识 = `data_date`**（数据日），`captured_date` 另存；**两期数据日相同必须拒绝**（exit 2） | `io/snapshot.py` + `engine/pipeline.py::compute_alert` | 改回去 = "两期退化成同一期"回归 |
| K18 | 快照台账与说明**同源渲染**（`ledger.json` + `README.md` 皆由抓取器产出，禁手改）；`--check` 必须**重算** sha256 而非读台账 | `tools/fetch_snapshots.py` | 手改台账/说明即被检出 |
| K19 | 快照原始件 `-text` 冻结；"标了属性"不算数，**须比对工作树与 `git cat-file blob` 的 sha256 相等** | `.gitattributes` + `tests/guards/test_snapshot_ledger.py` | 字节漂移则 sha256 全失配 |
| K20 | 导入**形态失败**（空/坏编码/缺表头/缺必填列/CSV 结构错）→ 抛错 exit 2，**不进逐行清单**；**行级失败** → 进清单 exit 1 | `io/csv_import.py` + `cli.py` | 混淆两者 = 读者去改错的东西 |
| K21 | 进货单**只接受 UTF-8（含 BOM）**，**不做编码猜测**；非 UTF-8 显式拒绝 | `io/csv_import.py::_read_text` | 猜测会把 GBK 静默解成乱码品名 |
| K22 | 两处 `unknown` 行可用性**分开**：表头级（未登记列名）**行可用**；行级（字段数多于表头）**行不入库** | `io/csv_import.py::parse_purchases` | 一律"都丢弃"或"都保留"都是错的 |
| K23 | 食材库同品名**取最后一条价**；重复**必须可观测**（`duplicate_names`，两条通路都列出） | `io/csv_import.py::build_food_library` | 隐性覆盖 = 读者无从知道取舍发生过 |
| K24 | 零可用行报错**必须指向进货单**，不得由下游报"BOM 引用不存在的食材" | `engine/pipeline.py::_require_usable_rows` | 错误指向错误的对象比沉默更坏 |
| K25 | `check` 与 `run` **共用同一分派点**（`csv_import.parse_purchases`）；无第二份列名映射/判定逻辑 | `engine/pipeline.py` + `tests/guards/test_import_dispatch.py` | 三道门：AST + 行为计数 + 结论等同 |
| K26 | 金额列**不校验数值性**（不参与计算）——登记过的口径，非遗漏 | `io/csv_import.py` docstring + 测试 | 若改须同改 docstring 与该测试 |
| K27 | 摘要写"见清单"则**必须真打印清单**（`pipeline.render_issues` 单一渲染源） | `engine/pipeline.py` + `cli.py` | 同"未启用章节显式写出"：承诺可见性就必须真可见 |
| K28 | **行级代码与文件级代码不混用**：文件级结论（零可用行）用 `ISSUE_NO_USABLE_ROWS`（`line=0`），**不得**借用行级 `required_empty` | `io/csv_import.py` + `engine/pipeline.py` | 借行级代码会让下游按行号定位到一个不存在的问题行 |
| **K29（M3 新增）** | **公式原文锚定**：plan/02 §一 的公式原文被 `formulas.py` docstring 逐字复述，守门断言两处一致；**扫描面内同一算式只准一处实现**（例外仅 `benchmark/runner.py`，按 B5 设计独立重算） | `rules/formulas.py` + `tests/guards/test_formula_single_source.py` | 在别处手写同一算式（如 `delta / old_cost`）即红。**别用 `assert "xxx" in source` 式断言——本门断言的是"plan 的原文被复述"** |
| **K30（M3 新增）** | **`input_required` 语义**：放行门控、其 `value` **不进可用集**、运行时由取数点索取（缺失 exit 2）。**与 `pending` 不同形** | `rules/params.py::effective_params` + `pipeline.yield_rate_for` | 改回"整域抛错" = 与 plan/02 §三 声明矛盾 + 过度阻断 |
| **K31（M3 新增）** | **净料率两种故障分开**：**缺条目**（本不由参数包承载）→ exit 2；**值越界** ∉ (0,1] → 该行（该菜）`invalid` 并入清单 → exit 1 | `engine/pipeline.py::compute_costcard` | 混为一谈 = 处置建议是错的 |
| **K32（M3 新增）** | **行级问题的处置粒度 = 整道菜排除**（不是丢该行、其余照加）；**全部菜品都被排除** → `no_usable_dishes`（`line=0`，文件级）→ exit 2 | `engine/pipeline.py::compute_costcard` | 丢行求和 = 把自洽但偏低的数字当成对的。**这条必须登记，否则下一个人会"修好"成另一种** |
| **K33（M3 新增）** | **来源校验在消费点**（`pipeline._sourced` 显式调 `validate_source`），不只在 `make_source` 构造期；`qty` 也必须挂来源 | `engine/pipeline.py` + `_load_bom` | 只守构造期 = 只守了自己造的那一半 |
| **K34（M3 新增）** | `SourceMissing` **继承 `ValueError`**（+ 机读 `code = "source_missing"`），使其被 CLI 的 `except (ParamsError, ValueError)` 接住 → exit 2 | `model.py` | 退回裸 `Exception` = 未捕获 traceback |
| **K35（M3 新增）** | **成本卡行级 issue 的定位用 `where`（菜品·食材）、`line = None`**，与进货单行号、`line=0` 文件级**三种形态互不冒充** | `engine/pipeline.py::_line_issue` + `render_issues` | 硬填行号会让读者去查一个不存在的位置 |

**修正纪律**：改口径前先判是"**校验方式不自洽**"（只改谓词）还是"**口径本身定错**"（引擎与真值同源修正，两边一起改）；共同验收门 = `gen_params.py --check` + `gen_samples.py --check` 仍输出 `OK`（M4 起再加 `gen_truth.py --check` → `FROZEN_TRUTH_OK`）。

---

## 四、本机环境坑（M0/M1/M2/M3 实测）

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
| **管道吞退出码**（M1/M2 两次踩） | `cmd \| head; echo $?` 拿到的是 `head` 的退出码 0 | 核验退出码必须 `> /dev/null 2>&1` **单独跑**，不接管道 |
| **测试夹具与被测对象不匹配**（M2 新记） | 小进货单配大 BOM → 失败原因变成"BOM 缺食材"，**测错了对象** | 小进货单配小 BOM（`_bom_for()` 按需生成） |
| **端到端测试里的 `if` 分支是假门**（M3 新记） | "若触发了则断言 X"→ 未触发时静默通过 | 把前提断言出来（如 `assert target in bom_foods`），别让分支吞掉它 |
| **临时副本做变异验证要清干净**（M3 新记） | 改工作树文件做变异 → 忘了还原就提交 | 变异脚本一律 `shutil.copyfile` 备份 + `finally` 还原；**提交前 `git status` 复核**（M3 实测无 `.bak` 残留） |

**gh 认证状态**（M0 实测）：登录 `yuluo554`，token scopes = `gist, read:org, repo`（**无 workflow**）
→ 建仓必须走 `gh repo create --public ... --source . --remote origin`（**不带 `--push`**）+ 切 SSH
remote 后 push（SSH 不受 OAuth scope 限制，携带 workflow 文件也能触发 CI）。**当前仍无远端。**

---

## 五、关键命令速查

```bash
# 双解释器全量测试（收尾必跑）
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest -q    # 255 passed
PYTHONDONTWRITEBYTECODE=1 py -3.8  -X utf8 -m pytest -q    # 255 passed

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

# 零字面量门禁（新增源码后必跑；M3 起扫描面为整包）
py -3.12 -X utf8 tools/check_literals.py --selftest
py -3.12 -X utf8 tools/check_literals.py          # LITERAL_GATE_OK: 扫描面 24 个入口，0 命中

# 端到端 + 报告（退出码 1 = 有异常行，明示语义）
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json --report out/report

# 带预警端到端（两期真实快照；exit 1 = 有异常行；实测 141 项超阈值、4 道菜受影响）
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json --with-alert --snapshots data/snapshots/xinfadi-2026-08-06.json data/snapshots/xinfadi-2026-10-06.json

# 核算引擎失败路径手验（M3）——形态/输入不可用一律 exit 2
#   target_margin=1.0 / old_price=0 / 净料率缺条目 / source 缺失 / BOM 四条形态失败
#   净料率越界 → exit 1（该菜被排除，其余照常出数）
# 自检
py -3.12 -X utf8 -m rcc.cli selftest

# 收集数对账（"dev 与干净环境同 extras 下应一致"）
py -3.12 -X utf8 -m pytest --collect-only -q | tail -1

# 变异验证（M3 六条已实测全红；改 formulas/params/pipeline/model/check_literals 后可复跑）
# ① formulas docstring 去公式原文 → test_formula_single_source 必红
# ② alert 里手写 delta/old_cost → 同上（扫描面内第二份算式）必红
# ③ check_literals 词边界退回 (?![0-9]) → 门禁因版本号刷屏必红
# ④ params.py 让 input_required 值混入可用集 → test_params_gate 必红
# ⑤ pipeline 把 yield 越界改成整单 raise → test_engine_m3/test_cli 必红
# ⑥ model.py 把 SourceMissing 退回裸 Exception → 两处必红

# 退出码核验（**别接管道**）
py -3.12 -X utf8 -m rcc.cli run --purchases <bad>.csv --bom <bom> > /dev/null 2>&1; echo $?

# git 链三核对（防 cwd 被劫持）
pwd && git log --oneline -1 && git remote -v
```

---

## 六、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M4.md" 继续完成任务
```

（入库的本文件用相对路径 `plan/HANDOFF-M4.md`；启动命令由用户侧拼绝对路径。）

**M4 目标一句话**：写 `tools/gen_truth.py` 产三份真值库（B1/B2/B3）并配 `--check` 位级一致守门，
回填覆盖度双登记（分母+分子），把五套件探活补成"注入缺陷 → 基准必报未达标"的硬断言，
使五套件从"规则驱动层已达标"推进到"全部达标 + 探活全红 + 覆盖度如实声明"。
