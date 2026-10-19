"""标准库 API 版本兼容门（**口径变更：M7 起 floor 为 3.12**）。

**这道门的来历**：M0 时本项目的底线解释器是 3.8，实测踩到
``Path.write_text(newline=)``（3.10+ 参数）——3.12 上全绿、3.8 上直接 TypeError，
CI 的 win-3.8 作业必红而本机 3.12 永远测不出。当时建了 ``test_py38_compat.py``
用 AST 扫描已知的 3.9+/3.10+ API 误用，在 3.12 上即可提前发现。

**M7 的口径调整（DEC4）**：3.8 于 2024-10 EOL、3.9 于 2025-10、3.10 于 2026-10 EOL，
``requires-python`` 抬到 ``>=3.12``、CI 矩阵收缩为 ``{windows, ubuntu}×3.12``。
于是"3.8 兼容"不再是契约——但**这道扫描门本身仍然有价值**：它守的是
"用了比 floor 更新的 API"。故保留机制、换掉基准版本：

- 扫描面与判据形态不变（AST 查已知的版本化 API / 语法）；
- ``NEWER_APIS`` 表按 floor=3.12 重述：**高于 3.12 的** API 才是越界；
- 新增两条**同源断言**：`requires-python` 必须 >= floor，CI 矩阵不得出现
  低于 floor 的通道——"声明 floor"与"实际守 floor"不能各写一份。

**机制探活保留**（`test_compat_guard_is_not_vacuous`）：没有阳性/阴性对照的
扫描门可能一直是空扫。
"""

import ast
import os
import re

import pytest

FLOOR = (3, 12)

# 高于 floor 才引入的 API：``名字`` → 引入版本说明。
# floor 时代（3.12）已有的东西不在此列；这里只列**3.13+** 的。
NEWER_APIS = {
    # 3.13+
    "deprecated": "warnings.deprecated 装饰器是 3.13+",
}

# 历史判据留档：``write_text``/``write_bytes`` 的 ``newline=`` 参数是 3.10+。
# floor 已抬到 3.12，它现在是**合法**用法，故不再参与越界判定——
# 保留常量是为了让"当年为什么写这道门"在代码里可查（口径变更须留痕）。
NEWLINE_KWARG_APIS = {"write_text", "write_bytes"}

SCAN_DIRS = ("src", "tools", "benchmark", "tests")


def _python_files(repo_root):
    for rel_dir in SCAN_DIRS:
        target = os.path.join(repo_root, rel_dir)
        if not os.path.isdir(target):
            continue
        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
            for filename in sorted(filenames):
                if filename.endswith(".py"):
                    yield os.path.join(dirpath, filename)


def _api_hits(tree):
    """AST 里命中的 ``NEWER_APIS`` 调用节点。"""
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in NEWER_APIS:
            hits.append((func.attr, node.lineno))
        elif isinstance(func, ast.Name) and func.id in NEWER_APIS:
            hits.append((func.id, node.lineno))
    return hits


def test_no_api_newer_than_floor(repo_root):
    """扫描**高于 floor** 的已知 API（floor=3.12 时即 3.13+ 的东西）。"""
    offenders = []
    for path in _python_files(repo_root):
        tree = ast.parse(open(path, "r", encoding="utf-8").read())
        for name, lineno in _api_hits(tree):
            offenders.append("%s:%d %s（%s）" % (
                os.path.relpath(path, repo_root).replace(os.sep, "/"),
                lineno, name, NEWER_APIS[name]))
    assert not offenders, "使用了高于 floor（%d.%d）的 API: %s" % (
        FLOOR[0], FLOOR[1], offenders)


def test_every_scanned_file_compiles(repo_root):
    """语法可解析性（一个语法错误会让该文件的所有门静默失效）。"""
    for path in _python_files(repo_root):
        source = open(path, "r", encoding="utf-8").read()
        try:
            compile(source, path, "exec")
        except SyntaxError as exc:
            pytest.fail("%s 语法错误: %s" % (path, exc))


def test_dict_union_and_pipe_annotation_scanners_still_work(repo_root):
    """``dict | dict``（3.9+）与 PEP 604 注解（3.10+）的扫描器**仍然能跑**。

    floor=3.12 下这两种写法都合法，故**不再断言命中数为 0**——但扫描器本身
    必须还能正确识别它们（下面用合成源码做阳性对照）。留着的原因是它们同时
    兜住"把位或误判成注解"这类混淆，且历史变异验证就是靠它们做的。
    """
    for path in _python_files(repo_root):
        tree = ast.parse(open(path, "r", encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                # 只要求"能走完 AST 不炸"；命中与否在此不作判定
                _is_annotation_position(tree, node)

    probe = "def f(a: int | None) -> None:\n    pass\n"
    tree = ast.parse(probe)
    target = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr))
    assert _is_annotation_position(tree, target), "PEP 604 注解判定失效"

    dict_probe = "d = {'a': 1} | {'b': 2}\n"
    tree = ast.parse(dict_probe)
    assert any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr)
               and isinstance(n.left, ast.Dict) for n in ast.walk(tree)), \
        "dict | dict 探测失效"


def _is_annotation_position(tree, target):
    """判定该 BinOp 是否位于注解位置。"""
    for node in ast.walk(tree):
        annotation = None
        if isinstance(node, ast.AnnAssign):
            annotation = node.annotation
        elif isinstance(node, ast.arg):
            annotation = node.annotation
        elif isinstance(node, ast.FunctionDef):
            annotation = node.returns
        if annotation is target:
            return True
        if annotation is not None:
            for inner in ast.walk(annotation):
                if inner is target:
                    return True
    return False


# ------------------------------------- floor 声明与守门必须同源（M7 新增两条）

def test_requires_python_matches_floor(repo_root):
    """`requires-python` 必须 >= floor——**声明与守门同源**。

    失效形态有两种，都真实发生过：floor 抬了但 `requires-python` 没抬（pip 会往
    已 EOL 的解释器上装，装完按新语法崩）；或反之（门守着新版本，声明还是旧的）。
    两者都是"同一个事实在两处各写一份"。
    """
    text = open(os.path.join(repo_root, "pyproject.toml"), "r", encoding="utf-8").read()
    match = re.search(r'^requires-python\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml 未声明 requires-python"
    spec = match.group(1)
    assert ">=" in spec, "requires-python 未用 >= 形式（实际: %r）" % spec
    parts = spec.split(">=")[1].strip().split(".")
    declared = (int(parts[0]), int(parts[1]))
    assert declared >= FLOOR, (
        "requires-python=%r 低于本门守的 floor %d.%d" % (spec, FLOOR[0], FLOOR[1]))


def test_ci_matrix_has_no_channel_below_floor(repo_root):
    """CI 矩阵不得出现低于 floor 的解释器通道（否则在已 EOL 的版本上白跑）。"""
    import yaml

    path = os.path.join(repo_root, ".github", "workflows", "ci.yml")
    with open(path, "r", encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    channels = set()
    for job in (doc.get("jobs") or {}).values():
        matrix = ((job.get("strategy") or {}).get("matrix") or {})
        for entry in matrix.get("include") or []:
            if "python" in entry:
                channels.add(str(entry["python"]))
        for value in matrix.get("python") or []:
            channels.add(str(value))
    assert channels, "CI 矩阵里没有任何 python 通道（门形同虚设）"
    below = sorted(ch for ch in channels
                   if tuple(int(p) for p in ch.split(".")[:2]) < FLOOR)
    assert not below, "CI 矩阵含低于 floor 的通道: %s（floor=%d.%d）" % (
        below, FLOOR[0], FLOOR[1])


def test_compat_guard_is_not_vacuous():
    """**机制探活**：确认扫描真能抓出越界 API（防恒绿假门）。"""
    probe = next(iter(NEWER_APIS))
    bad_source = "def f():\n    return %s(None)\n" % probe
    assert _api_hits(ast.parse(bad_source)), "越界 API 探测机制失效（%r 未被识别）" % probe

    # 阴性：普通调用不得被判为越界
    ok_source = "def f():\n    return len([])\n"
    assert not _api_hits(ast.parse(ok_source)), "普通调用被误判为越界（阴性对照失败）"

    # 属性形态也要能抓（`warnings.deprecated(...)`）
    attr_source = "import warnings\ndef f():\n    return warnings.%s(None)\n" % probe
    assert _api_hits(ast.parse(attr_source)), "属性形态的越界 API 未被识别"


def test_known_api_table_is_documented():
    """已知 API 表必须非空且带版本说明——空表等于门关了。"""
    assert NEWER_APIS, "NEWER_APIS 为空（扫描门变成空扫）"
    for name, note in NEWER_APIS.items():
        assert re.search(r"\d+\.\d+", note), "%r 的说明未写版本号: %r" % (name, note)
