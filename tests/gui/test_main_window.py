"""GUI offscreen 冒烟：真装配窗口、真读页签、真走自检通路。

**为什么需要它**：三条 AST 门禁只能证明"界面层没有算术/没有越层 import"，证明
不了"窗口真能装配起来"。一块装不上的界面在源码态与静态检查里都是绿的，要到
用户双击 exe 时才现形。

**依赖纪律**（plan/04 §一、§五）：本文件 import 重件，故用模块级
``importorskip`` 声明式跳过——没有 gui extra 的机器跳过本文件**是合法形态**。
"分层门禁类测试不许整体 skip" 那条约束落在 ``tests/guards/``（AST 三条）与
``tests/gui/test_layering_behavior.py``（不 import 重件，恒跑）。

**offscreen 由 ``tests/gui/conftest.py`` 在模块层设好**——Qt 只在创建
``QApplication`` 时读 ``QT_QPA_PLATFORM``，测试函数里再设已太晚。
"""

import json
import os
import subprocess
import sys

import pytest

# ``exc_type=ImportError`` 显式声明：pytest 9.1 起，模块被找到但 import 抛
# ImportError 时默认不再跳过而是报错。本文件想要的语义正是"缺依赖即跳过"
# （plan/04 §一 允许 GUI 交互测试声明式跳过），故显式写出来，别让它在新版
# pytest 上从"跳过"变成"红"。
# 模块级声明式跳过（缺 gui extra 的机器上跳过本文件是合法形态，plan/04 §一）。
# **不用 ``pytest.importorskip``**：它的 ``exc_type`` 参数是 pytest 8.2+ 才有，
# 而本项目底线解释器（py3.8）上的 pytest 是 7.4——传它当场 TypeError，不传又在
# pytest 9.1+ 变成"模块被找到但 import 失败即报错"。手工 try/except + 模块级
# ``pytest.skip`` 在两个版本上语义一致，且把"缺依赖"与"依赖坏了"一并归入跳过。
try:
    import PySide6
except ImportError as _exc:  # pragma: no cover - 取决于运行环境是否装了 gui extra
    pytest.skip("需要 gui extra（PySide6）: %s" % _exc, allow_module_level=True)

from rcc.gui import main_window  # noqa: E402


class TestWindowAssembly:
    """真装配：页签数、标题、关于页签的版本行。"""

    def test_build_window_assembles_all_tabs(self):
        app, window, tab_count = main_window.build_window()
        try:
            assert tab_count == len(main_window.TABS), (
                "装配出的页签数 %d 与登记数 %d 不符" % (tab_count, len(main_window.TABS)))
            assert tab_count > 0, "页签数为 0（空窗口也算装配成功？）"
            tabs = window.centralWidget()
            assert tabs is not None, "主窗口没有中央控件"
            names = [tabs.tabText(index) for index in range(tabs.count())]
            assert names == list(main_window.TABS), "页签顺序/名称与登记不符: %s" % names
        finally:
            window.close()
            app.quit()

    def test_about_tab_shows_version_and_disclaimer(self):
        """「关于」页必须带版本号与免责声明——这两句是用户可见承诺。"""
        from rcc import __version__

        app, window, _count = main_window.build_window()
        try:
            tabs = window.centralWidget()
            page = tabs.widget(main_window.TABS.index("关于"))
            texts = [child.text() for child in page.findChildren(object)
                     if hasattr(child, "text") and callable(child.text)]
            joined = " ".join(texts)
            assert __version__ in joined, "关于页未显示版本号"
            assert "辅助" in joined or "免责" in joined, "关于页未显示免责口径"
        finally:
            window.close()
            app.quit()

    def test_build_app_returns_exit_code(self, monkeypatch):
        """``build_app()`` 必须返回整数退出码（CLI 直接拿它当进程退出码）。"""
        executed = {}

        def fake_exec(self):
            executed["called"] = True
            return 0

        monkeypatch.setattr(PySide6.QtWidgets.QApplication, "exec", fake_exec)
        code = main_window.build_app()
        assert executed.get("called"), "build_app 未调用 app.exec()（窗口根本没进事件循环）"
        assert isinstance(code, int), "build_app 返回的不是退出码: %r" % (code,)


class TestGuiSelftestChannel:
    """``rcc gui`` 的脚本化验收通路：``--selftest <输出文件>``。

    窗口版 stdout 不接终端，这条通路是**唯一**能脚本化验收窗口 exe 的方式。
    本机装了 gui extra 时以源码态跑一遍——冻结态的那一遍在 M5 的 exe 验收里做
    （源码态证明不了"数据随包走"）。
    """

    def test_launcher_selftest_writes_json_and_exits_zero(self, repo_root, tmp_path):
        out = tmp_path / "gui-selftest.json"
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONPATH"] = os.path.join(repo_root, "src") + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, os.path.join(repo_root, "tools", "launcher_gui.py"),
             "--selftest", str(out)],
            capture_output=True, cwd=repo_root, env=env,
            encoding="utf-8", errors="replace")
        assert proc.returncode == 0, "自检退出码应为 0: %s%s" % (proc.stdout, proc.stderr)
        assert out.exists(), "自检未产出 JSON 文件（窗口版唯一的回传通路断了）"

        report = json.loads(out.read_text(encoding="utf-8"))
        assert report["ok"] is True, report
        assert report["tab_count"] == len(main_window.TABS)
        assert report["param_count"] > 0, "生效参数数为 0（随包参数没读到）"
        names = {check["name"] for check in report["checks"]}
        assert "tabs_assembled" in names, "自检未覆盖窗口装配（装不上也算过？）"

    def test_launcher_selftest_requires_output_path(self, repo_root):
        """缺输出路径 → 用法错误（exit 2），不静默当"自检通过"。"""
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONPATH"] = os.path.join(repo_root, "src") + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, os.path.join(repo_root, "tools", "launcher_gui.py"),
             "--selftest"],
            capture_output=True, cwd=repo_root, env=env,
            encoding="utf-8", errors="replace")
        assert proc.returncode == 2, (
            "缺输出路径时应报用法错误 exit 2，实际 %d" % proc.returncode)


class TestSelftestDoesNotDependOnHeavyDeps:
    """核心自检**不得**依赖重件——否则 CLI 的 ``selftest`` 在没装 gui 的机器上会挂。"""

    def test_core_selftest_runs_without_gui_import(self, repo_root):
        """在**禁掉 PySide6** 的子进程里跑核心自检，必须仍能出结论。"""
        # 造出一个真的拦住 PySide6 的 meta_path 拦截器
        probe = (
            "import sys\n"
            "class Blocker:\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            "        if name.split('.')[0] == 'PySide6':\n"
            "            raise ImportError('PySide6 blocked by probe')\n"
            "        return None\n"
            "sys.meta_path.insert(0, Blocker())\n"
        )
        code = (
            "from rcc import selftest\n"
            "report = selftest.run_selftest()\n"
            "print('OK' if report.get('ok') else 'FAIL')\n"
        )
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = os.path.join(repo_root, "src") + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-c", probe + code],
            capture_output=True, cwd=repo_root, env=env,
            encoding="utf-8", errors="replace")
        assert "OK" in (proc.stdout or ""), (
            "禁掉 PySide6 后核心自检失败——自检被重件污染了？\n%s%s"
            % (proc.stdout, proc.stderr))


def test_gui_layer_has_no_business_logic_in_tabs():
    """页签装配只做展示：TABS 是纯字符串登记表，不含判定文案。

    这条防止"界面里长出第二份口径"——比如把"预警阈值"之类的业务常量写进页签名。
    """
    assert all(isinstance(name, str) and name for name in main_window.TABS)
    assert len(set(main_window.TABS)) == len(main_window.TABS), "页签名重复"
