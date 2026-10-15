# HANDOFF-M5 交接快照

> 上一里程碑：**M4 基准**（已完成，2026-10-15）
> 下一里程碑：**M5 交付**（PySide6 exe + CLI 打包 / 用户手册 / 随包白名单 / GUI 分层门禁 / 免安装 exe 本地可用 + 自检断言数据目录落在 exe 目录内）
> 本快照在 M4 出口落盘，含六节：进度+证据 / 待办 / 既定口径 K 清单 / 环境坑 / 命令速查 / 启动提示词

---

## 一、当前进度与证据（M4 出口状态）

| 项 | 状态 | 证据 |
|---|---|---|
| **真值库生成器** | ✅ | 新增 `tools/gen_truth.py`（plan/02 §七、plan/03 §二 引用它）。产 `data/truth/{import,costcard,alert}.json` + `manifest.json`；`--check` → **`FROZEN_TRUTH_OK`**（与 `gen_params`/`gen_samples` 同构：重生成 → 逐字节比对） |
| **真值库只存输入与期望（M4 头号设计）** | ✅ | 原 `_sample_suite` 比对的是真值库**内部**两个冻结字典（`expect` vs `observed`），**从不跑引擎**——"基准全绿"可能只是"基准什么都没查"。M4 把观测移出真值库：`benchmark/cases.py::observe_*` 把用例内联输入**真喂引擎**后实算。守门 `test_truth_libraries_hold_no_frozen_observations` 断言库里没有 `observed` 一类字段；变异验证⑦（把 `observed` 塞回真值库）→ 门红 |
| **结论键自带结论** | ✅ | 键形如 `status:莴笋=up`、`cost:醋溜白菜=3.24`、`issue:L3:not_numeric:invalid`。只把状态当值（`{"status:X":"up"}` vs `"down"`）时**字段名集合相同**，集合对账看不见差异 → **误分类静默通过**。改为键名自带结论后，值的变化即改变键名。对账语义仍单一实现源（`cases.confirmed_keys`/`compare_nonpass`，真值库测试与基准共用） |
| **五套件全部达标** | ✅ | `rcc bench` → **总判: 达标，exit 0**。B1 19 用例/18 形态、B2 15/15、B3 7/7、B4 29 端点、B5 4 项 |
| **覆盖度双登记回填** | ✅ | `manifest.json` 的 `coverage` 段填**分母（形态总数）+ 分子（采样数）+ 采样清单**。B1 18/18、B2 15/15、B3 7/7（B4/B5 规则驱动，写在 plan/03 §四 表内） |
| **分母做不小（M4 机制）** | ✅ | 分母**不由人手写清单决定**：B1/B2 把 `csv_import`/`pipeline` 的 `ISSUE_*` 常量集**运行时反射**出来 + 登记的结构性形态；**分子必须等于分母**，否则生成器直接报错（`TRUTH_FORMS_INCOMPLETE`，exit 1）。守门两条（`test_coverage_denominator_tracks_code_constants` / `..._pipeline_constants`）；变异验证⑤（新增 `ISSUE_*` 代码而无用例）→ 生成器报错 |
| **探活全红（八条变异）** | ✅ | ①F1 改除为乘→B2 红 ②量化 HALF_UP→HALF_DOWN→B4 红 ③排序降序→升序→B3 红 ④篡改真值期望→B1 红 ⑤新增 `ISSUE_*` 而无用例→生成器报错 ⑥删真值库→报未启用+exit 1 ⑦把观测冻进真值库→门红 ⑧时长门槛登记了却不判定→时长测试红。**八条全红**（脚本在仓库树外副本上做，工作树无残留） |
| **B4 量化探活补硬** | ✅ | 原探活只断言"坏实现本身给出不同结果"，**没断言套件报未达标**——那不是探活，是对坏实现的自述。现断言 `suite_boundary(...)["ok"] is False`，并保留"坏实现确实与正本不同"作前提断言（防恒真假门） |
| **时长门槛真参与判定** | ✅ | `max_duration_seconds` 原先**既未校验也未使用**（"登记了却静默不判"）。现按"实测单套件耗时 ≤ 门槛"判定；输出含实测值与"（超时长门槛）"标记。测试用**可控时钟**（`monkeypatch` 时钟）而非真实计时——真实计时下"极快套件"会与门槛 0 撞成"恰好相等"，测出来的是计时抖动不是判定逻辑 |
| **误报率要么实测要么显式声明未测** | ✅ | 样本驱动层（B1–B3）：误报率 = 观测多出的结论键占比（**实测值**）；规则驱动层（B4/B5）无观测键通道、**结构上不可测** → manifest 的 `measures_false_positive` **显式声明未测**（不拿恒 0 冒充达标）。变异验证：给观测器加噪声键 → 误报率 > 0 |
| **门槛字段齐备即配置错误** | ✅ | `_check_thresholds` 现要求五项全在（含 `max_duration_seconds` 与 `measures_false_positive`），缺一即 `ConfigError`(exit 2)，**不回落默认值**；`coverage` 段缺失同样报配置错误 |
| **共同验收门统一** | ✅ | plan/02 §七 与 plan/03 §二 表述不同（`FROZEN_TRUTH_OK` vs 泛指 `OK`）。按"plan/02 是口径来源"统一为三生成器各输出 `FROZEN_PARAMS_OK` / `FROZEN_SAMPLES_OK` / `FROZEN_TRUTH_OK`，回写 plan/03 §十一 |
| **测试全绿（双解释器）** | ✅ | `py -3.12` **287 passed**；`py -3.8` **287 passed**（收集数 287，两边一致） |
| 冻结产物位级一致 | ✅ | `gen_params.py --check` → `FROZEN_PARAMS_OK`；`gen_samples.py --check` → `FROZEN_SAMPLES_OK`；`gen_truth.py --check` → `FROZEN_TRUTH_OK` |
| 快照位级一致 | ✅ | `fetch_snapshots.py --check` → `SNAPSHOT_CHECK_OK`；`--selftest` → `SNAPSHOT_SELFTEST_OK` |
| 零字面量门禁 | ✅ | `--selftest` → `LITERAL_GATE_SELFTEST_OK`；门禁 → `LITERAL_GATE_OK: 扫描面 24 个入口，禁用 token 31 个，0 命中`（新增 `benchmark/cases.py` 已被整包扫描面覆盖，且**无除法 BinOp**——未长出第二份公式实现） |
| 脱敏审计 | ✅ | `--selftest` → `AUDIT_SELFTEST_OK`；全模式 → `DESENSITIZE_AUDIT_OK: HARD 0 / REVIEW 0 / advisory 53`（advisory 全为 sha256 长 hex，属文档化功能） |
| README 逐字执行 | ✅ | 九步实测退出码：`run`/`alert run`/`report`/`check` = 1、**`bench` = 0（M4 起五套件达标，原为 1）**、`selftest` = 0；生成器 `--check` = 0。README 的 `bench` 描述与"评测"表已按末态回写 |
| CI 真实状态 | ⬜ **未接远端，CI 未跑过** | **诚实口径：本地等价校验通过（双解释器 pytest 287 + 门禁 selftest + 三生成器 --check + 快照 --check + 八条变异验证），CI 配置已入仓待首推验证** |

### M4 期实测发现的缺陷与陷阱（都已处置，记此防复现）

1. **"基准全绿"可以是"基准什么都没查"**（M4 头号发现）：原 `_sample_suite` 读真值库里的 `expect` 与 `observed` 两个字典做集合比较——**真值库自带"标准答案"**，于是"达标"只证明"我写进文件的答案等于我自己写进文件的答案"，**引擎怎么改都不会红**。处置 = 观测移出真值库、由观测器运行时实算。
   **判别口诀：凡是"期望"与"观测"来自同一个文件的地方，都要问一句"这个基准有没有在跑被测对象？"**
2. **"把状态当值"会让集合对账失明**：`{"status:X": "up"}` 与 `{"status:X": "down"}` 的**字段名集合相同**——错误方向、误分类全部静默通过。处置 = 结论键自带结论（`status:X=down`），值的变化即改变键名。
   **这条与上一条同源：对账单元选错，门就只是装饰。**
3. **"登记了却静默不判"与沉默同样坏**：`max_duration_seconds` 早就在门槛里，却**没人读它**——门槛表看起来齐备，实际少判一项。处置 = 真判时长；不可测的项（规则驱动层的误报率）**显式声明未测**而不是拿恒 0 顶上。
   **判别口诀：凡是 manifest/配置里"有这一项"的地方，都要问"谁在读它、读不到会怎样"。**
4. **假覆盖的最后一公里是"分母从哪来"**：plan/03 §四 早写"只写分子即假覆盖"，但没规定分母怎么来。处置 = 分母从代码常量集**反射**（新增代码自动进分母）+ **分子必须等于分母否则生成器拒绝产出**。
   **判别口诀：凡"覆盖率 100%"，先问分母是不是被我做小了。**
5. **探活写成"对坏实现的自述"就不算探活**：B4 的量化探活原只断言"坏量化实现给出不同结果"——它证明的是**坏实现确实坏**，不是**基准会报未达标**。处置 = 断言 `suite["ok"] is False`，并把"坏实现确实不同"降为**前提断言**（防恒真假门）。
   **这条是 M3"恒真假门"教训的第二次现形，只不过这次假门藏在探活自身里。**
6. **夹具与被测对象不匹配（M3 老坑重演）**：`cc-yield-out-of-range` 用**单菜 BOM** 配净料率越界——K32 规定"整道菜排除"，于是成本卡为空、走了**另一条形态**（`no_usable_dishes` → exit 2），测出来的是"全部排除"而不是"行级问题但其余照常出数"。处置 = 每条行级问题用例**搭档一道健康菜**（`_with_healthy`），并断言健康菜的成本。
   **端到端用例的夹具必须让"想要的那条分支"真的可达。**
7. **测试断言了自己的实现细节（M4 第二次）**：`cc-qty-zero` 原用**单行** BOM 且 qty=0 → 成本 0 → 建议售价 0 → F4 拒绝（售价须 > 0）。引擎是对的；测的是 F4 端点（B4 已覆盖），不是 F2 的"qty=0 不贡献成本"。处置 = 搭配一个非零用量行。
   **判别口诀：端到端用例红了，先问"是实现错了、还是我的用例没走到我想测的那条路"。**
8. **`_write_text` 默认 UTF-8 会掩盖"非 UTF-8 必须被拒绝"**：B1 有"进货单非 UTF-8 → 形态失败"这条口径，但把文本按 UTF-8 写盘再读，永远走不到拒绝分支。处置 = 用例可声明 `purchases_encoding`，观测器按真实编码落字节。
   **凡"必须拒绝某输入形态"的口径，用例必须真造出那个形态的字节。**
9. **测试自己污染了工作树**：`test_suites_are_evaluated_live_...` 原把 `repo_root` 当 workdir 传给观测器 → 解析器在仓库根写了 `probe.csv`（`git status` 抓到）。处置 = 改传 `tmp_path`；**提交前 `git status` 复核**（这条 M3 就登记过，这次是"测试夹具写盘位置"这个新形态）。
10. **临时副本要能独立跑**：探活/变异测试复制仓库时若漏 `benchmark/` 或 `data/`，报的是"模块找不到/文件缺失"而不是"被测行为变了"——**测试变成测自己的脚本**。处置 = `_probe_repo()` 明确复制 `tools + src + benchmark + data`。

---

## 二、下一里程碑待办（M5 交付）

**DoD**：免安装 exe 本地可用；随包数据可达（**自检断言数据目录落在 exe 目录内**）；GUI 分层门禁绿。

**M5 起点状态（已核实，别重做）**：`src/rcc/packaging.py`（`DATA_WHITELIST` / `find_data_dir` / `build_datas` / `frozen_data_is_inside_dist`）与 `src/rcc/selftest.py` 的**冻结态分支已实现**；`tests/guards/test_gates.py` 的 GUI 三条 AST 门禁、`test_gui_lazy_import_scope_is_covered`、`test_cmd_gui_returns_exit_3_when_dependency_missing` 已绿；`src/rcc/gui/main_window.py` 有骨架（4 个页签：核算/预警/参数/关于）。`data/truth` **已在白名单内**（M4 补齐）。**尚无任何 `.spec` 文件**（`find . -name "*.spec"` 为空），`tests/gui/` 目录**尚不存在**。M5 是**补缺口**：

- [ ] **PyInstaller spec 尚不存在**（plan/05 §一、§四 描述了 onedir 双 exe 形态）。plan/04 §四 的 **G-PACK** 门（"spec 无手写数据路径、无禁区字面；`datas` 只由 `build_datas()` 产生"）**尚无实现**——M5 要写 spec + 落地 G-PACK。
  > **白名单已含四个数据目录**：`data/rules/params.json`、`data/snapshots`、`data/samples`、`data/truth`。**新增目录必须同步登记**，否则构建后断言报"白名单外多余"。
- [ ] **构建产物留底与 sha256 留档**：plan/05 §十 的三件套是 **M6** 的 DoD；M5 只要求"免安装 exe 本地可用 + 自检断言数据目录落在 exe 内"。构建产物**留底仓库树外**（同"验证产物不写仓库内 out/"纪律：`out/` 在 `.gitignore` 里，往那里写会"看着成功其实没写"）。
- [ ] **用户手册**（plan/05 §十一 README 终检清单）：mermaid 架构图 / 快速开始 / 进货单格式（导入契约） / 评测表 / 限制 / 免责声明 / 已知环境问题 / 下载即用。**README 里的每个数字与退出码都要实测过**。
- [ ] **GUI 交互测试尚未建**：plan/04 §一 的测试分层表列了 `tests/gui/`（"offscreen 冒烟 + 分层门禁，PySide6 模块级 `importorskip`"），但**该目录目前不存在**——GUI 侧现有的只有 `tests/guards/test_gates.py` 里的**三条 AST 门禁**（不 import 规则层 / 无算术 / 无业务数值字面量）与 `test_gui_lazy_import_scope_is_covered`（CLI 的 try 覆盖 import 到调用）与 `test_cmd_gui_returns_exit_3_when_dependency_missing`（缺依赖 exit 3）。M5 要补 `tests/gui/`：offscreen 冒烟（`QT_QPA_PLATFORM=offscreen`）+ 保留分层门禁。
  > plan/04 §五 要求"**核心层能力不许整体 skip**"——GUI 交互测试可 `importorskip`，但**分层门禁类测试不依赖重件、必须恒跑**（M0 期已按此形态落在 `tests/guards/`，别搬到 `tests/gui/` 去 skip 掉）。
  > **重件边界提醒**：`import rcc.gui` 本身**永不抛 ImportError**（重件只在函数体内 import），真正的缺依赖异常在 `build_app()`/`run()` 才抛——所以"缺依赖 exit 3"的测试要围绕**调用**而非 import 写（`test_cmd_gui_returns_exit_3_when_dependency_missing` 是现成范例）。
- [ ] **G-README 门（已实现）需在 M5 复跑**：README 每改一次输入路径/退出码就要重跑（`tests/guards/test_repo_gates.py::test_readme_commands_run`）。
- [ ] **冻结态自检行为验证**：`selftest` 的 `frozen_data_inside_dist` 分支在**非冻结态返回 `None`**（不让源码运行被误判 FAIL）。M5 打 exe 后必须**真在冻结态跑一次** `--selftest`，确认该项真的 `True`（本地源码态证明不了它）。
- [ ] 收尾：plan/00·05·06 状态回写 → **写 `plan/HANDOFF-M6.md`** → commit。

**M5 开工前建议先读**：plan/05（全文，尤其 §一 交付形态 / §二 依赖分层 / §九之二 冻结件打包纪律 / §十一 README 终检 / §十二 回写清单）、`src/rcc/packaging.py`（`_frozen_data_candidates` 的三条候选）、`src/rcc/selftest.py`（冻结态分支）。

**M5 无待定夺项**。

---

## 三、既定口径 K 清单（动了会打挂基准/测试，改前先读 plan/02）

| 编号 | 口径 | 位置 | 影响面 |
|---|---|---|---|
| K1 | `net_unit_price = purchase_unit_price / yield_rate`，`yield_rate ∈ (0,1]`，净料单价**必然 ≥ 毛料单价** | `rules/formulas.py::net_unit_price` | 引擎/基准 B4/测试；方向反了 7+ 个测试变红（M4 实测：B2 样本套件也红） |
| K2 | 损耗率**不是独立参数**，`loss_rate = 1 - yield_rate` 只在呈现层导出 | 同上 | 参数包只存 `yield_rate` |
| K3 | `suggested_price` **先量化**（唯一"量化作用于中间量"的例外），F4 据此反算；`dish_cost` 保持全精度 | `formulas.suggested_price` + `pipeline.compute_pricing` | 改则 B5 对账与 F4 往返断言全变 |
| K4 | Decimal 全链路（`parse_float=Decimal`），量化 `ROUND_HALF_UP`；精度约定 `0.01`/`0.0001` **豁免零字面量门禁** | `model.py` | 金额/比率字段禁用 float；量化方向反了 B4 红 |
| K5 | 参数三态：`verified` 放行 / `pending` **阻断该 scope** / `input_required` **放行门控、值不进可用集、运行时必索** | `rules/params.py` | 门控语义；改则退出码断言全变 |
| K6 | 门控**按 scope 分**（`cost`/`pricing`/`alert`） | `rules/params.py::effective_params` | 无关 pending 不得阻断核算路径 |
| K7 | 导入三态 `ok`/`invalid`/`unknown`；**异常行一律列清单**；`unknown ≠ ok` | `io/csv_import.py` | CLI 退出码 1 语义；B1 真值库 19 用例 |
| K8 | 退出码：0 完成 / 1 降级或未达标或 `not_enabled` / 2 输入不可用或用法错误 / 3 缺可选依赖 | `cli.py` + `benchmark/runner.py` | 锁进测试。**M4：`bench` 达标时 = 0**（README 已回写） |
| K9 | 基准门槛**随 `data/truth/manifest.json` 下发**（数据非代码），缺失即 `ConfigError`(exit 2)，**不回落默认值** | `benchmark/runner.py::load_thresholds` | 别把门槛写进代码。**M4 起门槛项含 `max_duration_seconds` 与 `measures_false_positive`，五项缺一即配置错误** |
| K10 | 真值对账语义**单一实现源** `benchmark/cases.py`（`confirmed_keys`/`compare_nonpass`），真值库测试与基准共用 | `benchmark/cases.py` | 防双口径漂移 |
| K11 | 报告章节**单一渲染源** `report/sections.py`，MD 与 XLSX 同源 | `report/sections.py` | 别各写各的组装逻辑 |
| K12 | 机读产物逐字节可复现：`ZIP_STORED` + `create_system=0` + 固定 `date_time` + 条目排序 | `report/export.py` | 引第三方库会破坏此承诺 |
| K13 | 零字面量门禁 token **运行时实算自参数包**，源码零词面；扫描面含 docstring/注释 | `tools/check_literals.py` | 扫描面为**整包 `src/rcc` + `benchmark`**；词边界尾端排除 `\.[0-9]`。**M4 新增 `benchmark/cases.py` 已自动入面（24 个入口）且无除法 BinOp** |
| K14 | 确定性生成：**禁 stdlib random、禁 set 迭代序、禁系统时钟**；写盘 `newline="\n"` | `tools/detrng.py` + 各生成器 | 冻结件必须跨机位级一致。**M4 的 `gen_truth.py` 同受此纪律**（守门 `test_generator_is_deterministic_across_runs`） |
| K15 | 分层：GUI 只消费 `engine/pipeline`，**零算术、零业务数值、不 import 规则层**（AST 三条齐上） | `tests/guards/test_gates.py` | 三条缺一漏一半 |
| K16 | 所有会打印的可执行入口（CLI + tools 有 main 的脚本）**必须**调 `ensure_utf8_stdio()` | `tests/guards/test_repo_gates.py` | 新增脚本漏守即红。**M4 的 `gen_truth.py` 已带守卫**（门自动覆盖新脚本） |
| K17 | 快照**期间标识 = `data_date`**（数据日），两期数据日相同必须拒绝（exit 2） | `io/snapshot.py` + `pipeline.compute_alert` | 改回去 = "两期退化成同一期"回归；B3 有 `same_period_rejected` 用例 |
| K18 | 快照台账与说明**同源渲染**；`--check` 必须**重算** sha256 而非读台账 | `tools/fetch_snapshots.py` | 手改台账/说明即被检出 |
| K19 | 快照原始件 `-text` 冻结；须比对工作树与 `git cat-file blob` 的 sha256 相等 | `.gitattributes` + `tests/guards/test_snapshot_ledger.py` | 字节漂移则 sha256 全失配。**M4：`data/truth/**/*.json -text` 同样已标** |
| K20 | 导入**形态失败** → 抛错 exit 2，**不进逐行清单**；**行级失败** → 进清单 exit 1 | `io/csv_import.py` + `cli.py` | 混淆两者 = 读者去改错的东西；B1 有 5 类形态失败用例 |
| K21 | 进货单**只接受 UTF-8（含 BOM）**，**不做编码猜测** | `io/csv_import.py::_read_text` | B1 用**真 GBK 字节**用例证明它真被拒绝 |
| K22 | 两处 `unknown` 行可用性**分开**：表头级**行可用**；行级**行不入库** | `io/csv_import.py::parse_purchases` | B1 两态各有用例 |
| K23 | 食材库同品名**取最后一条价**；重复**必须可观测** | `io/csv_import.py::build_food_library` | B1 有 `duplicate_names_observable` 用例 |
| K24 | 零可用行报错**必须指向进货单** | `engine/pipeline.py::_require_usable_rows` | B2 有 `no_usable_rows` 用例 |
| K25 | `check` 与 `run` **共用同一分派点** | `engine/pipeline.py` + `tests/guards/test_import_dispatch.py` | 三道门：AST + 行为计数 + 结论等同。**B1 观测器也走这个分派点**，于是"另写一份判定逻辑"会同时让 B1 红 |
| K26 | 金额列**不校验数值性**——登记过的口径，非遗漏 | `io/csv_import.py` docstring + 测试 | B1 有 `amount_not_validated` 用例 |
| K27 | 摘要写"见清单"则**必须真打印清单** | `engine/pipeline.py` + `cli.py` | 同"未启用章节显式写出" |
| K28 | **行级代码与文件级代码不混用**：文件级结论用 `ISSUE_NO_USABLE_ROWS`（`line=0`） | `io/csv_import.py` + `engine/pipeline.py` | 借行级代码会让下游按行号定位到不存在的问题行。**M4：覆盖度形态归属也按这条分**（`no_usable_rows` 归 B2 分母而非 B1） |
| K29 | **公式原文锚定**：plan/02 §一 公式原文被 `formulas.py` docstring 逐字复述；扫描面内同一算式只准一处实现（例外 `benchmark/runner.py`） | `rules/formulas.py` + `tests/guards/test_formula_single_source.py` | 在别处手写同一算式即红 |
| K30 | **`input_required` 语义**：放行门控、值不进可用集、运行时由取数点索取（缺失 exit 2） | `rules/params.py::effective_params` + `pipeline.yield_rate_for` | 改回"整域抛错" = 与 plan/02 §三 矛盾 |
| K31 | **净料率两种故障分开**：**缺条目** → exit 2；**值越界** → 该菜 `invalid` 并入清单 → exit 1 | `engine/pipeline.py::compute_costcard` | 混为一谈 = 处置建议是错的。**B2 两态各有用例** |
| K32 | **行级问题的处置粒度 = 整道菜排除**；**全部菜品都被排除** → `no_usable_dishes`（`line=0`）→ exit 2 | `engine/pipeline.py::compute_costcard` | 丢行求和 = 把自洽但偏低的数字当成对的。**M4 实测坑：行级问题用例必须搭档一道健康菜，否则测的是"全部排除"** |
| K33 | **来源校验在消费点**；`qty` 也必须挂来源 | `engine/pipeline.py` + `_load_bom` | 只守构造期 = 只守了自己造的那一半 |
| K34 | `SourceMissing` **继承 `ValueError`**（+ 机读 `code = "source_missing"`） | `model.py` | 退回裸 `Exception` = 未捕获 traceback |
| K35 | **成本卡行级 issue 用 `where`（菜品·食材）、`line = None`**，三种定位形态互不冒充 | `engine/pipeline.py::_line_issue` + `render_issues` | 硬填行号会让读者去查不存在的位置 |
| **K36（M4 新增）** | **真值库只存输入与期望，观测由观测器运行时实算**；真值库里出现 `observed` 一类字段即红 | `benchmark/cases.py` + `data/truth/*.json` | 冻观测 = 评测退化成"比对两个冻结字典"，**引擎坏掉也照样全绿** |
| **K37（M4 新增）** | **结论键自带结论**（`status:X=down`、`cost:X=3.24`），取值恒 `ok`；对账语义单一实现源 | `benchmark/cases.py::confirmed_keys`/`compare_nonpass` | 状态当值会因字段名集合相同而**看不见误分类** |
| **K38（M4 新增）** | **覆盖度分母从代码常量集反射**（`csv_import`/`pipeline` 的 `ISSUE_*`），**分子必须等于分母**否则生成器报错 | `tools/gen_truth.py` + `manifest.json` | 防"分母被悄悄做小"。新增异常代码必须同时配用例 |
| **K39（M4 新增）** | **门槛五项齐备**（含 `max_duration_seconds` 与 `measures_false_positive`），缺一即 `ConfigError`；**时长真判**；**不可测的误报率显式声明未测** | `benchmark/runner.py` + `manifest.json` | "登记了却静默不判"与沉默同样坏；拿恒 0 比门槛是恒真假门 |
| **K40（M4 新增）** | **探活必须断言"基准报未达标"**，不得只断言"坏实现本身不同" | `tests/benchmark/test_runner.py` | 后者是"对坏实现的自述"，不证明门会红 |

**修正纪律**：改口径前先判是"**校验方式不自洽**"（只改谓词）还是"**口径本身定错**"（引擎与真值同源修正，两边一起改）；共同验收门 = `gen_params.py --check` + `gen_samples.py --check` + `gen_truth.py --check` 三者都输出 `OK`。

---

## 四、本机环境坑（M0–M4 实测）

| 坑 | 症状 | 处置 |
|---|---|---|
| 本机有 **3.8.8 与 3.12.10** 两条通道 | 用 3.12 全绿但 3.8 会挂一批 API | 开工先 `py -0p`；**改动后双解释器都跑** |
| `python` 可能是商店占位符 | `python -m venv` 失败 | 用 `py -3.12` / `py -3.8`；venv 内用 `python` |
| `core.autocrlf=true`（本机全局） | 新 clone 会把 LF 翻成 CRLF，冻结件 sha256 失配 | `.gitattributes` `* text=auto eol=lf` + 快照/真值库 `-text` + EOL 门守门 |
| git 全局 user.email | 发布期脱敏硬门 | **M0 已全历史改写为 noreply**；后续每次 `git commit --amend` 都要显式带 `GIT_COMMITTER_EMAIL=<noreply>` |
| 跨盘符 `os.path.relpath` | `ValueError: path is on mount 'C:', start on 'D:'` | 展示路径 `try/except ValueError` 回落绝对路径 |
| pip 代理污染 | `https://127.0.0.1:xxxx` 连接失败 | `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>` |
| 中文控制台编码 | `UnicodeEncodeError` | 跑脚本一律 `py -X utf8`；入口守卫是另一层 |
| pyc 偶发损坏 | 随机 FAIL / unknown opcode | 全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__` |
| pytest `tmp_path` 在 C: 盘 | 与仓库 D: 跨盘 | 同"跨盘符 relpath"条 |
| 测试多时分批跑 | 单批偶发崩溃 | 分批 ≤50、批间 sleep；单批失败只重跑该批 |
| **新发地接口偶发 503** | 抓取随机失败 | 抓取器内置退避重试（4 次，间隔递增）；批量抓取间 sleep 1s |
| **`out/` 目录在 `.gitignore` 里** | 往 `out/` 写验证产物会"看着成功其实没写" | 验证产物一律写**仓库树外**（`$TEMP`） |
| **管道吞退出码**（M1/M2 两次踩） | `cmd \| head; echo $?` 拿到的是 `head` 的退出码 0 | 核验退出码必须 `> /dev/null 2>&1` **单独跑**，不接管道 |
| **测试夹具与被测对象不匹配**（M2 新记，**M4 第二次踩**） | 单菜 BOM 配行级问题 → 走成"全部排除"，测错了对象 | 行级问题用例**搭档一道健康菜**并断言健康菜成本（`_with_healthy`）；小进货单配小 BOM |
| **端到端测试里的 `if` 分支是假门**（M3 新记） | "若触发了则断言 X"→ 未触发时静默通过 | 把前提断言出来，别让分支吞掉它 |
| **临时副本做变异验证要清干净**（M3 新记） | 改工作树文件做变异 → 忘了还原就提交 | 变异脚本一律在**树外副本**上做；**提交前 `git status` 复核**（M4 实测无残留） |
| **测试夹具写盘位置**（M4 新记） | 观测器把 `repo_root` 当 workdir → 在仓库根写了 `probe.csv` | 观测器只需**临时目录**做收尾清理，不碰仓库根；`git status` 是最后一道网（M4 实测已清） |
| **探活测试的仓库副本要能独立跑**（M4 新记） | 副本漏 `benchmark/` → 报"模块找不到"而非"被测行为变了"，测试变成测自己的脚本 | `_probe_repo()` 明确复制 `tools + src + benchmark + data` |
| **时长/性能断言用真实计时不可靠**（M4 新记） | 门槛 0 与实测 0.0 "恰好相等"，测的是计时抖动 | 用 `monkeypatch` 打桩时钟（每次调用前进固定秒数） |

**gh 认证状态**（M0 实测）：登录 `yuluo554`，token scopes = `gist, read:org, repo`（**无 workflow**）
→ 建仓必须走 `gh repo create --public ... --source . --remote origin`（**不带 `--push`**）+ 切 SSH
remote 后 push（SSH 不受 OAuth scope 限制，携带 workflow 文件也能触发 CI）。**当前仍无远端。**

---

## 五、关键命令速查

```bash
# 双解释器全量测试（收尾必跑）
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest -q    # 287 passed
PYTHONDONTWRITEBYTECODE=1 py -3.8  -X utf8 -m pytest -q    # 287 passed

# 脱敏审计（新增文档/提交前必跑；**单独跑，别接管道**）
py -3.12 -X utf8 tools/audit_desensitize.py --selftest     # AUDIT_SELFTEST_OK
py -3.12 -X utf8 tools/audit_desensitize.py                # DESENSITIZE_AUDIT_OK

# 冻结产物位级一致（改数据后必跑；M4 起三个生成器）
py -3.12 -X utf8 tools/gen_params.py --check      # FROZEN_PARAMS_OK
py -3.12 -X utf8 tools/gen_samples.py --check     # FROZEN_SAMPLES_OK
py -3.12 -X utf8 tools/gen_truth.py --check       # FROZEN_TRUTH_OK

# 快照位级一致 + 自检（离线；改了快照/台账必跑）
py -3.12 -X utf8 tools/fetch_snapshots.py --check       # SNAPSHOT_CHECK_OK
py -3.12 -X utf8 tools/fetch_snapshots.py --selftest    # SNAPSHOT_SELFTEST_OK
py -3.12 -X utf8 tools/fetch_snapshots.py --refetch-check   # 联网重抓比对

# 零字面量门禁（新增源码后必跑；扫描面为整包 src/rcc + benchmark）
py -3.12 -X utf8 tools/check_literals.py --selftest
py -3.12 -X utf8 tools/check_literals.py          # LITERAL_GATE_OK: 24 个入口，0 命中

# 基准（M4：五套件达标 → exit 0）
py -3.12 -X utf8 -m rcc.cli bench                 # 总判: 达标
py -3.12 -X utf8 -m rcc.cli bench --only import   # 部分运行（声明"未测套件的指标不作判定"）
py -3.12 -X utf8 -m rcc.cli bench --json          # 含 duration_seconds / coverage / false_positive_measured

# 端到端 + 报告（退出码 1 = 有异常行，明示语义）
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json --report <树外>/report

# 带预警端到端（两期真实快照；exit 1 = 有异常行）
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json --with-alert --snapshots data/snapshots/xinfadi-2026-08-06.json data/snapshots/xinfadi-2026-10-06.json

# 自检
py -3.12 -X utf8 -m rcc.cli selftest

# 收集数对账（"dev 与干净环境同 extras 下应一致"）
py -3.12 -X utf8 -m pytest --collect-only -q | tail -1    # 287 tests collected

# 变异验证（M4 八条已实测全红；改基准/真值库/门槛后可复跑）
# ① formulas F1 改除为乘 → B2 红
# ② model 量化 HALF_UP→HALF_DOWN → B4 红
# ③ alert 排序降序→升序 → B3 红
# ④ 篡改 data/truth/import.json 的 expect_keys → B1 红
# ⑤ csv_import 新增一个 ISSUE_* 而无用例 → gen_truth.py 报 TRUTH_FORMS_INCOMPLETE
# ⑥ 删 data/truth/import.json → bench 报未启用 + exit 1
# ⑦ 往真值库塞 "observed" 字段 → test_truth_frozen 红
# ⑧ runner 的 threshold_ok 去掉 duration_ok → 时长测试红
# 第八条的脚本形态：把 `and result["duration_ok"]` 从 threshold_ok 表达式里删掉

# 退出码核验（**别接管道**）
py -3.12 -X utf8 -m rcc.cli bench > /dev/null 2>&1; echo $?    # 0
py -3.12 -X utf8 -m rcc.cli bench --only nope > /dev/null 2>&1; echo $?   # 2

# git 链三核对（防 cwd 被劫持）
pwd && git log --oneline -1 && git remote -v
```

---

## 六、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M5.md" 继续完成任务
```

（入库的本文件用相对路径 `plan/HANDOFF-M5.md`；启动命令由用户侧拼绝对路径。）

**M5 目标一句话**：写 PyInstaller spec（`datas` 只由 `build_datas()` 产生，落 G-PACK 门）打 onedir 双 exe，
在**真冻结态**跑 `--selftest` 确认数据目录落在 exe 目录内，补齐用户手册与 GUI 交互测试的分层门禁，
使交付物从"源码态可跑"推进到"免安装 exe 本地可用 + 随包数据可达可自证"。
