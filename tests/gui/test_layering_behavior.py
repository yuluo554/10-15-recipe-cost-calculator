"""GUI 分层纪律的**行为**验证（不依赖 PySide6，恒跑）。

``tests/guards/test_gates.py`` 用 AST 静态断言守住"界面层不 import 规则层 /
无算术 / 无业务数值"，那是**形状**上的保证。本文件补**行为**上的那一半：
``rcc.gui`` 被 import 时**不得**把 PySide6 拉进解释器。

这条性质不是修饰——``cli.cmd_gui`` 的 ``try/except ImportError`` 之所以能包住
"从 import 到调用完成"的整段，前提正是"import 本身不触及重件"，缺依赖的异常
只在 ``build_app()`` 才抛。若哪天有人在 ``gui/__init__.py`` 顶层 import 了 Qt，
AST 的 import 断言（只看规则层）抓不到，而 CLI 的缺依赖通路会当场变形。

**不用 ``importorskip``**：本文件不 import PySide6，只断言它"没被 import"，
故在没有 gui extra 的机器上同样必须执行（plan/04 §五：分层门禁类恒跑）。
"""

import os
import subprocess
import sys

import pytest

# 在子进程里做——本测试进程可能已因别处 import 过 PySide6，测不出"导入 rcc.gui
# 是否顺带拉起重件"。探活代码插在**检查之前**，让它在 print 前显式 import 重件
# （拼在检查之后，探活就永远看不到它）。逐行拼接而非分号串联——分号拼接一旦拼出
# 语法错误，探活会**静默 skip** 掉，而那正是"假门"的又来一次。
def _probe_script(extra_code=""):
    lines = ["import sys", "import rcc.gui"]
    if extra_code:
        lines.append(extra_code)
    lines.append("print('HEAVY' if 'PySide6' in sys.modules else 'LIGHT')")
    return "\n".join(lines)


def _run_probe(repo_root, extra_code=""):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.path.join(repo_root, "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", _probe_script(extra_code)],
        capture_output=True, cwd=repo_root, env=env,
        encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def test_importing_gui_does_not_pull_pyside6(repo_root):
    """``import rcc.gui`` 必须保持轻量——重件只在函数体内 import。"""
    code, out, err = _run_probe(repo_root)
    assert code == 0, "探测子进程失败: %s" % err
    assert out == "LIGHT", (
        "import rcc.gui 把 PySide6 拉进了 sys.modules——"
        "重件必须留在函数体内（CLI 的缺依赖通路依赖此性质）")


def test_probe_would_detect_a_heavy_import(repo_root):
    """**机制探活**：探测必须真读 ``sys.modules``——喂它一个重件就得报 HEAVY。

    本文件**不许依赖 gui extra**（它在没装 PySide6 的机器上、以及"装了但坏掉"
    的机器上都照样要跑），故探活不假定 PySide6 可用：先试真件，装不上就放一个
    合成同名模块进 ``sys.modules``。**两条路径都必须报 HEAVY**——任何一条静默
    变成 skip，"这道探活有效"就退化成一句没有证据的话。
    """
    extra = (
        "try:\n"
        "    import PySide6\n"
        "except ImportError:\n"
        "    import types\n"
        "    import sys as _sys\n"
        "    _sys.modules['PySide6'] = types.ModuleType('PySide6')\n"
    )
    code, out, err = _run_probe(repo_root, extra)
    assert code == 0, "探测子进程失败（机制探活不可达）: %s" % err
    assert out == "HEAVY", "探测机制失效：注入重件后仍报 LIGHT"


def test_gui_directory_has_no_top_level_heavy_import(repo_root):
    """静态复核：``gui/`` 下任何模块都不得在**模块层** import PySide6。

    与行为断言互为交叉验证——行为断言在"装了 PySide6 且恰好没被别的路径预载"
    时才最灵敏，静态断言则不受运行时状态影响。
    """
    import ast

    offenders = []
    gui_dir = os.path.join(repo_root, "src", "rcc", "gui")
    for dirpath, _dirnames, filenames in os.walk(gui_dir):
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            path = os.path.join(dirpath, filename)
            tree = ast.parse(open(path, "r", encoding="utf-8").read())
            for node in tree.body:  # 只看模块层，不看函数体内
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] == "PySide6":
                            offenders.append("%s:%d" % (filename, node.lineno))
                elif isinstance(node, ast.ImportFrom):
                    if (node.module or "").split(".")[0] == "PySide6":
                        offenders.append("%s:%d" % (filename, node.lineno))
    assert not offenders, "gui/ 模块层 import 了 PySide6（分层纪律）: %s" % offenders
