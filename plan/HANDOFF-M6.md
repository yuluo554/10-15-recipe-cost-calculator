# HANDOFF-M6 交接快照

> 上一里程碑：**M5 交付**（已完成，2026-10-15）
> 下一里程碑：**M6 发布**（GitHub 公开仓库：tag / Release 附产物 + sha256 留档 / `plan/RELEASE-M6.md` 三件套 + 干净环境逐条跑通 + 脱敏四步 + 产物扫描）
> 本快照在 M5 出口落盘，含六节：进度+证据 / 待办 / 既定口径 K 清单 / 环境坑 / 命令速查 / 启动提示词

---

## 一、当前进度与证据（M5 出口状态）

| 项 | 状态 | 证据 |
|---|---|---|
| **PyInstaller onedir 双 exe** | ✅ | 新增 `tools/rcc.spec`（构建规格）+ `tools/launcher_cli.py` / `tools/launcher_gui.py`（冻结态入口）。产物：`rcc.exe`（控制台，1,792,565 B）+ `rcc-gui.exe`（窗口版，1,785,102 B）+ `_internal/`（共 170 个文件，114 MB）。**构建产物留底仓库树外**（`$TEMP/rcc-dist`），树内无 `build/` `dist/` 残留 |
| **免安装 exe 本地可用（DoD）** | ✅ | 冻结态实测（**中立目录**，非仓库树）：`selftest` exit 0、`bench` 总判达标 exit 0、`run`/`check`/带预警 `run`/`--report` 全可达随包数据。带预警实跑 `预警：141 项超阈值`，与源码态一致。**无参数运行 → exit 2**（用法错误语义同源码态） |
| **窗口真起得来（不只自检通路）** | ✅ | `rcc-gui.exe` 与 `rcc.exe gui` 两条通路在 `QT_QPA_PLATFORM=offscreen` 下**都进入 Qt 事件循环**（8 秒超时后仍在运行、无异常输出、须外部终止）。**`rcc.exe gui` 也能起窗口**：静态分析跟进 `cmd_gui` 函数体内的 `from .gui import main_window`，Qt 因此一并入包；两 exe 共享 `_internal/`，磁盘上只有一份 |
| **随包数据可达 + 自检断言（DoD 核心）** | ✅ | 中立目录实测 `rcc.exe selftest` → `frozen=true`、**`frozen_data_inside_dist=true`**（`exe=…\rcc`、`data=…\rcc\_internal\data`）；窗口版 `rcc-gui.exe --selftest out.json` → 同样 `true` + 页签 4 个 + exit 0 |
| **冻结态负向对照**（比"能跑"更强） | ✅ | 删掉 `_internal/data` 后 `selftest` → `data_dir` 与 `params_loadable` 双双 `ok=false`、总判 `ok=false`、**exit 1**。**不静默回落开发机仓库**（`find_data_dir` 冻结分支找不到内嵌数据时返回候选路径交自检判定） |
| **G-PACK 门（plan/04 §四）** | ✅ | 新增 `tests/guards/test_pack_gate.py`（**20 项**）：spec 无手写数据路径 / 无禁区字面（**取 `FORBIDDEN_IN_DIST`，不复制第二份**）+ AST 断言 `DATAS` 由 `build_datas()` 产生 + **核心断言"包内路径 == 仓库内相对路径"** + 白名单对账 + 冻结判定本身的探活 |
| **修复实装期抓出的真实缺陷（M5 头号发现）** | ✅ | `build_datas()` 原对**目录**条目也用 `dirname(rel)` 作目标目录，而 PyInstaller 把目录源的**内容**复制进目标目录 → `data/snapshots/x.json` 被**拍平**成 `data/x.json`，三份快照+样例+真值库全挤进 `data/`。**构建不报任何错、源码态全绿、只有换机器才炸**。处置 = 目录取条目自身、文件取父目录；并把它写进 G-PACK 核心断言 |
| **冻结态数据定位收敛** | ✅ | `benchmark/runner.py::TRUTH_DIR` 与 `cases.snapshot_path()` 原各按 `__file__` 上溯拼 `data/...`（源码态对、冻结态落空）。现分别用 `find_data_dir()/truth` 与 `dirname(find_data_dir())/data/snapshots/…`。`cases.REPO_ROOT` 因此成死代码，已删 |
| **GUI 交互测试层（plan/04 §一，M5 新建）** | ✅ | 新增 `tests/gui/`：`conftest.py`（offscreen **在模块层**设，Qt 只在建 `QApplication` 时读它）+ `test_main_window.py`（窗口装配 / 关于页版本与免责 / `build_app` 返回码 / `--selftest` 通路 / **核心自检不依赖重件**）+ `test_layering_behavior.py`（**不 import 重件、恒跑**：`import rcc.gui` 不得把 PySide6 拉进 `sys.modules`，含机制探活）。**10 项双解释器零 skip** |
| **分层门禁归属（别搬进可 skip 的目录）** | ✅ | AST 三条仍在 `tests/guards/test_gates.py`（恒跑）；行为面在 `tests/gui/test_layering_behavior.py`（也不 import 重件、恒跑）。只有真需要 Qt 的窗口冒烟才模块级跳过 |
| **九条变异验证（全红）** | ✅ | 脚本在**仓库树外副本**上做，工作树无残留：①spec 手写数据路径→红 ②`DATAS` 改字面列举→红 ③`build_datas()` 目录条目退回 `dirname`→红 ④新增未登记数据目录→红 ⑤`frozen_data_is_inside_dist` 恒 True→红 ⑥spec 写**带中文**的禁区路径→红（**第一版判据按 ASCII 筛，把它静默滤掉了——变异验证当场抓出并修掉**）⑦`--selftest` 页签数恒 0→`tests/gui/` 红 ⑧去掉 `setuptools<81` 上界→红 ⑨去掉 `PyInstaller>=6` 下界→红 |
| **用户手册（README）** | ✅ | 新增：打包成免安装 exe 一节（含"为什么要断言数据落在 exe 内"与**中立目录**验收纪律）+ 下载即用一节（附件名/sha256 **留空标 ⬜ 待 M6 回填**，不预填）+ 已知环境问题补窗口版无控制台一条 + 特性补"随包数据可自证"。状态行更新到 M5 |
| **README 退出码全部实测** | ✅ | 源码态复跑：`run`/`alert run`/`check` = **1**、`bench` = **0**、`selftest` = **0**、`bench --only nope` = **2**、`run --purchases nope.csv` = **2**、`gui`（打桩缺 PySide6）= **3**。冻结态 exe 复跑 `run`/`check`/`alert run` 亦 = 1（与源码态一致） |
| **G-README 门复跑** | ✅ | `tests/guards/test_repo_gates.py` 18 项全绿（README 引用的输入路径真存在、由生成器产出、按退出码真跑通） |
| **CI 配置修正（两处真漂移）** | ✅ | ①补 `gen_truth.py --check`（共同验收门是三个生成器，漏掉它 = 真值库无人守）②`bench` 的 `\|\| test $? -eq 1` 改为直接断言 0（M4 起五套件达标）。`tests/guards/test_repo_gates.py` 的 CI 门仍绿 |
| **测试全绿（双解释器）** | ✅ | `py -3.12` **317 passed**；`py -3.8` **317 passed**（收集数 317；M4 为 287，本期 +20 G-PACK +10 GUI）。**M7 复核实测收集数 = 321**（见 §七：本行数字在 M6 之后漂了 +4） |
| **全部既有门复跑** | ✅ | 零字面量 `LITERAL_GATE_OK: 24 个入口，0 命中` + `--selftest` OK；脱敏 `DESENSITIZE_AUDIT_OK: HARD 0 / REVIEW 0 / advisory 63` + `--selftest` OK；三生成器 `--check` 全 OK；快照 `--check` / `--selftest` OK；`bench` 达标 exit 0 |
| **dev-only 环境下的门（模拟 CI）** | ✅ | 用 `sys.meta_path` 拦掉 `PyInstaller`/`PySide6` 后跑 `tests/guards` + `tests/gui`：**115 passed, 1 skipped**（唯一 skip 是窗口冒烟，声明式且合法）。G-PACK **不依赖 PyInstaller**（自己复刻其目录语义），故在只装 `.[dev]` 的 CI 上照跑 |
| CI 真实状态 | ⬜ **未接远端，CI 未跑过** | **诚实口径：本地等价校验通过（双解释器 pytest 317 + 门禁 selftest + 三生成器 --check + 快照 --check + 九条变异验证 + 冻结态 exe 实跑），CI 配置已入仓待首推验证** |

### M5 期实测发现的缺陷与陷阱（都已处置，记此防复现）

1. **"目录条目的目标目录"这个字段在两种源上语义不同**（M5 头号发现）：`build_datas()` 对文件和目录都用 `dirname(rel)`，而 PyInstaller 把目录源的**内容**复制进目标目录——于是三份快照被拍平进 `data/`。**构建成功、源码态全绿、只有"换台机器/中立目录跑"才暴露**。
   **判别口诀：凡"把 X 装进 Y"的代码，先问"X 是文件还是目录？PyInstaller（或任何打包器）对两者的处置一样吗？"**
2. **静态门禁只能证"写法合规"，证不了"装机后可用"**：spec "没有手写数据路径"这条断言，在拍平缺陷存在时**照样是绿的**。故 G-PACK 的核心断言改成了**行为性质**——白名单产物经打包器语义展开后，包内路径必须等于仓库内相对路径；再加一条**负向对照**（删数据后自检必须红）。
   **这条是 M4"活体观测 vs 冻结比对"的同一条教训在打包侧的现形：判据要落在"真跑出来的结果"上，不落在"代码里没写什么"上。**
3. **按 ASCII 筛字面量会留一条带中文的绕过通道**：禁区字面判据第一版只取无空白且 ASCII 的字面量，变异验证里写了 `"plan/00-README总览.md"` ——**中文把它滤掉了，门是全绿的假门**。修法 = 筛"有无空白"而非"是否 ASCII"（说明文案含空格，真路径不含）。
   **凡"过滤噪声"的代码，都要拿一个"该抓但形态怪"的样本试一遍**。
4. **两个 Analysis 会各自收集同一批第三方 datas，只传一个是赌运气**：PyInstaller 的静态分析跟进函数体内 import（`cli → cmd_gui → gui.main_window → PySide6`），故 CLI 与 GUI 两个分析**各自都收集了一份 Qt 插件/翻译**。只传 `a_cli.datas` 实测能出可用包——但那是赌两个分析恰好收集同样的文件。已改为两边都传，去重交给 COLLECT。
5. **入口脚本不能是包内模块**：PyInstaller 把入口当**顶层模块**执行，`src/rcc/cli.py` 里的 `from . import __version__` 当场 ImportError。故入口独立成 `tools/launcher_*.py`（只装编码守卫 + 转交包内 main）。**启动器不承担任何业务判断**——它若长出一份判断，就是第二处口径。
6. **核心自检不许被重件污染**：`--selftest` 若为观测页签而 import GUI，就把 PySide6 拖进 CLI 的导入图，`rcc selftest` 会在没装 gui extra 的机器上挂。处置 = 页签观测落在启动器（`launcher_gui.run_selftest`），核心自检零重件——并配一条测试**在拦掉 PySide6 的子进程里跑核心自检**。
7. **探活自己会写坏**：`tests/gui/test_layering_behavior.py` 的探活用分号拼一段 `-c` 脚本，插值拼出了 `; ;` 语法错误 → 子进程非 0 → `pytest.skip` **静默跳过**，"探活有效"变成一句没证据的话。修法 = 逐行拼装 + 断言子进程 `returncode == 0`（**不许把"探活跑不起来"降级成 skip**）。
8. **`pytest.importorskip` 的 `exc_type` 是 8.2+ 才有**：本项目底线 py3.8 上的 pytest 是 7.4.4——传它 TypeError，不传又在 pytest 9.1+ 变成硬失败。处置 = 手工 `try/except ImportError` + 模块级 `pytest.skip(..., allow_module_level=True)`，两版本语义一致。
9. **`py -3.12 -m PyInstaller --clean` 会先删 dist**：构建若因环境级崩溃失败，dist 就没了。故 `--distpath`/`--workpath` 一律指向**仓库树外**（`$TEMP`），既避开 `out/` 被 gitignore 的"看着成功其实没写"，也保证失败时树外那份还在。
10. **`benchmark/cases.py` 的 `REPO_ROOT` 在改路径解析后成了死代码**：收敛到 `find_data_dir()` 后没人再引用它。**改完路径解析要回头清残留**——留着它下一个人会以为"这里也自己拼路径"。

---

## 二、下一里程碑待办（M6 发布）

**DoD（三件套，缺一即未达成）**：

1. `git tag -a vX.Y.Z`（**打在含完整收尾回写文档的提交上**）+ push tag；
2. `gh release create` 附产物（本地留 release zip 副本 + sha256 留档可复验）：**notes 用 `--notes-file <md>` 传文件** + `--verify-tag`；发布后 `gh release view <tag> --json assets,tagName,isDraft` 核验（`draft=false` + 附件名在列）；**移动已发布 Release 的 tag 会把它打回 draft**，每次移动后复验 `isDraft`；
3. `plan/RELEASE-M6.md`（发布留档，只写**实测到的**，未跑的项留 ⬜ 并说明原因，不留空不预填）。

**另需完成**：

- [ ] **建仓**：`gh repo create --public --description ... --source . --remote origin`（**不带 `--push`**——token 无 workflow scope，带 workflow 文件必被拒、留半失败态）→ 验证 SSH key → `git remote set-url origin git@github.com:<u>/<r>.git` → push 一次成（SSH 不受 OAuth scope 限制，带 workflow 也能触发 CI）；
- [ ] **CI 首跑验收**：按提交逐条配对 `gh run list` 的 `head_sha` + `conclusion`（**对账单位是 push 事件，不是提交数**）；CI 上会跑 `windows×{3.8,3.12} + ubuntu×{3.12}`；**注意 windows 与 ubuntu 的差异**（路径分隔符、控制台编码）；
- [ ] **发布 zip 组装（确定性）**：ASCII 名 zip（`rcc-vX.Y.Z-win64.zip`），`zipfile` 手打：`ZIP_STORED` + 条目**按路径显式 sort**（`os.walk` 顺序不稳定，不排序则两次打包字节不同）+ 固定 `date_time=(1980,1,1,0,0,0)` + `create_system=0`；**两次独立打包逐字节一致**（实测背书）。留档写清：**可复跑的是"同 dist → 同 zip"这步**，**exe 构建本身不承诺跨机字节一致**；
- [ ] **sha256 留档工具化**：`hashlib` 输出**直接重定向生成**，人只写注释行（手工转录 64 位 hex 错一位肉眼不可查）；沿用 `plan/DIST-sha256-M6.txt` 格式；
- [ ] **README 回填**：把"下载即用"一节的 ⬜ 换成真附件名与 sha256；状态行改"✅ vX.Y.Z 已发布"挂 Release 链接；CI 徽章指向发布仓库 Actions；
- [ ] **干净环境验证**（plan/04 §六）：`git archive HEAD | tar -x -C <树外>` → 全新 `py -3.12 -m venv` → **逐条照 README 快速开始执行**并记录退出码成表 → pytest 收集数对账（同 extras 下 dev 与干净环境必须一致，**差异逐项归因到声明式跳过**）；
- [ ] **脱敏四步 + 产物扫描**（plan/05 §八）：文件级/内容级/提交元数据/历史终验三扫（**扫描前先跑阳性对照**验证扫描命令本身有效）；**构建产物本体扫描**（全 dist 树字节读法跑强标记，个人标记按**组合路径签名**匹配，命中串豁免裁决 = "官方原件同串比对"；**留档与扫描器源码不得逐字复述命中串**）；
  > **M5 新增的产物面要一并扫**：`tools/rcc.spec`、`tools/launcher_*.py` 已入仓；冻结态 exe 与 `_internal/` 是**新出现的二进制面**，别只扫源码；
- [ ] **时序纪律**：收官期新增文档（发布留档/交接快照）**先 `git add` 再跑本地审计**（tracked 扫描面只含已跟踪文件）；**"验证描述"是最高频的自命中源**（写"用固定字面值 X 扫描得 0 命中"时 X 本身进了仓库 → 写成"用固定字面值（不在此复述）"）；**CI run 日志是第三个留档面**（守门失败会回显待检文档原文行 → 含敏感回显的失败 run 必须 `gh run delete`）；
- [ ] **"三清"后再切 public**（plan/05 §九）：全历史脱敏三扫 0 硬门 + 坏 blob 修净（`git fsck` 无悬空敏感对象）+ 失败 run 已删。**先清后切是单向门**；
- [ ] **发布物本体验证（最强证据）**：真下载 release 附件 → 下载件 sha256 与留档逐位一致 → **解压中立目录跑冻结态 `--selftest`**。三步齐了才算"发布物本体已验"；
- [ ] 收尾：plan/00·04·05·06 状态回写 → **写 `plan/HANDOFF-M7.md`（若还有后续）或收官快照** → commit → push 等 CI 绿。

**M6 开工前建议先读**：plan/05 全文（尤其 §五 留档与基线校验 / §六 发布 zip 确定性 / §八 脱敏四步 / §九 三清与九之二 / §十 三件套 / §十一 README 终检 / §十二 回写清单）、plan/04 §六 干净环境验证。

**M6 无待定夺项**（可见性 public 已定夺，见 plan/00 决策记录）。

---

## 三、既定口径 K 清单（动了会打挂基准/测试，改前先读 plan/02）

| 编号 | 口径 | 位置 | 影响面 |
|---|---|---|---|
| K1 | `net_unit_price = purchase_unit_price / yield_rate`，`yield_rate ∈ (0,1]`，净料单价**必然 ≥ 毛料单价** | `rules/formulas.py::net_unit_price` | 引擎/基准 B4/测试；方向反了 7+ 个测试变红 |
| K2 | 损耗率**不是独立参数**，`loss_rate = 1 - yield_rate` 只在呈现层导出 | 同上 | 参数包只存 `yield_rate` |
| K3 | `suggested_price` **先量化**（唯一"量化作用于中间量"的例外），F4 据此反算；`dish_cost` 保持全精度 | `formulas.suggested_price` + `pipeline.compute_pricing` | 改则 B5 对账与 F4 往返断言全变 |
| K4 | Decimal 全链路（`parse_float=Decimal`），量化 `ROUND_HALF_UP`；精度约定 `0.01`/`0.0001` **豁免零字面量门禁** | `model.py` | 金额/比率字段禁用 float；量化方向反了 B4 红 |
| K5 | 参数三态：`verified` 放行 / `pending` **阻断该 scope** / `input_required` **放行门控、值不进可用集、运行时必索** | `rules/params.py` | 门控语义；改则退出码断言全变 |
| K6 | 门控**按 scope 分**（`cost`/`pricing`/`alert`） | `rules/params.py::effective_params` | 无关 pending 不得阻断核算路径 |
| K7 | 导入三态 `ok`/`invalid`/`unknown`；**异常行一律列清单**；`unknown ≠ ok` | `io/csv_import.py` | CLI 退出码 1 语义；B1 真值库 19 用例 |
| K8 | 退出码：0 完成 / 1 降级或未达标或 `not_enabled` / 2 输入不可用或用法错误 / 3 缺可选依赖 | `cli.py` + `benchmark/runner.py` | 锁进测试。M4：`bench` 达标时 = 0。**M5：冻结态 exe 与源码态退出码一致（已实测）** |
| K9 | 基准门槛**随 `data/truth/manifest.json` 下发**（数据非代码），缺失即 `ConfigError`(exit 2)，**不回落默认值** | `benchmark/runner.py::load_thresholds` | 别把门槛写进代码。门槛项含 `max_duration_seconds` 与 `measures_false_positive`，五项缺一即配置错误 |
| K10 | 真值对账语义**单一实现源** `benchmark/cases.py`（`confirmed_keys`/`compare_nonpass`） | `benchmark/cases.py` | 防双口径漂移 |
| K11 | 报告章节**单一渲染源** `report/sections.py`，MD 与 XLSX 同源 | `report/sections.py` | 别各写各的组装逻辑 |
| K12 | 机读产物逐字节可复现：`ZIP_STORED` + `create_system=0` + 固定 `date_time` + 条目排序 | `report/export.py` | 引第三方库会破坏此承诺。**M6 的 release zip 同纪律** |
| K13 | 零字面量门禁 token **运行时实算自参数包**，源码零词面；扫描面含 docstring/注释 | `tools/check_literals.py` | 扫描面为**整包 `src/rcc` + `benchmark`**（24 个入口）；词边界尾端排除 `\.[0-9]` |
| K14 | 确定性生成：**禁 stdlib random、禁 set 迭代序、禁系统时钟**；写盘 `newline="\n"` | `tools/detrng.py` + 各生成器 | 冻结件必须跨机位级一致 |
| K15 | 分层：GUI 只消费 `engine/pipeline`，**零算术、零业务数值、不 import 规则层**（AST 三条齐上） | `tests/guards/test_gates.py` | 三条缺一漏一半。**M5 加行为面**：`import rcc.gui` 不得拉 PySide6（`tests/gui/test_layering_behavior.py`） |
| K16 | 所有会打印的可执行入口（CLI + tools 有 main 的脚本）**必须**调 `ensure_utf8_stdio()` | `tests/guards/test_repo_gates.py` | 新增脚本漏守即红。**M5 的 `launcher_cli.py`/`launcher_gui.py` 已自动入面（共 9 个入口）** |
| K17 | 快照**期间标识 = `data_date`**（数据日），两期数据日相同必须拒绝（exit 2） | `io/snapshot.py` + `pipeline.compute_alert` | 改回去 = "两期退化成同一期"回归 |
| K18 | 快照台账与说明**同源渲染**；`--check` 必须**重算** sha256 而非读台账 | `tools/fetch_snapshots.py` | 手改台账/说明即被检出 |
| K19 | 快照原始件 `-text` 冻结；须比对工作树与 `git cat-file blob` 的 sha256 相等 | `.gitattributes` + `tests/guards/test_snapshot_ledger.py` | 字节漂移则 sha256 全失配。`data/truth/**/*.json -text` 同样已标 |
| K20 | 导入**形态失败** → 抛错 exit 2，**不进逐行清单**；**行级失败** → 进清单 exit 1 | `io/csv_import.py` + `cli.py` | 混淆两者 = 读者去改错的东西 |
| K21 | 进货单**只接受 UTF-8（含 BOM）**，**不做编码猜测** | `io/csv_import.py::_read_text` | B1 用**真 GBK 字节**用例证明它真被拒绝 |
| K22 | 两处 `unknown` 行可用性**分开**：表头级**行可用**；行级**行不入库** | `io/csv_import.py::parse_purchases` | B1 两态各有用例 |
| K23 | 食材库同品名**取最后一条价**；重复**必须可观测** | `io/csv_import.py::build_food_library` | B1 有 `duplicate_names_observable` 用例 |
| K24 | 零可用行报错**必须指向进货单** | `engine/pipeline.py::_require_usable_rows` | B2 有 `no_usable_rows` 用例 |
| K25 | `check` 与 `run` **共用同一分派点** | `engine/pipeline.py` + `tests/guards/test_import_dispatch.py` | 三道门：AST + 行为计数 + 结论等同 |
| K26 | 金额列**不校验数值性**——登记过的口径，非遗漏 | `io/csv_import.py` docstring + 测试 | B1 有 `amount_not_validated` 用例 |
| K27 | 摘要写"见清单"则**必须真打印清单** | `engine/pipeline.py` + `cli.py` | 同"未启用章节显式写出" |
| K28 | **行级代码与文件级代码不混用**：文件级结论用 `ISSUE_NO_USABLE_ROWS`（`line=0`） | `io/csv_import.py` + `engine/pipeline.py` | 借行级代码会让下游按行号定位到不存在的问题行 |
| K29 | **公式原文锚定**：plan/02 §一 公式原文被 `formulas.py` docstring 逐字复述；扫描面内同一算式只准一处实现（例外 `benchmark/runner.py`） | `rules/formulas.py` + `tests/guards/test_formula_single_source.py` | 在别处手写同一算式即红 |
| K30 | **`input_required` 语义**：放行门控、值不进可用集、运行时由取数点索取（缺失 exit 2） | `rules/params.py::effective_params` + `pipeline.yield_rate_for` | 改回"整域抛错" = 与 plan/02 §三 矛盾 |
| K31 | **净料率两种故障分开**：**缺条目** → exit 2；**值越界** → 该菜 `invalid` 并入清单 → exit 1 | `engine/pipeline.py::compute_costcard` | 混为一谈 = 处置建议是错的 |
| K32 | **行级问题的处置粒度 = 整道菜排除**；**全部菜品都被排除** → `no_usable_dishes`（`line=0`）→ exit 2 | `engine/pipeline.py::compute_costcard` | 丢行求和 = 把自洽但偏低的数字当成对的 |
| K33 | **来源校验在消费点**；`qty` 也必须挂来源 | `engine/pipeline.py` + `_load_bom` | 只守构造期 = 只守了自己造的那一半 |
| K34 | `SourceMissing` **继承 `ValueError`**（+ 机读 `code = "source_missing"`） | `model.py` | 退回裸 `Exception` = 未捕获 traceback |
| K35 | **成本卡行级 issue 用 `where`（菜品·食材）、`line = None`**，三种定位形态互不冒充 | `engine/pipeline.py::_line_issue` + `render_issues` | 硬填行号会让读者去查不存在的位置 |
| K36 | **真值库只存输入与期望，观测由观测器运行时实算**；真值库里出现 `observed` 一类字段即红 | `benchmark/cases.py` + `data/truth/*.json` | 冻观测 = 评测退化成"比对两个冻结字典" |
| K37 | **结论键自带结论**（`status:X=down`、`cost:X=3.24`），取值恒 `ok`；对账语义单一实现源 | `benchmark/cases.py::confirmed_keys`/`compare_nonpass` | 状态当值会因字段名集合相同而**看不见误分类** |
| K38 | **覆盖度分母从代码常量集反射**（`csv_import`/`pipeline` 的 `ISSUE_*`），**分子必须等于分母**否则生成器报错 | `tools/gen_truth.py` + `manifest.json` | 防"分母被悄悄做小" |
| K39 | **门槛五项齐备**（含 `max_duration_seconds` 与 `measures_false_positive`），缺一即 `ConfigError`；**时长真判**；**不可测的误报率显式声明未测** | `benchmark/runner.py` + `manifest.json` | "登记了却静默不判"与沉默同样坏 |
| K40 | **探活必须断言"基准报未达标"**，不得只断言"坏实现本身不同" | `tests/benchmark/test_runner.py` | 后者是"对坏实现的自述" |
| **K41（M5 新增）** | **`build_datas()`：文件条目目标目录 = 父目录；目录条目目标目录 = 条目自身**；**包内路径必须等于仓库内相对路径** | `src/rcc/packaging.py` + `tools/rcc.spec` + `tests/guards/test_pack_gate.py` | 目录条目取 `dirname` = 随包数据被拍平进 `data/`，**构建不报错、换机器才炸** |
| **K42（M5 新增）** | **随包数据定位只有一处** `packaging.find_data_dir()`（源码态与冻结态同一答案）；消费点不得自行按 `__file__` 上溯 | `src/rcc/packaging.py`（引用方 `rules/params.py` / `benchmark/runner.py` / `cases.py` / `selftest.py`） | 自行上溯在冻结态指向不存在的"仓库根" |
| **K43（M5 新增）** | **spec 的 `datas` 只由 `build_datas()` 产生**，无手写数据路径、无禁区字面；构建前对账白名单 | `tools/rcc.spec` + `tests/guards/test_pack_gate.py` | 手写路径 = 白名单改了 spec 没跟着改，构建不报错 |
| **K44（M5 新增）** | **冻结态自检断言 `data_dir` 落在 exe 目录内**（`os.path.commonpath`），**非冻结态返回 `None` 而非 FAIL**；**缺数据不静默回落开发机仓库** | `packaging.frozen_data_is_inside_dist` + `selftest.py` | 打包最常见失效模式 = "数据没随包走、exe 回头读了开发机仓库" |
| **K45（M5 新增）** | **分层门禁分两面**：AST（`tests/guards/`）+ 行为（`tests/gui/test_layering_behavior.py`，**不 import 重件、恒跑**）；只有真需要 Qt 的冒烟才跳过 | `tests/guards/test_gates.py` + `tests/gui/` | 把分层门禁搬进可 skip 的目录 = 没装 gui extra 的机器上界面分层无人守 |
| **K46（M5 新增）** | **打包入口不含业务判断**（`tools/launcher_*.py` 只装编码守卫 + 转交包内 main）；核心自检零重件 | `tools/launcher_*.py` + `src/rcc/selftest.py` | 入口若长判断 = 第二处口径；自检若 import GUI = 没装 gui extra 时 `rcc selftest` 挂 |

**修正纪律**：改口径前先判是"**校验方式不自洽**"（只改谓词）还是"**口径本身定错**"（引擎与真值同源修正，两边一起改）；共同验收门 = `gen_params.py --check` + `gen_samples.py --check` + `gen_truth.py --check` 三者都输出 `OK`。

---

## 四、本机环境坑（M0–M5 实测）

| 坑 | 症状 | 处置 |
|---|---|---|
| 本机有 **3.8.8 与 3.12.10** 两条通道 | 用 3.12 全绿但 3.8 会挂一批 API | 开工先 `py -0p`；**改动后双解释器都跑** |
| `python` 可能是商店占位符 | `python -m venv` 失败 | 用 `py -3.12` / `py -3.8`；venv 内用 `python` |
| `core.autocrlf=true`（本机全局） | 新 clone 会把 LF 翻成 CRLF，冻结件 sha256 失配 | `.gitattributes` `* text=auto eol=lf` + 快照/真值库 `-text` + EOL 门守门（**M5：`.spec` 已纳入 EOL 门扫描面**） |
| git 全局 user.email | 发布期脱敏硬门 | **M0 已全历史改写为 noreply**；后续每次 `git commit --amend` 都要显式带 `GIT_COMMITTER_EMAIL=<noreply>` |
| 跨盘符 `os.path.relpath` | `ValueError: path is on mount 'C:', start on 'D:'` | 展示路径 `try/except ValueError` 回落绝对路径 |
| pip 代理污染 | `https://127.0.0.1:xxxx` 连接失败 | `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>` |
| 中文控制台编码 | `UnicodeEncodeError` | 跑脚本一律 `py -X utf8`；入口守卫是另一层 |
| pyc 偶发损坏 | 随机 FAIL / unknown opcode | 全程 `PYTHONDONTWRITEBYTECODE=1`；出怪错先清 `__pycache__` |
| pytest `tmp_path` 在 C: 盘 | 与仓库 D: 跨盘 | 同"跨盘符 relpath"条 |
| 测试多时分批跑 | 单批偶发崩溃 | 分批 ≤50、批间 sleep；单批失败只重跑该批 |
| 新发地接口偶发 503 | 抓取随机失败 | 抓取器内置退避重试（4 次，间隔递增）；批量抓取间 sleep 1s |
| **`out/` 目录在 `.gitignore` 里** | 往 `out/` 写验证产物会"看着成功其实没写" | 验证产物一律写**仓库树外**（`$TEMP`）。**M5 的构建产物同纪律：`--distpath`/`--workpath` 指向 `$TEMP`** |
| 管道吞退出码 | `cmd \| head; echo $?` 拿到的是 `head` 的退出码 0 | 核验退出码必须 `> /dev/null 2>&1` **单独跑** |
| 测试夹具与被测对象不匹配 | 单菜 BOM 配行级问题 → 走成"全部排除"，测错了对象 | 行级问题用例**搭档一道健康菜**并断言健康菜成本 |
| 端到端测试里的 `if` 分支是假门 | "若触发了则断言 X"→ 未触发时静默通过 | 把前提断言出来 |
| 临时副本做变异验证要清干净 | 改工作树文件做变异 → 忘了还原就提交 | 变异脚本一律在**树外副本**上做；**提交前 `git status` 复核** |
| 测试夹具写盘位置 | 观测器把 `repo_root` 当 workdir → 在仓库根写了 `probe.csv` | 观测器只需临时目录做收尾清理；`git status` 是最后一道网 |
| 探活测试的仓库副本要能独立跑 | 副本漏 `benchmark/` → 报"模块找不到"而非"被测行为变了" | `_probe_repo()` 明确复制 `tools + src + benchmark + data` |
| 时长/性能断言用真实计时不可靠 | 门槛 0 与实测 0.0 "恰好相等" | 用 `monkeypatch` 打桩时钟 |
| **PyInstaller 的目录源语义（M5 新记）** | 目录条目按文件条目算目标目录 → 内容被拍平，**构建成功但冻结态取不到数据** | 目录条目目标目录取条目自身；判据落在"包内路径 == 仓库相对路径" |
| **两个 Analysis 各自收集第三方 datas（M5 新记）** | 只传一个分析的 datas，靠"两边恰好相同" | 两边 datas 都传 COLLECT，去重交给它 |
| **入口脚本的顶层模块语义（M5 新记）** | 拿包内模块当入口 → 相对导入 ImportError | 入口独立成 `tools/launcher_*.py` |
| **`--clean` 构建先删 dist（M5 新记）** | 构建中途崩 → dist 没了 | dist/work 路径指向仓库树外，树外那份是唯一回退 |
| **`pytest.importorskip(exc_type=)` 是 8.2+（M5 新记）** | py3.8 的 pytest 7.4 传它 TypeError | 手工 `try/except ImportError` + 模块级 `pytest.skip(allow_module_level=True)` |
| **探活脚本拼串会拼出语法错误（M5 新记）** | 分号拼 `-c` 脚本 → 子进程非 0 → 探活静默 skip，变成没证据的话 | 逐行拼装 + 断言 `returncode == 0`，**不许把"探活跑不起来"降级成 skip** |
| **PySide6 offscreen 的设点（M5 新记）** | Qt 只在建 `QApplication` 时读 `QT_QPA_PLATFORM`，测试函数里再设已太晚 | 在 `tests/gui/conftest.py` 的**模块层** `os.environ.setdefault` |

**gh 认证状态**（M0 实测，M5 期未变）：登录 `yuluo554`，token scopes = `gist, read:org, repo`（**无 workflow**）
→ 建仓必须走 `gh repo create --public ... --source . --remote origin`（**不带 `--push`**）+ 切 SSH remote 后 push。**当前仍无远端。**

---

## 五、关键命令速查

```bash
# 双解释器全量测试（收尾必跑）
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest -q    # 317 passed
PYTHONDONTWRITEBYTECODE=1 py -3.8  -X utf8 -m pytest -q    # 317 passed

# 脱敏审计（新增文档/提交前必跑；**单独跑，别接管道**）
py -3.12 -X utf8 tools/audit_desensitize.py --selftest     # AUDIT_SELFTEST_OK
py -3.12 -X utf8 tools/audit_desensitize.py                # DESENSITIZE_AUDIT_OK

# 冻结产物位级一致（改数据后必跑；三个生成器）
py -3.12 -X utf8 tools/gen_params.py --check      # FROZEN_PARAMS_OK
py -3.12 -X utf8 tools/gen_samples.py --check     # FROZEN_SAMPLES_OK
py -3.12 -X utf8 tools/gen_truth.py --check       # FROZEN_TRUTH_OK

# 快照位级一致 + 自检（离线；改了快照/台账必跑）
py -3.12 -X utf8 tools/fetch_snapshots.py --check       # SNAPSHOT_CHECK_OK
py -3.12 -X utf8 tools/fetch_snapshots.py --selftest    # SNAPSHOT_SELFTEST_OK
py -3.12 -X utf8 tools/fetch_snapshots.py --refetch-check   # 联网重抓比对

# 零字面量门禁 + G-PACK + GUI 分层门（新增源码/打包件后必跑）
py -3.12 -X utf8 tools/check_literals.py --selftest
py -3.12 -X utf8 tools/check_literals.py          # 24 个入口，0 命中
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest tests/guards/test_pack_gate.py -q   # 20 passed
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest tests/gui -q                        # 10 passed

# 基准（M4：五套件达标 → exit 0）
py -3.12 -X utf8 -m rcc.cli bench                 # 总判: 达标
py -3.12 -X utf8 -m rcc.cli bench --json

# 端到端（退出码 1 = 有异常行，明示语义）
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json

# 自检
py -3.12 -X utf8 -m rcc.cli selftest

# ---- 打包（M5）----------------------------------------------------------
# 构建（dist/work 一律指向仓库树外）
py -3.12 -X utf8 -m PyInstaller --clean --noconfirm \
    --distpath "$TEMP/rcc-dist" --workpath "$TEMP/rcc-build" tools/rcc.spec

# 冻结态自检（**在中立目录跑，别在仓库树内** —— CWD 上溯会命中仓库 data/）
cd "$(mktemp -d)"
"$TEMP/rcc-dist/rcc/rcc.exe" selftest                       # frozen=true + frozen_data_inside_dist=true, exit 0
"$TEMP/rcc-dist/rcc/rcc.exe" bench                          # 总判: 达标, exit 0
"$TEMP/rcc-dist/rcc/rcc-gui.exe" --selftest out.json        # 写 JSON, exit 0
# 负向对照：删 _internal/data 后再跑 selftest → ok=false + exit 1

# 收集数对账
py -3.12 -X utf8 -m pytest --collect-only -q | tail -1    # 317 tests collected

# 变异验证（M5 九条已实测全红；改打包纪律后可复跑）
# ① spec 手写 "data/..." → test_spec_has_no_handwritten_data_path 红
# ② DATAS 改字面列举 → test_spec_datas_come_from_build_datas 红
# ③ build_datas() 目录条目退回 dirname → test_bundled_layout_matches_repo_layout 红
# ④ data/ 下新增未登记目录 → test_whitelist_covers_every_data_directory 红
# ⑤ frozen_data_is_inside_dist 恒 True → test_frozen_inside_dist_rejects_data_outside_exe 红
# ⑥ spec 写带中文的禁区路径 → test_spec_has_no_forbidden_literals 红
# ⑦ --selftest 页签数恒 0 → tests/gui/test_main_window.py 红
# ⑧ 去掉 setuptools<81 上界 → test_build_extra_pins_setuptools_upper_bound 红
# ⑨ 去掉 PyInstaller>=6 下界 → test_build_extra_pins_pyinstaller_lower_bound 红

# 退出码核验（**别接管道**）
py -3.12 -X utf8 -m rcc.cli bench > /dev/null 2>&1; echo $?    # 0
py -3.12 -X utf8 -m rcc.cli bench --only nope > /dev/null 2>&1; echo $?   # 2

# git 链三核对（防 cwd 被劫持）
pwd && git log --oneline -1 && git remote -v
```

---

## 六、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M6.md" 继续完成任务
```

（入库的本文件用相对路径 `plan/HANDOFF-M6.md`；启动命令由用户侧拼绝对路径。）

**M6 目标一句话**：把 M5 打出来的 onedir 双 exe 组装成确定性 release zip（同 dist → 同 zip 逐字节一致），
建 GitHub 公开仓库并把 CI 跑绿（**首跑就是验收**），然后做三件套（tag / Release 附产物 + sha256 留档 /
`plan/RELEASE-M6.md`）、干净环境逐条跑通、脱敏四步 + 产物扫描，并**真下载附件复验**——
使交付物从"本地可用"推进到"别人能下载、能校验、能在自己机器上跑起来"。

---

## 七、M7 补记（2026-10-20）：非 editable 安装读不到数据

### 缺陷

`pyproject.toml` 在 M6 已经修过 `benchmark` 包的安装面，但**没有任何 `package-data`**；
数据在**仓库根** `data/`（包外）。`find_data_dir()` 源码态走 `repo_root()`，而
`pip install <wheel>` 之后 `repo_root()` 找到的是 `<venv>`，于是：

```
rcc selftest → {"ok": false, "data_dir": null, "param_count": 0, …}   exit 1
rcc bench    → FileNotFoundError: 未能定位数据目录（data/）            exit 1（裸 traceback）
rcc run ...  → "输入不可用: 未能定位数据目录（data/）"                  exit 2
```

**为什么 CI 全绿**：CI 唯一 job 是 `pip install -e ".[dev]"`，editable 安装把仓库根放上
`sys.path`，`repo_root()` 命中仓库根 → `data/` 正常。CI 里那条 console-script 冒烟
（注释写着"用 `python -m` 冒烟等于永远问不到用户装完到底能不能跑"）**思路完全正确，
只是跑在了错误的装态上**。

### 修复

1. `data/{rules,samples,snapshots,truth,README.md}` → `src/rcc/data/`（`git mv`，字节未动）；
2. `pyproject.toml` 加 `[tool.setuptools.package-data] rcc = ["data/**/*"]`；
3. `packaging.find_data_dir()` 新增**包内分支**（`package_data_dir()`，排在 `repo_root()`
   之前）——装态与源码态因此走同一条"包旁边找 `data/`"的路；**冻结态三个候选分支一个字未动**，
   "绝不回落开发机仓库"那条纪律保留；
4. `build_datas()` 的**源**改指包内数据根，**目标**仍是白名单里的包内相对路径
   （`data/...`）——exe 内布局与 wheel 内布局逐字相同；
5. 全量同步写死 `data/` 的地方：四个生成器/抓取器的输出目录、`check_literals` 的参数包路径、
   `make_release.check_dist` 的仓库侧基准、`tests/**` 的路径字面量、README 九步命令与目录树；
6. `tests/guards/test_pack_gate.py` 的"包内布局 == 仓库相对布局"断言按新口径重述
   （比较基准由 `repo_root` 改为 `package_data_dir`，**判定强度不变**：拍平仍立刻红）。

### 新增门禁（G-INSTALL）

| 层 | 位置 | 断言 |
|---|---|---|
| 结构级 | `tests/guards/test_install_smoke.py::test_wheel_contains_package_data` | wheel 里真有 `rcc/data/**`；关键文件（params/manifest/samples）在场；快照 ≥2 份 |
| 行为级 | 同文件 `::test_installed_wheel_is_usable` | 干净副本 → wheel → **全新 venv** → **中立目录**跑 `selftest`（exit 0 / `ok=true` / `param_count>0` / `data_dir` 在 site-packages 内且不在开发机仓库）与 `bench`（exit 0 / 五套件 `[达标]` / `总判: 达标`） |
| CI | `.github/workflows/ci.yml` "Installed-wheel smoke" 一步 | 同链路；**保留**原有 editable 态 console-script 冒烟（两种装态各守一半） |

**负控实测（必须记，这是本门最容易假绿的地方）**：第一版从**仓库树内**直接
`pip wheel .`，把 `[tool.setuptools.package-data]` 整段删掉后**两条门仍然全绿**——
因为仓库里残留的 `build/lib/rcc/data/` 被 setuptools 复用，wheel 里照样有数据。
改为**从仓库树外的干净副本构建**（只复制 `pyproject.toml`/`README.md`/`LICENSE`/`src`/`benchmark`）
后，删掉 `package-data` 两条门都按预期变红（结构级报"wheel 里没有任何 rcc/data/ 条目"，
行为级报"selftest 退出码 1"）。**教训：构建类门禁必须在不含上一次构建产物的树上跑。**

### 实测（M7 收口时）

```
pip wheel（干净副本）→ 46 条目 / data 16 / 110,562 B
干净 venv + 装 wheel + 中立目录：
  rcc selftest → exit 0；"ok": true；param_count: 12；
                 data_dir = <venv>/Lib/site-packages/rcc/data
  rcc bench    → exit 0；[达标] ×5；总判: 达标
  rcc run --purchases <site-packages>/rcc/data/samples/purchases-demo.csv … → exit 1（有异常行，明示语义）
pytest → 329 passed, 1 skipped（改前 321 + 装态门 2 + README 计数门 2 + D4 两条 2 +
        floor 同源断言 2；按文件逐个 `--collect-only` 对账：install_smoke 2 / repo_gates
        18→20 / test_cli 43→45 / py38_compat 5→7）
```

> **CI 侧已实测**：提交 `0ecdbdc` 推送后 CI run 39296693217，windows 与 ubuntu 两矩阵各 12 步
> 全 `success`（含本步）。
