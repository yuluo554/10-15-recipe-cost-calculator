# HANDOFF-M7 收官快照（M6 之后）

> 上一里程碑：**M6 发布**（已完成，2026-10-15）
> 下一里程碑：**无**（六期计划 M0→M6 已全部走完）。本文件是**收官快照**，供"二期/维护/换人接手"接续。
> 含六节：进度+证据 / 后续可做（非承诺） / 既定口径 K 清单（增补）/ 环境坑（增补）/ 命令速查 / 接续提示词

---

## 一、M6 出口状态与证据

| 项 | 状态 | 证据 |
|---|---|---|
| **公开仓库** | ✅ | <https://github.com/yuluo554/10-15-recipe-cost-calculator>（public）；`gh repo create --public ... --source . --remote origin`（**不带 `--push`**）→ 切 SSH remote → push |
| **CI 首跑** | ✅ | 见 `plan/RELEASE-M6.md` §二（当时的矩阵 `windows×{3.8,3.12}` + `ubuntu×3.12`；**M7 起收缩为 `{windows,ubuntu}×3.12`**）；**新增"控制台脚本冒烟"一步**（`rcc` 裸命令形式，见 §四 头号发现）；M7 再加"装真 wheel"一步 |
| **确定性 release 产物** | ✅ | `tools/make_release.py`：`rcc-v0.1.0-win64.zip`，170 条目 / 118,507,589 B / sha256 `fc62a21e…09a3`；`verify` 两次独立打包**同 sha256** |
| **sha256 留档** | ✅ | `plan/DIST-sha256-M6.txt`（哈希行由 `sha256sum` 重定向生成，人只写注释）；`sha256sum -c` 复验三行全 `OK`、**无告警** |
| **发布留档** | ✅ | `plan/RELEASE-M6.md`（只写实测到的，未跑的项留 ⬜） |
| **冻结态验收** | ✅ | 中立目录：`selftest` → `frozen=true` + `frozen_data_inside_dist=true` + exit 0；`bench` → 达标 exit 0；`rcc-gui.exe --selftest` → 页签 4 + exit 0；**负向对照**删 `_internal/data` → `ok=false` + exit 1 |
| **干净环境验证** | ✅ | `git archive` 导出树 → 全新 venv（Python 3.12.10 / pytest 9.1.1）→ **319 passed / 3 skipped / 321 collected**；收集数与本地同 extras **一致**；README 快速开始 9 行退出码逐条实测 |
| **脱敏四步 + 产物扫描** | ✅ | tracked/history/messages 均 **HARD 0**；提交元数据只剩 noreply；`git fsck` 无悬空对象；**产物本体** 102 处命中经"官方原件同串比对"**实算**裁决为 `UPSTREAM`，本项目自有数据与代码 **0 处** |
| **M6 头号发现（已修 + 加门）** | ✅ | 顶层 `benchmark/` 未进安装面 → **`rcc bench` 控制台通路挂**（详见 §四） |
| **测试** | ✅ | 双解释器 **328 passed**（收集数一致）。**M7 复核**：单解释器 **329 passed, 1 skipped**（floor 抬到 3.12 后不再跑 3.8 通道） |
| **M7：pip 装态可用** | ✅ | 数据迁入 `src/rcc/data/`；干净 venv 装 wheel 后 `selftest` exit 0 / `ok=true` / `param_count=12`、`bench` exit 0 五套件达标；详见 `plan/HANDOFF-M6.md §七`。**已推送 `0ecdbdc`，CI run 39296693217 两矩阵各 12 步全绿** |

---

## 二、后续可做（**非承诺**，仅列素材——二期选题时按价值挑）

| 方向 | 现状 | 若做，先想清楚 |
|---|---|---|
| Excel（.xlsx）进货单 | 首期只收 CSV，Excel 列扩展项（plan/00 决策记录） | 自写最小读需 `zipfile`+XML 并纳入 EOL/外链/确定性守门面；引 `openpyxl` 则破"核心零第三方依赖"。**两条路都要先回答"它进不进冻结 exe + 进不进零字面量扫描面"** |
| 联网拉价 | 首期只用内置快照（确定性优先） | 破"纯本地零网络"承诺，且引入外部不确定性 → 与"结论 100% 可复现"冲突。若做，须把"联网件"与"确定性件"分层 |
| 营养成分计算 | 未做（foodmate 数据库 M0 实测可连） | 与成本核算无耦合，属独立能力 |
| 多门店 | 未做 | 参数包按门店分层？口径是否仍是单一来源？ |
| 规则驱动误报率 | 结构上不可测，manifest 用 `measures_false_positive` **显式声明未测** | 要测就得先定义"规则层的误报"是什么——**别为了填一个格子而发明一个口径** |
| 单文件 exe（onefile） | 现为 onedir（启动快、随包数据可自证） | onefile 每次运行要解压到临时目录，"数据落在 exe 目录内"这条自检**语义会变**——G-PACK 与自检都要跟着改 |

---

## 三、既定口径 K 清单（M6 增补；K1–K46 见 `plan/HANDOFF-M6.md` §三）

| 编号 | 口径 | 位置 | 影响面 |
|---|---|---|---|
| **K47** | **顶层 `benchmark/` 必须在安装面内**：`package-dir` 显式映射其根（`{"": "src", "benchmark": "benchmark"}`），`packages.find` 的 `where` 含仓库根 | `pyproject.toml` + `tests/guards/test_pack_gate.py` | 退回只装 `src/` = 控制台脚本 `rcc bench` ModuleNotFoundError。**"看着对"的 `where = ["src", "."]` 同样错**（默认根把 benchmark 映射到不存在的 `src/benchmark`） |
| **K48** | **release zip 的确定性 = "同 dist → 同 zip"**（`ZIP_STORED` + 条目显式 sort + 固定 `date_time` + `create_system=0`）；**exe 构建本身不承诺跨机字节一致** | `tools/make_release.py` + `tests/guards/test_release_tooling.py` | 不排序则两次打包字节不同而**两次都成功**；把 exe 哈希写成"可复现"是假的 |
| **K49** | **产物扫描的豁免裁决 = "官方原件同串比对"实算**（命中的串在上游原件中同串存在 → `UPSTREAM`），**不是手写豁免清单**；被裁决项**仍打印计数** | `tools/audit_desensitize.py::scan_dist`/`_upstream_contains` | 手写清单会随依赖版本漂移失效；不打印 = 豁免变黑洞 |
| **K50** | **产物在仓库树外，审计器必须支持 `--dist-path`** | `tools/audit_desensitize.py` | 二者叠加会让"产物扫描"**扫了个空**（静默空扫比不扫更坏） |
| **K51** | **发布工具链落 `tools/`，不做 `rcc` 子命令** | `tools/make_release.py` | `rcc` 是发给用户的 CLI；发布工具进 `rcc` = 随包发给用户 + 拖进门禁扫描面 |
| **K52** | **checksum 留档不留空行**（GNU `sha256sum -c` 对空行报 `improperly formatted`） | `plan/DIST-sha256-M6.txt` | 刷屏的校验命令会让读者不再看它的输出 |
| **K53** | **冒烟必须覆盖"用户真敲的那条通路"**：CI 的 CLI 冒烟含**裸 `rcc`** 形式，不只是 `python -m rcc.cli` | `.github/workflows/ci.yml` | M6 头号缺陷正因"用 `python -m` 冒烟"而长期隐形 |
| **K54（M7 新增）** | **随包数据必须在安装面内**：数据住 `src/rcc/data/`，`pyproject.toml` 声明 `[tool.setuptools.package-data] rcc = ["data/**/*"]`；`find_data_dir()` 的**包内分支排在 `repo_root()` 之前** | `pyproject.toml` + `src/rcc/packaging.py` + `tests/guards/test_install_smoke.py` | 数据在包外 = **wheel 里零数据文件**，装完 `selftest`/`bench`/`run` 全挂，而 editable 态的 CI 全绿（它永远命中仓库根） |
| **K55（M7 新增）** | **数据路径的唯一来源是 `rcc.packaging.PACKAGE_DATA_REL`**（`= "src/rcc/data"`）：生成器、门禁、发布物对账都从它推，任何位置不得再写一份 `"src/rcc/data"` 字面量 | `src/rcc/packaging.py` + `tools/{gen_params,gen_samples,gen_truth,fetch_snapshots,check_literals,make_release}.py` + `tests/conftest.py` | 两处各写一份 = 第二份真相；下次搬目录时必有一处漏改而门变绿 |
| **K56（M7 新增）** | **G-PACK 的"布局一致"基准是数据根**（不是仓库根）：`包内路径 == "data/" + relpath(源, package_data_dir())` | `tests/guards/test_pack_gate.py` | 判定强度不变（拍平仍立刻红）；但基准必须跟着数据位置走，否则搬家后门测的是别的东西 |
| **K57（M7 新增）** | **构建类门禁必须从仓库树外的干净副本构建**：`pip wheel .` 会复用仓库里残留的 `build/lib/`，其中可能已有上一轮的 `rcc/data/` | `tests/guards/test_install_smoke.py::_clean_source_copy` + `.github/workflows/ci.yml` 装态步 | **实测过**：直接从仓库树内构建时，删掉 `package-data` 两条门仍全绿（负控假绿） |
| **K58（M7 新增）** | **错误口径按"是配置问题还是判定问题"分**：数据目录缺失 → `输入不可用: …` + **exit 2**（与 `run`/`check` 一致），不是 traceback + exit 1 | `src/rcc/cli.py::cmd_bench` + `tests/integration/test_cli.py` | exit 1 的语义是"检出不符合/未达标"；拿它报配置错误会让读者去改错的东西 |
| **K59（M7 新增）** | **文档里写死的数字必须有守门**：README 的测试数由 `tests/guards/test_repo_gates.py::test_readme_test_count_matches_collection` 与 `--collect-only` 比对 | `tests/guards/test_repo_gates.py` + `README.md` | M6 之后 README 写 317 而实测 321，**没有任何门会红**；没有守门的数字一定会漂 |
| **K60（M7 新增）** | **`license` 用 SPDX 字符串 + `license-files`**（PEP 639），`build-system` 下限抬到 `setuptools>=77` | `pyproject.toml` | TOML 表形态有硬期限（setuptools 报"2027-02-18 后不再支持"）；抬下限时不抬下限版本会直接被拒 |
| **K61（M7 新增）** | **floor=3.12**：`requires-python`、CI 矩阵、`test_stdlib_compat.py` 三处同源约束 | `pyproject.toml` + `.github/workflows/ci.yml` + `tests/guards/test_stdlib_compat.py` | 声明与守门各写一份 = 迟早对不上（判据已落在"解析后的值"上） |

---

## 四、M6 期实测发现的缺陷与陷阱（已处置，记此防复现）

1. **`benchmark/` 从未进安装面（M6 头号发现）**：`pyproject.toml` 只声明 `package-dir = {"" = "src"}` + `where = ["src"]`，而 `benchmark/` 在**仓库顶层**。三种运行方式里**只有一种挂**——源码态仓库根 `python -m rcc.cli bench`（CWD 恰好进 `sys.path`）能过、冻结态 `rcc.exe bench`（PyInstaller hiddenimports 显式收了它）能过、**装好的 `rcc bench` → `ModuleNotFoundError`**。
   **判别口诀：凡"包能不能被 import"，先问"它是被谁放到 sys.path 上的？"** 三种通路各自的 `sys.path` 来源不同（CWD / PyInstaller / 安装记录），一种通不等于另一种通。
   **修法**：`package-dir = {"": "src", "benchmark": "benchmark"}`。**第一版修法 `where = ["src", "."]` 看着对，实际把 benchmark 映射到不存在的 `src/benchmark`，安装当场失败**——所以判据要落在**解析结果**上，不是"配置里出现了 benchmark 这个词"。
2. **既有 G-README 门恰好用了"能过"的那种形式**：它跑 `python -m rcc.cli`（plan/04 §四 的 README 门），所以也看不见这个缺陷。**"门覆盖了 README"不等于"门覆盖了用户实际敲的命令"**。修法 = CI 冒烟补裸 `rcc` 一步（K53）。
3. **`sha256sum -c` 对空行报 `improperly formatted`**：GNU coreutils 的 checksum 解析把"空行后接下一行"当格式错误。留档去空行后复验干净。**同"误报会让门禁失效"**：刷屏的校验命令会被读者无视。
4. **产物按纪律落树外，审计器的 dist 模式却只认仓库内 `dist/`**：M5 把构建产物移出仓库树（避开 `out/` 被 gitignore），M6 的审计器若不动，产物扫描就在**正确纪律下扫了个空**。**改了一处的行为，要回头找"还有谁假设了旧行为"**。
5. **手写豁免清单是错的抽象**：产物里的 102 处 HARD 全在上游二进制，若写成"豁免这些文件名"，换依赖版本就漂移。**改为实算"该串是否在上游原件中出现"**——判据随实况变，不随人写死的清单变。
6. **`verify`/`check` 这类子命令要先有"变异验证"才算数**：G-RELEASE 的三条构建后断言各配一个变异（塞禁区目录 / 改包内数据一字节 / 加白名单外数据），三条各自报红。**"写了断言"与"断言有牙"是两件事**（M4/M5 同一条纪律）。

---

## 五、关键命令速查（M6 增补；其余见 `plan/HANDOFF-M6.md` §五）

```bash
# ---- 发布物组装（M6）----------------------------------------------------
# 1) 构建（dist/work 一律指向仓库树外；本机 TEMP 在 Git Bash 里是 /tmp）
py -3.12 -X utf8 -m PyInstaller --clean --noconfirm \
    --distpath "<树外>/dist" --workpath "<树外>/build" tools/rcc.spec

# 2) 构建后三断言（禁区成分 / 内嵌数据逐份 sha256 一致 / 白名单外多余）
py -3.12 -X utf8 tools/make_release.py check --dist "<树外>/dist/rcc"

# 3) 确定性自证（两次独立打包必须同 sha256）
py -3.12 -X utf8 tools/make_release.py verify --dist "<树外>/dist/rcc"

# 4) 打 release zip（归档内顶层 ASCII rcc/）
py -3.12 -X utf8 tools/make_release.py zip \
    --dist "<树外>/dist/rcc" --out "<树外>/rcc-v0.1.0-win64.zip"

# 5) sha256 台账（**重定向生成**，别手抄）
cd "<树外>" && sha256sum "rcc-v0.1.0-win64.zip" >> plan/DIST-sha256-M6.txt

# 6) 复验留档（三行全 OK、无告警）
sha256sum -c plan/DIST-sha256-M6.txt

# ---- 脱敏（M6 增补）------------------------------------------------------
# 产物本体扫描（产物在树外 → 必须显式 --dist-path）
py -3.12 -X utf8 tools/audit_desensitize.py --mode dist --dist-path "<树外>/dist/rcc"
# 四模式一次跑全（tracked/history/messages/dist）
py -3.12 -X utf8 tools/audit_desensitize.py

# ---- 干净环境验证（M6）---------------------------------------------------
git archive HEAD | tar -x -C "<树外新目录>"
cd "<树外新目录>" && py -3.12 -m venv v
NO_PROXY="*" no_proxy="*" ./v/Scripts/python.exe -m pip install -e ".[dev]"
./v/Scripts/python.exe -m pytest -q -rs                 # 319 passed / 3 skipped
./v/Scripts/rcc.exe bench                               # 裸控制台通路（用户真敲的那条）

# ---- 发布（三件套）------------------------------------------------------
# tag 打在**含完整收尾回写文档的提交**上
git tag -a v0.1.0 -m "..." && git push origin v0.1.0
gh release create v0.1.0 "<树外>/rcc-v0.1.0-win64.zip" \
    --verify-tag --notes-file <notes.md>
gh release view v0.1.0 --json assets,tagName,isDraft      # draft=false + 附件名在列
# 真下载复验：下载 → sha256 与留档比 → 解压中立目录跑 selftest
```

---

## 五之二、M7 期实测发现的缺陷与陷阱（已处置，记此防复现）

1. **"装完能不能用"是两种装态，M6 只验了一种**：M6 的发布验收走 **exe（冻结态）** 与
   **editable 安装**——两者都命中仓库根/内嵌数据。而 `pip install <wheel>` 是第三种形态，
   它既没有仓库根也没有 `_internal/`，于是 `find_data_dir()` 找不到 `data/`。
   **判别口诀：凡"数据在哪"的问题，先列出"这份数据在每种交付形态下分别从哪条路来"，
   逐条造环境验，别拿一种形态的绿去代表其余。**
2. **editable 安装结构上问不到"包里的数据在不在"**：`pip install -e` 把仓库根放上
   `sys.path`，任何"从仓库根找文件"的代码都会成功。**这不是 CI 配置问题，是装态的语义差异**——
   要让门问得到，必须造一个**不含仓库根**的环境（全新 venv + 真 wheel + 中立 CWD）。
3. **构建类门禁会被上一轮残留骗绿**（本轮最值钱的一条）：第一版 `test_install_smoke.py`
   直接从仓库树内 `pip wheel .`，因为仓库里有 `build/lib/rcc/data/`（上一轮构建残留），
   即使把 `[tool.setuptools.package-data]` 整段删掉，wheel 里照样有数据 → **两条门全绿，
   负控失效**。改为从**仓库树外干净副本**构建后，负控才按预期全红。
   **口诀：门禁要验"当前声明能产出什么"，就必须在一个"只有当前声明"的树上跑。**
4. **数据路径会散落在六七个工具里**：`gen_params`/`gen_samples`/`gen_truth`/`fetch_snapshots`/
   `check_literals`/`make_release` 各自拼过 `REPO_ROOT + "data"`。迁目录时若不收敛到
   `PACKAGE_DATA_REL`，下一次搬家必有一处漏改，而**漏改的那处往往没有门**。
5. **`bench` 的裸 traceback 藏在 import 期**：`benchmark/runner.py` 在**模块层**解析
   `TRUTH_DIR`（为了让 `--only` 与门槛读取共用一处），于是数据缺失时异常在
   `from benchmark import runner` 那一刻抛出——`cmd_bench` 里原有的 `try` 包不住它。
   **口诀：捕获错误的 `try` 要从"第一个可能触及坏状态的动作"开始，import 也算动作。**

---

## 六、接续提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M7.md" 继续工作
```

（入库的本文件用相对路径 `plan/HANDOFF-M7.md`；启动命令由用户侧拼绝对路径。）

**项目状态一句话**：M0→M6 六期计划已全部走完，M7 做了一轮二次迭代（修 `pip install` 装态、
加装态门禁、对齐 floor 与元数据）。交付物已从"本地可用"推进到"别人能下载、能校验、
能在自己机器上跑起来"，M7 之后**`pip install` 也能跑**。
**若接续**：先读本文件 §二（后续可做的现状与前置问题）、§五之二（M7 的五个陷阱）与
`plan/RELEASE-M6.md`（未跑项的 ⬜ 与原因）。**M7 已 commit `0ecdbdc` 并推送**，CI run 39296693217
（windows 与 ubuntu 各 12 步）全绿，`Node.js 20 is deprecated` 注解归零。
