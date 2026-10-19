"""零字面量门禁测试 + 冻结产物位级一致 + 分层门禁。

三条纪律各自独立：

1. **零字面量**：业务数值只能来自参数包，抄进代码即拦下（扫描面含 docstring 与注释）；
2. **冻结产物**：生成器 ``--check`` 位级一致（手改即红）；
3. **GUI 分层**：AST 三条齐上（不 import 规则层 + 无算术运算 + 无禁用数值字面量）。
"""

import ast
import os
import subprocess
import sys

import pytest

from rcc.model import MONEY_EXP, RATE_EXP


def _run_tool(repo_root, script, *args):
    """跑 tools/ 下的脚本，返回 ``(returncode, stdout+stderr)``。"""
    cmd = [sys.executable, os.path.join(repo_root, "tools", script)] + list(args)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(cmd, capture_output=True, cwd=repo_root, env=env)
    output = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    return proc.returncode, output


# ------------------------------------------------------------ 零字面量门禁

def test_literal_gate_passes(repo_root):
    code, output = _run_tool(repo_root, "check_literals.py")
    assert code == 0, "零字面量门禁报红:\n%s" % output
    assert "LITERAL_GATE_OK" in output


def test_literal_gate_selftest(repo_root):
    """阳性/阴性对照——**无自检的门禁可能一直是空扫**。"""
    code, output = _run_tool(repo_root, "check_literals.py", "--selftest")
    assert code == 0, output
    assert "LITERAL_GATE_SELFTEST_OK" in output


def test_literal_gate_detects_injected_value(repo_root, params_path, tmp_path):
    """**变异验证**：注入一个禁用数值 → 门禁必须报红。"""
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import check_literals

    tokens = check_literals.banned_tokens(params_path)
    assert tokens, "token 集为空（门禁会恒绿）"
    probe = tokens[0]
    hits = check_literals.scan_text("value = %s\n" % probe, tokens)
    assert hits, "注入禁用数值 %r 后门禁未报红（假门）" % probe


def test_literal_gate_clean_text_passes(repo_root, params_path):
    """阴性对照：干净源码不得报红。"""
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import check_literals

    tokens = check_literals.banned_tokens(params_path)
    assert not check_literals.scan_text("net = purchase / rate\n", tokens)


def test_literal_tokens_are_computed_not_hardcoded(repo_root, params_path):
    """token 必须**运行时实算**自参数包，源码零词面。"""
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import check_literals

    tokens = set(check_literals.banned_tokens(params_path))
    # 参数包里的净料率原值必须出现在 token 集里
    import json

    with open(params_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    for entry in data["yield_rates"].values():
        assert entry["value"] in tokens, "净料率 %s 未进 token 集" % entry["value"]


def test_quantize_precision_is_exempt(repo_root, params_path):
    """精度/基数约定豁免（否则门禁会因量化常数刷屏）。"""
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import check_literals

    tokens = set(check_literals.banned_tokens(params_path))
    for exp in (MONEY_EXP, RATE_EXP):
        assert format(exp.normalize(), "f") not in tokens


# -------------------------------------------------------- 冻结产物位级一致

def test_frozen_params_bit_identical(repo_root):
    """参数包是冻结产物——重生成必须逐字节一致。"""
    code, output = _run_tool(repo_root, "gen_params.py", "--check")
    assert code == 0, output
    assert "FROZEN_PARAMS_OK" in output


def test_frozen_samples_bit_identical(repo_root):
    code, output = _run_tool(repo_root, "gen_samples.py", "--check")
    assert code == 0, output
    assert "FROZEN_SAMPLES_OK" in output


def test_frozen_check_detects_drift(repo_root, tmp_path):
    """**变异验证**：改动冻结件后 --check 必须报红。"""
    import shutil

    src = os.path.join(repo_root, "src", "rcc", "data", "rules", "params.json")
    target_dir = tmp_path / "rules"
    target_dir.mkdir(parents=True)
    drifted = target_dir / "params.json"
    shutil.copyfile(src, str(drifted))
    with open(str(drifted), "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n")

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [sys.executable, os.path.join(repo_root, "tools", "gen_params.py"),
           "--check", "--out", str(drifted)]
    proc = subprocess.run(cmd, capture_output=True, cwd=repo_root, env=env)
    assert proc.returncode == 1, "改动冻结件后 --check 未报红（假门）"


def test_generators_are_deterministic_across_runs(repo_root):
    """同 seed 两次运行必须同结果（禁 stdlib random / set 序 / 时钟）。"""
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import importlib

    for name in ("gen_params", "gen_samples"):
        module = importlib.import_module(name)
        importlib.reload(module)
        first = module.outputs() if name == "gen_samples" else module.render(module.build_params())
        importlib.reload(module)
        second = module.outputs() if name == "gen_samples" else module.render(module.build_params())
        assert first == second, "%s 两次运行结果不同（不确定）" % name


def test_detrng_is_cross_version_stable(repo_root):
    """自研 splitmix64：固定 seed 必得固定序列（不依赖解释器版本）。"""
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    from detrng import SplitMix64

    rng = SplitMix64(20261015)
    seq = [rng.next_u64() for _ in range(5)]
    rng2 = SplitMix64(20261015)
    assert seq == [rng2.next_u64() for _ in range(5)]
    assert len(set(seq)) == len(seq), "序列应无明显重复"


# ------------------------------------------------------------- GUI 分层门禁

GUI_DIR = os.path.join("src", "rcc", "gui")
# 允许的取数入口（唯一）
ALLOWED_GUI_IMPORTS = ("..engine.pipeline", ".engine.pipeline")


def _gui_modules(repo_root):
    target = os.path.join(repo_root, GUI_DIR)
    for dirpath, _dirnames, filenames in os.walk(target):
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield os.path.join(dirpath, filename)


def test_gui_does_not_import_rule_or_engine_internals(repo_root):
    """断言一：界面层不得直接 import 规则层/引擎内部模块。"""
    offenders = []
    for path in _gui_modules(repo_root):
        tree = ast.parse(open(path, "r", encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
                if any(bad in module for bad in ("rules", "alert", "io", "report")):
                    offenders.append("%s: from %s" % (os.path.basename(path), module))
    assert not offenders, "界面层直接 import 了规则层/内部模块: %s" % offenders


def test_gui_has_no_arithmetic(repo_root):
    """断言二：界面层不得含算术运算（防"界面里直接算"）。

    判据：`BinOp` 且**两侧操作数均非字符串字面量**——任一侧是字符串字面量
    即为排版/格式化（`"tab_%s" % name`、`"a" + "b"`），不算算术。
    """
    banned = (ast.Mult, ast.Div, ast.Sub, ast.FloorDiv, ast.Mod, ast.Pow)
    offenders = []
    for path in _gui_modules(repo_root):
        tree = ast.parse(open(path, "r", encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, banned):
                if _is_string_operand(node.left) or _is_string_operand(node.right):
                    continue  # 字符串排版/格式化
                offenders.append("%s:%d %s" % (os.path.basename(path), node.lineno,
                                               type(node.op).__name__))
    assert not offenders, "界面层含算术运算: %s" % offenders


def _is_string_operand(node):
    """该操作数是否为字符串字面量（含 f-string / 相邻字符串拼接）。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.JoinedStr):  # f-string
        return True
    return False


def test_gui_has_no_business_numeric_literals(repo_root, params_path):
    """断言三：界面层不得内联业务数值（与引擎侧同一份 token 集）。"""
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import check_literals

    tokens = check_literals.banned_tokens(params_path)
    offenders = []
    for path in _gui_modules(repo_root):
        text = open(path, "r", encoding="utf-8").read()
        for token, line_no, _line in check_literals.scan_text(text, tokens):
            offenders.append("%s:%d" % (os.path.basename(path), line_no))
    assert not offenders, "界面层内联业务数值: %s" % offenders


def test_gui_ast_guards_are_not_vacuous(repo_root):
    """**机制探活**：确认三条 AST 断言真能抓出违规（防恒绿假门）。"""
    banned = (ast.Mult, ast.Div, ast.Sub)
    bad_source = "def f(x):\n    return x * 2\n"
    tree = ast.parse(bad_source)
    found = [n for n in ast.walk(tree)
             if isinstance(n, ast.BinOp) and isinstance(n.op, banned)]
    assert found, "算术探测机制失效"

    bad_import = "from ..rules import formulas\n"
    tree = ast.parse(bad_import)
    found = [n for n in ast.walk(tree)
             if isinstance(n, ast.ImportFrom) and n.module
             and any(b in n.module for b in ("rules", "alert", "io", "report"))]
    assert found, "import 探测机制失效"


def test_gui_lazy_import_scope_is_covered(repo_root):
    """惰性导入的 try 必须包住**从 import 到调用完成**的整段。

    分层守门要求重件只在函数体内 import ⇒ ``import rcc.gui`` 本身永不抛
    ImportError，真正的缺依赖异常在 ``build_app()`` 才抛。所以 CLI 的 try
    必须覆盖调用。
    """
    cli_path = os.path.join(repo_root, "src", "rcc", "cli.py")
    source = open(cli_path, "r", encoding="utf-8").read()
    tree = ast.parse(source)
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "cmd_gui":
            target = node
    assert target is not None, "未找到 cmd_gui"

    handler_names = []
    for node in ast.walk(target):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                handler_names.extend(ast.dump(handler.type).split("'"))
    assert "ImportError" in handler_names, "cmd_gui 未捕获 ImportError"

    # try 体内必须同时含 import 与调用（不能只包 import 行）
    covered = set()
    for node in ast.walk(target):
        if isinstance(node, ast.Try):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    covered.add("import")
                if isinstance(child, ast.Call):
                    func = child.func
                    if isinstance(func, ast.Attribute) and func.attr in ("run", "build_app"):
                        covered.add("call")
    assert covered == {"import", "call"}, (
        "cmd_gui 的 try 未同时覆盖 import 与调用（实际覆盖: %s）" % covered)


def test_cmd_gui_returns_exit_3_when_dependency_missing(repo_root):
    """缺依赖回归：用 ``__import__`` 打桩让 PySide6 抛 ImportError。

    本机装了 gui extra 时也能复现——不必等 CI。
    """
    sys.path.insert(0, os.path.join(repo_root, "src"))
    import builtins

    import rcc.cli

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("PySide6"):
            raise ImportError("simulated missing PySide6")
        return real_import(name, *args, **kwargs)

    class _Args(object):
        pass

    builtins.__import__ = fake_import
    try:
        code = rcc.cli.cmd_gui(_Args())
    finally:
        builtins.__import__ = real_import
    assert code == 3, "缺 PySide6 时应返回退出码 3，实际 %s" % code
