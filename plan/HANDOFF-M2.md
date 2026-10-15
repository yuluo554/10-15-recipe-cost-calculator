# HANDOFF-M2 交接快照

> 上一里程碑：**M1 数据先行**（已完成，2026-10-15）
> 下一里程碑：**M2 导入**（进货单解析与三态语义）
> 本快照在 M1 出口落盘，含六节：进度+证据 / 待办 / 既定口径 K 清单 / 环境坑 / 命令速查 / 启动提示词

---

## 一、当前进度与证据（M1 出口状态）

| 项 | 状态 | 证据 |
|---|---|---|
| 快照抓取器 | ✅ | `tools/fetch_snapshots.py`（联网抓取 + `--check` / `--selftest` / `--refetch-check`；`--dates` / `--captured-date` / `--force`） |
| **≥3 个可区分数据日** | ✅ | `data/snapshots/xinfadi-{2026-08-06,2026-09-06,2026-10-06}.json`，各 467 / 327 / 474 条 |
| 原始 JSON + 抓取日期 + sha256 台账 | ✅ | `data/snapshots/ledger.json` + `data/snapshots/README.md`（**同源渲染，禁手改**）；抓取日 2026-10-15；sha256 逐个登记 |
| `--check` 位级一致 | ✅ | `SNAPSHOT_CHECK_OK: 3 份快照位级一致，台账与磁盘实况同源`（离线，重算 sha256） |
| 抓取器自检 | ✅ | `--selftest` → `SNAPSHOT_SELFTEST_OK`（三种注入：篡改原始件 / 篡改台账 sha256 / 手改 README，**全部必被检出**） |
| **跨抓取字节稳定** | ✅ | `--refetch-check` → `SNAPSHOT_REFETCH_OK: 全部快照重抓字节一致`（联网重抓比对；同参数两次独立抓取字节相同，已实测） |
| 字节冻结生效 | ✅ | `git add` 后工作树 sha256 == `git cat-file blob :<path>` sha256（**逐份相等**，非只看 `git check-attr`）；`data/snapshots/** -text` 已标；全部件 CR=False |
| 题面论证可由留档复算 | ✅ | 从留档件直读大白菜 avgPrice = 0.55 / 0.53 / 0.40 元/斤，与 plan/01 §12 逐位一致 |
| **带预警端到端跑通** | ✅ | `rcc run --with-alert --snapshots <08-06> <10-06>` → exit 1；141 项超阈值、439 项变动（up 128/down 117/flat 112/new 45/gone 37）、4 道菜受影响（醋溜白菜 −22.50% 最显著） |
| 报告双轨 + 位级确定（预警版） | ✅ | 同一输入两次 `--report` 导出，`.md` 与 `.xlsx` 逐字节一致；XLSX 5 条目 0 外链违规 |
| 溯源块显示两期可区分 | ✅ | 报告 §六 出现 `旧快照 … xinfadi-2026-08-06.json | 2026-08-06` / `新快照 … xinfadi-2026-10-06.json | 2026-10-06` |
| **缺陷修复：期间标识** | ✅ | `load_snapshot` 原把 `date` ← `captured_date` → 两期显示同一抓取日；已改 `date` ← `data_date`（保留 `captured_date`）；`compute_alert` 加数据日相同的显式拒绝（exit 2） |
| 新守门测试 | ✅ | `tests/guards/test_snapshot_ledger.py` **11 项**（含篡改探活 + 两期退化守卫 + 两期可区分断言） |
| 测试全绿（双解释器） | ✅ | `py -3.12` **149 passed**；`py -3.8` **149 passed**（同 extras 下计数一致） |
| 零字面量门禁 | ✅ | `LITERAL_GATE_OK: 扫描面 16 个入口，禁用 token 31 个，0 命中`；`--selftest` → `LITERAL_GATE_SELFTEST_OK` |
| 冻结产物位级一致 | ✅ | `gen_params.py --check` → `FROZEN_PARAMS_OK`；`gen_samples.py --check` → `FROZEN_SAMPLES_OK` |
| 脱敏审计 | ✅ | `--selftest` → `AUDIT_SELFTEST_OK`；全模式 → `DESENSITIZE_AUDIT_OK: HARD 0 / REVIEW 0 / advisory 9`（advisory 全为台账/元数据里的 sha256 长 hex，属文档化功能） |
| 基准（规则驱动层） | ✅ | `bench --only boundary` exit 0（29/29）；`--only reconcile` exit 0（4/4）；样本驱动三套件仍 `not_enabled` + exit 1（**不冒充通过**） |
| CI 真实状态 | ⬜ **未接远端，CI 未跑过** | **诚实口径：本地等价校验通过（双解释器 pytest 149 + 门禁 selftest + 生成器 --check + 快照 --check），CI 配置已入仓待首推验证** |
| 干净环境验证（M1） | ⬜ **未重跑** | M0 已跑过（136 passed / 2 skipped）。M1 新增 11 项测试**依赖快照件**（已入仓，导出树里在），故干净环境预期 147 passed / 2 skipped——**M6 收尾时按 plan/04 §六 重跑并回填实测值**，此处不预填 |

### M1 期实测发现的缺陷与陷阱（都已处置，记此防复现）

1. **`limit` 缺省静默截断到 20 条**——响应 `count` 仍报真实总数（467），但 `list` 只回 20 条。
   **按错实现会产出"sha256 自洽但缺记录"的快照**，台账看不出来。处置 = 抓取器显式给足并
   **断言 `len(list) == count`**。
2. **请求参数被响应原样回显**（`current`/`limit`/品类 id 都在响应体里）——同一数据日换
   `limit` 值即得不同字节，sha256 不可比。处置 = 参数集固定，并把 `request` 记进 `.meta.json`。
3. **期间标识用抓取日 → 两期不可区分**（本里程碑头号缺陷）：`load_snapshot` 原把 `date`
   映射到 `captured_date`，于是 2026-08-06 与 2026-10-06 两期**双双显示 `2026-10-15`**。
   这正是"两期退化成同一期"的**第二种形态**（第一种是 `startDate` 参数被静默忽略）。
   处置 = `date` ← `data_date` + `compute_alert` 显式拒绝同期（exit 2）。
4. **`prodName` 同日可重复**：467 条里只有 394 个不同品名（73 条重复，不同规格/产地）。
   引擎按品名建索引**后出现者覆盖前者**——既有确定性行为，但语义上等于"取该品名最后一条"。
   原始件保留全部条目，重复数逐日记进 `.meta.json`。
5. **单位不全是"斤"**：467 条里 454 条为斤，其余个/只/筐/箱。`.meta.json` 的 `unit` 是
   **多数单位**，逐条单位以原始件 `unitInfo` 为准；首期不做单位换算。
6. **测试自身的假绿**：我最初的篡改探活按 `sorted()` 取了 `ledger.json`（不含 `avgPrice`），
   替换后字节不变 → 探活"通过"是假的。处置 = 只挑 `xinfadi-*.json`，并加
   `assert tampered != raw` 自证替换动作生效。**探活失败先怀疑探活自己**。

### M1 数据底座新增事实（已回写 data/README §一之三）

- 整日全品类查询（467 条）与四品类分别查询求和的 **`id` 集合逐条相等** → 取整日一份件为留档主体，
  逐品类查询改作**抓取期交叉核验**（断言并集 == 整日记录数，不等即报"有品类未登记"）。
- 三个数据日的品类覆盖（蔬菜/水果/肉禽蛋/水产）：08-06 = 134/81/140/112；**09-06 = 104/83/140/0**
  （该日水产为 0，属真实数据形态，非抓取失败）；10-06 = 133/87/141/113。
- `data_date`（数据日）与 `captured_date`（抓取日）**是两个字段**，同一抓取日可抓多个数据日。

---

## 二、下一里程碑待办（M2 导入）

**DoD**：样例进货单导入复跑通过；异常行清单可复现；三态语义锁进测试。

**M2 起点状态（已核实，别重做）**：`src/rcc/io/csv_import.py` 的 **CSV 通路已存在且可用**
（列名白名单 `COLUMN_MAP` + 三态 `ok`/`invalid`/`unknown` + 异常行逐条列清单 + `build_food_library`），
已有 12 项单测 + 集成测试覆盖退出码 1 语义。**M2 不是从零写解析器**，是补缺口：

- [ ] **先定夺 Excel 是否属首期**（这是 M2 的第一个决策，见下"待定夺"）——README"限制"节现写
      "首期仅支持 CSV（Excel 列为后续形态）"，而 plan/00 的 M2 写"进货单 CSV/Excel 解析"。
      **两处口径冲突，必须先定一个**，再决定要不要写 `openpyxl`/自写 xlsx 读（注意：自写 xlsx 读
      会与"核心零第三方依赖"交互，须登记决策）。
- [ ] **三态语义补齐**：现 `unknown` 仅覆盖"未登记列名"与"单位未登记"；plan/02 §5 还要求
      "整行结构不可解析"归 `unknown`。核对是否需要补，并**把三态写进显式测试矩阵**（现测试偏 `invalid`）。
- [ ] **`check` 与 `run` 共用同一分派点**（plan/06 硬纪律）：核对两条通路是否真走同一解析函数，
      防复制粘贴出第二份判定逻辑。
- [ ] **失败路径补齐**（plan/04 §三）：空文件、坏编码（非 UTF-8）、缺表头、全行异常、
      表头有 BOM（现用 `utf-8-sig`，需测）、列顺序打乱、多余空列。
- [ ] **食材库语义定死**：`build_food_library` 现为"同品名取最后一条价"，需在 plan/02 或
      模块注释里**显式登记**（它是"多来源同品名"的取舍口径，不写就是隐性第二口径）。
- [ ] 样例进货单可复现：`gen_samples.py` 已注入 3 类异常行（非数值 / 空品名 / 未登记列名），
      **M2 若扩样例体例，必须走生成器整目录重生成**（禁手改，配 `--check`）。
- [ ] 收尾：plan/00·05·06 状态回写 → **写 `plan/HANDOFF-M3.md`** → commit。

**待定夺（M2 开工前必须问用户）**：

1. **Excel 是否进首期**（README 与 plan/00 口径冲突，见上）；
2. 若要 Excel：**用 `openpyxl`（破"核心零第三方依赖"）还是自写最小 xlsx 读**（自写只读 inlineStr/
   sharedStrings 有工作量，且要把 `zipfile` 读路径纳入 EOL/外链/确定性守门面）。

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
| **K17（M1 新增）** | 快照**期间标识 = `data_date`**（数据日），`captured_date` 另存；**两期数据日相同必须拒绝**（exit 2） | `io/snapshot.py` + `engine/pipeline.py::compute_alert` | 改回去 = "两期退化成同一期"回归 |
| **K18（M1 新增）** | 快照台账与说明**同源渲染**（`ledger.json` + `README.md` 皆由抓取器产出，禁手改）；`--check` 必须**重算** sha256 而非读台账 | `tools/fetch_snapshots.py` | 手改台账/说明即被检出 |
| **K19（M1 新增）** | 快照原始件 `-text` 冻结；"标了属性"不算数，**须比对工作树与 `git cat-file blob` 的 sha256 相等** | `.gitattributes` + `tests/guards/test_snapshot_ledger.py` | 字节漂移则 sha256 全失配 |

**修正纪律**：改口径前先判是"**校验方式不自洽**"（只改谓词）还是"**口径本身定错**"（引擎与真值同源修正，两边一起改）；共同验收门 = `gen_params.py --check` + `gen_samples.py --check` 仍输出 `OK`。

---

## 四、本机环境坑（M0/M1 实测）

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

**gh 认证状态**（M0 实测）：登录 `yuluo554`，token scopes = `gist, read:org, repo`（**无 workflow**）
→ 建仓必须走 `gh repo create --public ... --source . --remote origin`（**不带 `--push`**）+ 切 SSH
remote 后 push（SSH 不受 OAuth scope 限制，携带 workflow 文件也能触发 CI）。**当前仍无远端。**

---

## 五、关键命令速查

```bash
# 双解释器全量测试（收尾必跑）
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest -q    # 149 passed
PYTHONDONTWRITEBYTECODE=1 py -3.8  -X utf8 -m pytest -q    # 149 passed

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

# 端到端 + 报告
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json --report out/report

# 带预警端到端（两期真实快照；exit 1 = 有异常行）
py -3.12 -X utf8 -m rcc.cli run --purchases data/samples/purchases-demo.csv --bom data/samples/bom-demo.json --with-alert --snapshots data/snapshots/xinfadi-2026-08-06.json data/snapshots/xinfadi-2026-10-06.json

# 基准（boundary/reconcile 应 exit 0；样本驱动套件未生成时 exit 1 属明示语义）
py -3.12 -X utf8 -m rcc.cli bench
py -3.12 -X utf8 -m rcc.cli bench --only boundary

# 自检
py -3.12 -X utf8 -m rcc.cli selftest

# 收集数对账（"dev 与干净环境同 extras 下应一致"）
py -3.12 -X utf8 -m pytest --collect-only -q | tail -1

# 冻结件字节冻结实测（标了 -text ≠ 字节真没变）
git add data/snapshots && python -c "
import subprocess,hashlib
for f in ['data/snapshots/xinfadi-2026-08-06.json']:
    w=hashlib.sha256(open(f,'rb').read()).hexdigest()
    b=hashlib.sha256(subprocess.run(['git','cat-file','blob',':'+f],capture_output=True).stdout).hexdigest()
    print(f, w==b)
" && git reset -q

# git 链三核对（防 cwd 被劫持）
pwd && git log --oneline -1 && git remote -v
```

---

## 六、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M2.md" 继续完成任务
```

（入库的本文件用相对路径 `plan/HANDOFF-M2.md`；启动命令由用户侧拼绝对路径。）

**M2 目标一句话**：把进货单导入的三态语义与失败路径锁进测试（CSV 通路已存在，是补缺口不是重写），
并先定夺 Excel 是否进首期——注意 README"仅 CSV"与 plan/00"CSV/Excel"两处口径冲突。
