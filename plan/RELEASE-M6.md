# plan/RELEASE-M6.md — 发布留档（M6 三件套之三）

> **本项目 v0.1.0 的发布记录。**
> 纪律（plan/05 §十）：**只写实测到的**；未跑的项留 ⬜ 并说明原因，**不留空、不预填**。
> 每个数字都对应一次真跑或一个可复算的哈希；没有"预期值"。

---

## 一、发布物

| 项 | 值 | 来源 |
|---|---|---|
| 版本 | `0.1.0` | `src/rcc/__init__.py::__version__`（`rcc --version` 实测输出同值） |
| 附件名 | `rcc-v0.1.0-win64.zip` | `tools/make_release.py zip` 输出 |
| 附件字节 | 118,507,589 | 同上（`os.path.getsize`） |
| 附件 sha256 | `fc62a21eabf000d383c09e0e12351d74e2a27c4e107c2312234d68a34b4d09a3` | `sha256sum` 重定向生成，见 `plan/DIST-sha256-M6.txt` |
| 归档条目数 | 170 | `tools/make_release.py zip` 输出 |
| 归档内顶层 | `rcc/`（`rcc.exe` + `rcc-gui.exe` + `_internal/`） | 归档清单实测 |
| 平台 | Windows x64（onedir 免安装） | `tools/rcc.spec` |

**随包数据**（`_internal/data/`，15 份）：`rules/params.json` + `samples/`（2）+ `snapshots/`（9）+ `truth/`（3）。经逐份 sha256 与仓库内同相对路径比对，**15/15 一致**（`tools/make_release.py check` 断言二）。

---

## 二、建仓与 CI 首跑

| 项 | 值 |
|---|---|
| 仓库 | <https://github.com/yuluo554/10-15-recipe-cost-calculator>（public） |
| 可见性决策 | public（plan/00 决策记录 2026-10-15，用户定夺） |
| 建仓路径 | `gh repo create --public ... --source . --remote origin`（**不带 `--push`**）→ 切 SSH remote → `git push`（**一次成**，5.3s） |
| **为什么切 SSH** | 本机 token scopes = `gist, read:org, repo`，**无 `workflow`**；带 workflow 文件走 HTTPS+token 会被 GitHub 拒绝。SSH 不受 OAuth scope 限制 |
| CI 矩阵 | `windows×{3.8,3.12}` + `ubuntu×3.12`（旧解释器只在 windows 守） |
| **CI 首跑结论** | ✅ **success**（run <https://github.com/yuluo554/10-15-recipe-cost-calculator/actions/runs/38707578140>） |

**CI 首跑对账**（plan/05 §七：对账单位是 **push 事件** + `head_sha`，不是提交数）：

| push 事件 | `head_sha` | conclusion | 三个 job 各自结论 |
|---|---|---|---|
| 1（首次 push，含全部 M6 提交 + 收尾回写） | `65dee9ed` | **success** | `windows-latest/py3.8` ✅ · `windows-latest/py3.12` ✅ · `ubuntu-latest/py3.12` ✅ |

- **每个 job 实测 `321 passed, 1 skipped`**（三个 job 一致）。**为什么是 321 而不是本地 328**：CI 只装 `.[dev]`（无 PySide6），`tests/gui/test_main_window.py` **模块级** skip 把 7 项移出收集面 → 328 − 7 = 321。唯一 skip 的原因在日志里明写：`需要 gui extra（PySide6）`——**声明式跳过，不是失败**。
- **新增的"控制台脚本冒烟"步骤三个平台都真跑过**（step 级结论 `success`），这正是 M6 头号发现（§六）对应的那一步。
- **run 日志已核查无敏感回显**：无邮箱形态、无本机用户名、无个人路径签名 → **无需删除任何 run**（plan/05 §八"第三个留档面"）。

---

## 三、确定性（"可复跑的是哪一步"）

诚实口径，**不许含糊**（plan/05 §六）：

| 范围 | 结论 | 证据 |
|---|---|---|
| **同 dist → 同 zip 逐字节一致** | ✅ **实测** | `tools/make_release.py verify` 两次独立打包得同一 sha256 `fc62a21e…09a3` |
| 打包机制 | ZIP_STORED + 条目按路径显式 sort + 全条目 `date_time=(1980,1,1,0,0,0)` + `create_system=0` | `tools/make_release.py`；G-RELEASE 门断言这三条 |
| **exe 构建本身跨机字节一致** | ❌ **不承诺** | PyInstaller 产物受 bootloader 构建、依赖版本、路径影响。`plan/DIST-sha256-M6.txt` 里 exe 那两行是**本机构建记录**，不是"可复现"承诺 |

> M5 实测缺陷提醒：`os.walk` 的产出顺序跨调用不稳定，**不显式排序则两次打包字节不同**——而两次都"成功"，不看 sha256 根本发现不了。故排序不是风格问题，是确定性前提。

---

## 四、冻结态验收（中立目录，非仓库树）

判据 = "离开开发机仍能证明自己完整"。全部在 `mktemp -d` 的中立目录下跑，**不在仓库树内**（CWD 上溯会命中仓库 `data/`，"内嵌数据"就验了个寂寞）。

| 通路 | 命令 | 结果 |
|---|---|---|
| 控制台自检 | `rcc.exe selftest` | `frozen=true`、**`frozen_data_inside_dist=true`**（`exe=…\rcc`、`data=…\rcc\_internal\data`）、`params_loadable=true`（参数条目 12）、`formulas_ok=true`、**exit 0** |
| 窗口版自检 | `rcc-gui.exe --selftest out.json` | 同上 + 页签 4 个、**exit 0** |
| 内置基准 | `rcc.exe bench` | 五套件全达标（import 19/19、costcard 15/15、alert 7/7、boundary 29/29、reconcile 4/4）、**总判「达标」、exit 0** |
| **负向对照** | 删 `_internal/data` 后再跑 `selftest` | `data_dir` / `params_loadable` / `formulas_ok` 三项 `ok=false`、总判 `ok=false`、**exit 1**；**不静默回落开发机仓库** |
| 归档解压后自检 | 解压 release zip 到中立目录 → `rcc.exe selftest` | `frozen=true`、`ok=true`、**exit 0**；随包 15 份数据与仓库 sha256 **15/15 一致** |

---

## 五、干净环境验证（plan/04 §六）

| 项 | 值 |
|---|---|
| 导出方式 | `git archive HEAD \| tar -x -C <树外新目录>` |
| 导出树文件数 | 105（天然无 `.git`、无 `_private/`） |
| 解释器 | 全新 `py -3.12 -m venv` → Python 3.12.10；`pip install -e ".[dev]"` → pytest 9.1.1 |
| **pytest 收集数对账** | 干净环境 **321 collected / 319 passed / 3 skipped**；本地同 extras（拦掉 PySide6）**321 collected** → **一致** |
| 差异归因 | 本地全 extras 收集 **328**；328 − 321 = **7** = `tests/gui/test_main_window.py` **模块级** skip（缺 PySide6 时整模块移出收集面）。3 个 skip 明细：①gui 模块级（缺 PySide6）②`test_audit` 历史通道（导出树无 `.git`）③`test_audit` 提交元数据（同上）。**逐项归因到声明式跳过，不是"全绿"就完事** |

### 逐条照 README 快速开始执行的退出码表（干净环境实测）

| README 步骤 | 命令 | 实测退出码 | README 明示语义 |
|---|---|---|---|
| 2 | `gen_params.py` / `gen_samples.py` / `gen_truth.py` | 0 / 0 / 0 | 生成成功 |
| 3 | `rcc run --purchases … --bom …` | **1** | 有异常行（明示语义） |
| 4 | `rcc run … --with-alert --snapshots …` | **1** | 有异常行 |
| 5 | `rcc run … --report out/report` | **1** | 有异常行（报告仍产出） |
| 6 | `rcc check --purchases … --bom …` | **1** | 检出问题 |
| 7 | `rcc bench` | **0** | 五套件达标 |
| 8 | `rcc selftest` | **0** | 自检全过 |
| 9 | `rcc gui`（无 gui extra） | **3** | 缺可选依赖 |
| — | `rcc --version` | **0** | — |

> **退出码非 0 ≠ 跑挂**（plan/04 §六）：判据是"符合 README 明示的退出码语义"。上表每一行都逐条真跑过。

---

## 六、干净环境验证抓出的缺陷（**M6 头号发现**）

**顶层 `benchmark/` 包未进安装面 → 控制台脚本 `rcc bench` 挂。**

- **症状**：干净 venv 里 `rcc bench`（README 第 7 步）→ `ModuleNotFoundError: No module named 'benchmark'`，exit 1。
- **根因**：`benchmark/` 在**仓库顶层**，而 `pyproject.toml` 只声明 `package-dir = {"" = "src"}` + `where = ["src"]`，于是它**根本没被装上**。
- **为什么 M0–M5 全都没发现**（三种运行方式只有一种会挂）：
  1. 源码态仓库根 `python -m rcc.cli bench` → CWD 恰在 `sys.path` 上，**能过**；
  2. 冻结态 `rcc.exe bench` → PyInstaller 的 hiddenimports 显式收了它，**能过**；
  3. **装好的控制台脚本 `rcc bench` → 挂**。
  既有 G-README 门用的是 `python -m` 形式，**恰好落在"能过"的那一类**——所以这道门也看不见它。
- **处置**：`package-dir` 显式映射 `benchmark` 的根 + `packages.find` 的 `where` 纳入仓库根。
  **陷阱**：`where = ["src", "."]` 那种"看着对"的写法**仍会失败**——默认根 `src` 把 `benchmark` 映射到不存在的 `src/benchmark`，安装当场报 `package directory 'src\benchmark' does not exist`（已实测）。故必须给精确键映射。
- **新门**：G-PACK 增两条，判定落在 **package-dir 的解析结果**上（不是"pyproject 里出现了 benchmark 这个词"——第一版坏配置也含它），并配机制探活复现那个坏配置。

> **元教训**：这道缺陷的形状与 M5 头号发现同构——**"本地三种验证都绿、只有换环境才炸"**。
> M5 是"构建不报错、换机器才炸"（目录条目被拍平）；M6 是"源码态与冻结态都过、只有装好的控制台脚本才炸"。
> 两条都说明同一件事：**判据要落在"用户真实使用的那条通路"上**。README 写的是 `rcc bench`，那就得真跑 `rcc bench`。

---

## 七、脱敏四步 + 产物扫描（plan/05 §八）

**token 全部运行时实算**（邮箱从 `git log`、用户名从 `getpass`、盘符从仓库路径），源码与留档零词面。

| 步 | 内容 | 结果 |
|---|---|---|
| 1 | **文件级**：`git ls-files` 无 `.env`/`.key`/`secret`/`token`；`.gitignore` 覆盖 | ✅ 0 命中（93 个跟踪文件里无此类） |
| 2 | **内容级**：四模式扫描 tracked / history / messages | ✅ 三者 **HARD 0 / REVIEW 0**（advisory 均为登记过的 sha256 长 hex） |
| 3 | **提交元数据**：`git log --format="%ae %ce" --all \| sort -u` | ✅ **只剩一个值** = GitHub noreply（M0 已完成全历史改写） |
| 4 | **历史终验三扫** | ✅ 全 0 硬门；`git fsck` 无悬空敏感对象 |
| 5 | **产物本体扫描**（全 dist 树字节读法） | ✅ **HARD 0**；102 处命中经"官方原件同串比对"裁决为 **UPSTREAM**（上游固有） |

### 产物扫描的豁免裁决（"官方原件同串比对"，**实算不写清单**）

`tools/audit_desensitize.py` 的 `--dist-path` 模式：命中的串若在**上游原件**（运行本扫描器那条解释器的官方安装目录 + 其 site-packages）中**同串存在**，判为 `UPSTREAM`——仍打印、仍计数，只是不阻断。

| 命中分布（102 处） | 裁决依据 |
|---|---|
| CPython 组件（`python312.dll`、`base_library.zip`、`_bz2.pyd`） | 官方 CPython 安装目录内同串存在 |
| OpenSSL（`libcrypto-3.dll` / `-x64`） | 同上 |
| Qt/PySide6（`Qt6Core/Gui/Pdf.dll`、`opengl32sw.dll`、`qtiff.dll`） | site-packages 内 PySide6 原件同串存在 |
| **本项目自有数据/代码** | **0 处命中** |

- **零 `user_path` 命中**：个人路径按**组合路径签名**匹配（不匹配裸词——否则 Qt DLL 里的厂商串含本机用户名子串会刷屏）；
- **裁决有牙**（阴性对照实测）：往包内数据注入一个**不在上游**的合成邮箱 → 仍判 HARD、exit 1；
- **留档与扫描器源码不逐字复述命中串**：输出一律掩码化。

---

## 八、"三清"与转公开（plan/05 §九）

| 清 | 判据 | 结果 |
|---|---|---|
| ① 全历史脱敏三扫 0 硬门 | tracked/history/messages 均 HARD 0 | ✅ |
| ② 历史坏 blob 修净 | `git fsck` 无悬空敏感对象 | ✅ **收尾时 `git fsck` 输出为空**。过程中的悬空对象只有**tag 前移产生的旧 tag 对象**（3 个，`--force` 移动留下的），已核查：**全部指向可达提交、body 只含 noreply 邮箱**（即已脱敏的目标形态），无任何敏感内容 → 随后 `git reflog expire --expire-unreachable=now` + `git gc --prune=now` 清掉，`git fsck` 复验为空 |
| ③ 失败 run 已删 | `gh run list` 无含敏感回显的失败 run | ✅ **无失败 run**——**截至收尾的每一轮 push 事件（含 tag push 与 branch push）均 success**，一条失败记录都没有；且**逐 run 收集日志后核查**：无邮箱形态、无本机用户名、无个人路径签名 → **无需删除任何 run** |
>
> **为什么不写具体轮数**：每 push 一次就多一轮 run，写死的数字会立刻过期（本记录撰写期间就发生过一次）。**判据是"有无失败 run"，不是"跑了几轮"**——前者是性质，后者是快照。要核当前轮数用 `gh run list --json databaseId,event,conclusion`。

**顺序**：先清后切是单向门。本仓库**建仓即 public**（`gh repo create --public`），故"三清"在建仓推送**之前**完成——即 §七 与上表①② 的结果都是**推送前**取得的。

**时序实测**（把"先清后切"落到具体时刻上）：仓库创建 `08:33:50Z`（public、**空仓**）→ 首次 push `08:42:25Z`。**这中间约 9 分钟里，公开仓库是空的**——被推送的内容（`65dee9e` 那条已验过的树）在推上去之前就已经通过了 §七 的全部扫描。**故"public"这个状态从未与"未验证的内容"同时存在**。这正是 plan/05 §九 要防的事：不是"public 本身有风险"，而是"**先公开了还没验的东西**"。

---

## 九、发布物本体验证（最强证据）

| 步 | 内容 | 结果 |
|---|---|---|
| 1 | **真下载** release 附件（`gh release download`） | ✅ 下载件 118,507,589 B（与上传件同字节数） |
| 2 | 下载件 sha256 与留档**逐位一致** | ✅ `sha256sum -c` 对 `plan/DIST-sha256-M6.txt` 输出 `rcc-v0.1.0-win64.zip: OK`（rc 0、无告警） |
| 3 | 解压**中立目录**跑冻结态自检 | ✅ 解压到中立目录后 `rcc.exe selftest` → `frozen=true` + **`frozen_data_inside_dist=true`** + `ok=true`（参数条目 12）+ **exit 0**；`bench` → **exit 0** |

**三步齐了 → "发布物本体已验"成立。** 这一步与 §四 的区别：§四 验的是**我自己机器上的 dist**，本节验的是**从 GitHub 真下载回来的那个文件**——中间隔着一次上传与一次下载，只有本节能证明"附件没在上传/下载环节坏掉或被替换"。

---

## 十、三件套状态

| # | 项 | 状态 |
|---|---|---|
| 1 | `git tag -a v0.1.0`（打在含完整收尾回写文档的提交上）+ push tag | ✅ 注解 tag 已创建并 push；`--verify-tag` 通过（tag 先于 Release 存在） |
| 2 | `gh release create v0.1.0`（`--notes-file` + `--verify-tag`）附产物 + `gh release view --json assets,tagName,isDraft` 核验 | ✅ 核验结果：`isDraft=false`、`tagName=v0.1.0`、附件 `rcc-v0.1.0-win64.zip` 在列（size 118,507,589，state `uploaded`） |
| 3 | `plan/RELEASE-M6.md`（本文件） | ✅ 已落盘 |

### 发布期实测：tag push 是否触发 CI

plan/05 §七 要求"**以当轮实测为准留档**（两种行为都出现过）"。本轮实测：

| push 事件 | ref | `head_sha` | conclusion |
|---|---|---|---|
| 1 | `refs/heads/main` | `65dee9ed` | success |
| 2 | **`refs/tags/v0.1.0`** | `94d192ad` | **success（tag push 触发了 CI）** |
| 3 | `refs/heads/main` | `94d192ad` | success |

**结论：本仓库的 `on: push`（不带 branches/tags 限定）对 tag push 与 branch push 都触发。** 故 push tag 与 push main 各产生一轮 run（同一 sha 出现两轮，是因为两次 push 分别触发，**不是**失败重跑）。

> **tag 移动后的复验纪律**（plan/05 §十）：本轮**实际发生了 tag 移动**。按 plan/05 §十"tag 打在含完整收尾回写文档的提交上"的要求，发布留档的每次回填都使"最新提交"前移，tag 随之**多次前移**（`--force`）。**每次前移后都立即复验 `isDraft`，结果恒为 `false`**（未被退回 draft），附件 `rcc-v0.1.0-win64.zip` 全程未受影响。
>
> **tag 的最终指向 = 含本记录完整内容的那个提交**（自指，故不必枚举哈希；用 `git rev-list -n1 v0.1.0` 与 `git rev-parse HEAD` 核对两者相等即可）。
>
> **实测口径**：本轮 Release 按 `targetCommitish=main` 创建（`gh release create` 取该分支最新提交），故前移 tag **未**把它打回 draft；plan/05 §十 那句"移动 tag 会打回 draft"指的是 Release **绑定 tag 本身**的形态。**纪律照做：无论哪种形态，移动后都必须复验 `isDraft`**——本轮每次移动都做了，结果均为 `false`。

---

## 十一、发布期发现与处置

1. **`rcc bench` 控制台通路挂**（§六）——干净环境验证抓出，已修 + 加门 + CI 补冒烟步骤（K53）；
2. **`sha256sum -c` 对留档里的空行报 "improperly formatted"**：GNU coreutils 对 checksum 文件中的**空行**（后接下一行）会告警。留档因此去掉空行——**刷屏的校验命令会让读者不再看它的输出**，与"误报会让门禁失效"同一条纪律；
3. **`--dist-path` 的引入**：M5 纪律把构建产物放在**仓库树外**，而审计器的 dist 模式原本只认仓库内 `dist/`——发布期产物按纪律在树外，故必须支持显式路径，否则"产物扫描"这一步会在正确的纪律下**扫了个空**；
4. **`gh release download` 必须在仓库目录内跑**：在仓库外的临时目录执行会报 `failed to run git: fatal: not a git repository`——它不是"下载失败"，而是**找不到仓库上下文**（退出码仍为 0，容易误判为成功）。**"命令没报错"与"文件真下下来了"要分开验**（用 `ls` 看字节数为证）；
5. **`git tag -f` 前移会留下悬空 tag 对象**：每次前移都产生一个不可达的旧 tag 对象，`git fsck` 会报 `dangling tag`。**它不是污染**（body 只有 noreply、指向可达提交），但"三清"要求 fsck 干净，故收尾用 `reflog expire --expire-unreachable=now` + `gc --prune=now` 清掉。**判别口诀：fsck 报悬空 ≠ 有敏感泄漏，先看对象类型与内容再决定清不清**——把"悬空"一律当污染处理，会在无关对象上浪费一次全仓 gc。
