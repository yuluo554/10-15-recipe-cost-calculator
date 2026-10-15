# HANDOFF-M7 收官快照（M6 之后）

> 上一里程碑：**M6 发布**（已完成，2026-10-15）
> 下一里程碑：**无**（六期计划 M0→M6 已全部走完）。本文件是**收官快照**，供"二期/维护/换人接手"接续。
> 含六节：进度+证据 / 后续可做（非承诺） / 既定口径 K 清单（增补）/ 环境坑（增补）/ 命令速查 / 接续提示词

---

## 一、M6 出口状态与证据

| 项 | 状态 | 证据 |
|---|---|---|
| **公开仓库** | ✅ | <https://github.com/yuluo554/10-15-recipe-cost-calculator>（public）；`gh repo create --public ... --source . --remote origin`（**不带 `--push`**）→ 切 SSH remote → push |
| **CI 首跑** | ✅ | 见 `plan/RELEASE-M6.md` §二（矩阵 `windows×{3.8,3.12}` + `ubuntu×3.12`）；**新增"控制台脚本冒烟"一步**（`rcc` 裸命令形式，见 §四 头号发现） |
| **确定性 release 产物** | ✅ | `tools/make_release.py`：`rcc-v0.1.0-win64.zip`，170 条目 / 118,507,589 B / sha256 `fc62a21e…09a3`；`verify` 两次独立打包**同 sha256** |
| **sha256 留档** | ✅ | `plan/DIST-sha256-M6.txt`（哈希行由 `sha256sum` 重定向生成，人只写注释）；`sha256sum -c` 复验三行全 `OK`、**无告警** |
| **发布留档** | ✅ | `plan/RELEASE-M6.md`（只写实测到的，未跑的项留 ⬜） |
| **冻结态验收** | ✅ | 中立目录：`selftest` → `frozen=true` + `frozen_data_inside_dist=true` + exit 0；`bench` → 达标 exit 0；`rcc-gui.exe --selftest` → 页签 4 + exit 0；**负向对照**删 `_internal/data` → `ok=false` + exit 1 |
| **干净环境验证** | ✅ | `git archive` 导出树 → 全新 venv（Python 3.12.10 / pytest 9.1.1）→ **319 passed / 3 skipped / 321 collected**；收集数与本地同 extras **一致**；README 快速开始 9 行退出码逐条实测 |
| **脱敏四步 + 产物扫描** | ✅ | tracked/history/messages 均 **HARD 0**；提交元数据只剩 noreply；`git fsck` 无悬空对象；**产物本体** 102 处命中经"官方原件同串比对"**实算**裁决为 `UPSTREAM`，本项目自有数据与代码 **0 处** |
| **M6 头号发现（已修 + 加门）** | ✅ | 顶层 `benchmark/` 未进安装面 → **`rcc bench` 控制台通路挂**（详见 §四） |
| **测试** | ✅ | 双解释器 **328 passed**（收集数一致） |

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

## 六、接续提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M7.md" 继续工作
```

（入库的本文件用相对路径 `plan/HANDOFF-M7.md`；启动命令由用户侧拼绝对路径。）

**项目状态一句话**：M0→M6 六期计划已全部走完——确定性规则引擎 + 五套件基准 + 免安装双 exe +
确定性 release 产物 + 公开仓库与 CI，交付物已从"本地可用"推进到"别人能下载、能校验、能在自己机器上跑起来"。
**若接续**：先读本文件 §二（后续可做的现状与前置问题）与 `plan/RELEASE-M6.md`（未跑项的 ⬜ 与原因）。
