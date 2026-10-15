# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir 双 exe 构建规格（plan/05 §一、§三）。

产出**一个 onedir 目录**、两个可执行文件：``rcc.exe``（控制台）与
``rcc-gui.exe``（窗口版）。两者共享 ``_internal/``——随包数据只需登记一次，
也因此 "数据目录落在 exe 目录之内" 这条自检对**两个 exe 同时成立**。

三条纪律（由 ``tests/guards/test_pack_gate.py`` 的 G-PACK 门守住）：

1. **datas 只由 ``rcc.packaging.build_datas()`` 产生**——本文件不得手写任何数据
   路径。手写路径的失效模式是"白名单改了、spec 没跟着改"，而构建不报错，
   直到换台机器才发现随包数据缺了；
2. **不得出现禁区字面**（``plan`` / ``tests`` / ``_private`` / ``.git``）——版权
   原文与开发过程材料绝不能进发行包；
3. **构建前先对账白名单**：``data/`` 下出现未登记目录即构建失败，堵住"新数据
   目录悄悄没进包"（构建后扫描才发现时，产物已经发出去了）。
"""

import os
import sys

_REPO_ROOT = os.path.dirname(SPECPATH)
_SRC = os.path.join(_REPO_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from rcc.packaging import (  # noqa: E402
    build_datas,
    unregistered_data_dirs,
)

_unregistered = unregistered_data_dirs(_REPO_ROOT)
if _unregistered:
    raise SystemExit(
        "data/ 下存在未登记进白名单的目录（会静默不进包）: %s" % _unregistered)

# 随包数据：**唯一来源**是白名单构建器，本文件不出现任何数据路径字面。
DATAS = build_datas(_REPO_ROOT)

# 延迟导入的模块：PyInstaller 的静态分析跟得到函数体内的 import，但基准包
# （顶层 ``benchmark/``，不在 src/ 下）与报告层导出属"只在某个子命令路径上才
# 触及"的模块，显式登记以免构建出"跑 bench 时 ModuleNotFoundError"的 exe。
_LAZY = [
    "benchmark",
    "benchmark.cases",
    "benchmark.runner",
    "rcc.report.export",
    "rcc.report.sections",
]

_ENTRY_DIR = os.path.join(_REPO_ROOT, "tools")
_PATHEX = [_SRC, _REPO_ROOT]


def _analysis(script, hiddenimports, datas):
    return Analysis(
        [os.path.join(_ENTRY_DIR, script)],
        pathex=_PATHEX,
        binaries=[],
        datas=datas,
        hiddenimports=list(hiddenimports),
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        # 禁区包不进包：GUI 分析不得把 test/开发工具链拖进来
        excludes=["pytest", "PyInstaller", "yaml"],
        noarchive=False,
        optimize=0,
    )


# ---- 通道一：控制台 CLI（无 Python 机器上的脚本化验证通路） ----------------
a_cli = _analysis("launcher_cli.py", _LAZY, DATAS)
pyz_cli = PYZ(a_cli.pure)
exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="rcc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# ---- 通道二：窗口版 GUI（重件 PySide6 只在此分析里收集） --------------------
# 数据登记在 CLI 分析里（仓库白名单那 15 份），**两边都传给 COLLECT**：PyInstaller
# 的静态分析会跟进函数体内的 import（`rcc.cli` → `cmd_gui` → `rcc.gui.main_window`
# → PySide6），于是**两个分析各自都收集到了一份 Qt 的 datas**（插件/翻译/字体）。
# 只传 a_cli.datas 也能出可用的包——但那是在赌"两个分析的 Qt datas 恰好相同"：
# 只要哪天 GUI 侧多收集一个文件，它就会**静默不进包**，而构建不报错、CLI 侧还
# 照跑。两边的 datas 全传，去重交给 COLLECT。
a_gui = _analysis("launcher_gui.py", _LAZY + ["rcc.gui.main_window"], [])
pyz_gui = PYZ(a_gui.pure)
exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="rcc-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe_cli,
    a_cli.binaries,
    a_cli.datas,
    exe_gui,
    a_gui.binaries,
    a_gui.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="rcc",
)
