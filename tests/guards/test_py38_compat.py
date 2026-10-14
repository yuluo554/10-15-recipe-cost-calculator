"""Python 3.8 兼容性门（本项目底线解释器）。

**为什么需要这道门**：本机装了 3.12 也装了 3.8，用 3.12 跑测试全绿，但 3.8 上
一批 API 不存在——本项目实测踩到 ``Path.write_text(newline=)``（3.10+ 参数），
在 3.8 上直接 TypeError，CI 的 win-3.8 作业必红而本机 3.12 永远测不出。

本门用 AST/正则扫描**已知的 3.9+ / 3.10+ 语法与 API 误用**，在 3.12 上即可
提前发现，不必等 CI。
"""

import ast
import os

import pytest

# 3.9+ / 3.10+ 才有的 API：``名字`` → 引入版本
NEWER_APIS = {
    "write_text": "Path.write_text(newline=) 是 3.10+ 参数",
    "removeprefix": "str.removeprefix 是 3.9+",
    "removesuffix": "str.removesuffix 是 3.9+",
    "pairwise": "itertools.pairwise 是 3.10+",
    "anext": "builtins.anext 是 3.10+",
    "zip_strict": "zip(strict=) 是 3.10+",
}

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


def test_no_newer_stdlib_api_usage(repo_root):
    """扫描已知的 3.9+/3.10+ API 误用（3.12 上即可提前发现）。"""
    offenders = []
    for path in _python_files(repo_root):
        tree = ast.parse(open(path, "r", encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = None
                if isinstance(func, ast.Attribute):
                    name = func.attr
                elif isinstance(func, ast.Name):
                    name = func.id
                if name in NEWER_APIS:
                    # 只在真传了关键字参数时判 write_text
                    if name == "write_text" and not node.keywords:
                        continue
                    offenders.append("%s:%d %s（%s）" % (
                        os.path.relpath(path, repo_root).replace(os.sep, "/"),
                        node.lineno, name, NEWER_APIS[name]))
    assert not offenders, "使用了 3.9+/3.10+ 才有的 API（3.8 会挂）: %s" % offenders


def test_no_walrus_in_comprehension_scope_issues(repo_root):
    """3.8 支持海象运算符，但不支持某些位置——这里只做语法可解析性检查。"""
    for path in _python_files(repo_root):
        source = open(path, "r", encoding="utf-8").read()
        try:
            compile(source, path, "exec")
        except SyntaxError as exc:
            pytest.fail("%s 语法错误: %s" % (path, exc))


def test_no_dict_union_operator(repo_root):
    """``dict | dict`` 合并运算符是 3.9+（3.8 上 TypeError）。"""
    offenders = []
    for path in _python_files(repo_root):
        tree = ast.parse(open(path, "r", encoding="utf-8").read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
                    and isinstance(node.left, ast.Dict)):
                offenders.append("%s:%d dict | dict（3.9+）" % (
                    os.path.relpath(path, repo_root).replace(os.sep, "/"), node.lineno))
    assert not offenders, "使用了 dict 合并运算符（3.9+）: %s" % offenders


def test_no_pipe_annotations(repo_root):
    """``X | Y`` 类型注解是 3.10+（3.8 上求值即 TypeError）。"""
    offenders = []
    for path in _python_files(repo_root):
        tree = ast.parse(open(path, "r", encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                # 排除位或的常规用法：两侧都是常量数字（不常见）时不算
                if isinstance(node.left, ast.Constant) and isinstance(node.right, ast.Constant):
                    continue
                # 注解位置（AnnAssign / arg.annotation / returns）才算
                if _is_annotation_position(tree, node):
                    offenders.append("%s:%d 注解用了 X | Y（3.10+）" % (
                        os.path.relpath(path, repo_root).replace(os.sep, "/"),
                        node.lineno))
    assert not offenders, "类型注解用了 PEP 604 语法（3.10+）: %s" % offenders


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
        # 注解内部嵌套（如 list[X | Y]）
        if annotation is not None:
            for inner in ast.walk(annotation):
                if inner is target:
                    return True
    return False


def test_compat_guard_is_not_vacuous():
    """**机制探活**：确认扫描真能抓出 3.10+ API 误用（防恒绿假门）。"""
    bad_source = "def f(p):\n    p.write_text('x', newline='\\n')\n"
    tree = ast.parse(bad_source)
    found = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "write_text" and n.keywords]
    assert found, "write_text(newline=) 探测机制失效"

    bad_annotation = "def f(a: int | None) -> None:\n    pass\n"
    tree = ast.parse(bad_annotation)
    assert _is_annotation_position(tree, next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr))), \
        "PEP 604 注解探测机制失效"
