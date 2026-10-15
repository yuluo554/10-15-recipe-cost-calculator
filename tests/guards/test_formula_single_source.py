"""口径单一定义点守门（plan/02 §一：公式与注记同源一致）。

**为什么这是一道门**：plan/02 声明自己是"全部数值口径的唯一定义点"，且禁止任何
地方手写第二份口径（含 docstring 与注释里的示例数值）。但"同源一致"若只靠人工
比对，它会随实现漂移而无人察觉——**文档说一套、代码做一套，两边各自自洽**。

本门把"同源"落成两条可证伪的断言：

1. **公式原文一致**：plan/02 §一 表格里的每条公式，必须逐字出现在
   `formulas.py` 对应函数的 docstring 里。公式只准有一份写法；
2. **前提校验语句也一致**：表格"前提校验"列的关键条件（如 `yield_rate ∈ (0, 1]`）
   必须与实现里的 `_require` 谓词方向一致——**校验方向反了是 F1 最易犯的缺陷**
   （净料单价 < 毛料单价）。

**探活前提**：本门若写成"docstring 里出现了某关键词"，它会在改词后仍绿。故断言
的是**plan/02 里的原文被代码复述**，改动任一侧都会红。
"""

import ast
import os
import re

import pytest


def _formulas_source(repo_root):
    path = os.path.join(repo_root, "src", "rcc", "rules", "formulas.py")
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _plan_source(repo_root):
    path = os.path.join(repo_root, "plan", "02-算法与口径说明.md")
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _docstrings(source):
    """``{函数名: docstring}``。"""
    tree = ast.parse(source)
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and ast.get_docstring(node):
            out[node.name] = ast.get_docstring(node)
    return out


# plan/02 §一 表格里的公式原文 → formulas.py 里对应的函数名
FORMULA_ANCHORS = {
    "net_unit_price": "net_unit_price = purchase_unit_price / yield_rate",
    "dish_cost": "dish_cost = Σ_i (net_unit_price_i × qty_i)",
    "suggested_price": "suggested_price = dish_cost / (1 - target_margin)",
    "actual_margin": "actual_margin = (price - dish_cost) / price",
    "change_rate": "change_rate = (new_price - old_price) / old_price",
}


class TestFormulaTextIsSingleSource:
    def test_plan_contains_each_formula_string(self, repo_root):
        """前置：plan/02 必须真的含这些公式原文（否则本门形同虚设）。"""
        plan = _plan_source(repo_root)
        missing = [text for text in FORMULA_ANCHORS.values() if text not in plan]
        assert not missing, "plan/02 §一 缺少公式原文: %s" % missing

    def test_each_formula_docstring_repeats_the_plan_string(self, repo_root):
        """**同源一致**：每条公式的原文必须逐字出现在对应函数的 docstring 里。

        改 plan/02 的公式或改代码 docstring 任一侧 → 本门必红。
        """
        docstrings = _docstrings(_formulas_source(repo_root))
        offenders = []
        for func_name, formula in FORMULA_ANCHORS.items():
            doc = docstrings.get(func_name)
            if doc is None:
                offenders.append("%s: 无 docstring" % func_name)
                continue
            if formula not in doc:
                offenders.append("%s: docstring 未复述公式 %r" % (func_name, formula))
        assert not offenders, (
            "公式与注记不同源（plan/02 是唯一定义点）:\n  " + "\n  ".join(offenders))

    def test_guard_is_not_vacuous(self):
        """机制探活：伪造一份 docstring 缺公式的源码 → 判据必须报红。"""
        fake = 'def net_unit_price(a, b):\n    """F1 净料单价。"""\n    return a / b\n'
        docstrings = _docstrings(fake)
        formula = FORMULA_ANCHORS["net_unit_price"]
        assert formula not in docstrings["net_unit_price"], "探活失效：判据抓不出缺公式的 docstring"


class TestPremiseDirectionIsSingleSource:
    """前提校验方向必须与 plan/02 的注记一致（F1 方向反了是最易犯的实现缺陷）。"""

    def test_f1_direction_note_exists_in_both(self, repo_root):
        """plan/02 与代码都须写明"净料单价必然 ≥ 毛料单价"这条方向纪律。"""
        plan = _plan_source(repo_root)
        assert "净料单价**必然 ≥ 毛料单价**" in plan, "plan/02 缺 F1 方向注记"
        doc = _docstrings(_formulas_source(repo_root))["net_unit_price"]
        assert "必然 ≥ 毛料单价" in doc, "formulas.net_unit_price 的 docstring 缺方向注记"

    def test_f1_rate_domain_matches_plan(self, repo_root):
        """取值域 ``(0, 1]`` 必须在两侧都写出来，且实现真按它校验。"""
        plan = _plan_source(repo_root)
        assert "(0, 1]" in plan, "plan/02 缺 F1 取值域"
        doc = _docstrings(_formulas_source(repo_root))["net_unit_price"]
        assert "(0, 1]" in doc, "formulas.net_unit_price 的 docstring 缺取值域"

        from decimal import Decimal

        from rcc.rules import formulas

        # 实现必须真按 (0, 1] 校验：0 与 >1 都拒绝
        with pytest.raises(formulas.FormulaError):
            formulas.net_unit_price(Decimal(1), Decimal(0))
        with pytest.raises(formulas.FormulaError):
            formulas.net_unit_price(Decimal(1), Decimal("1.0001"))

    def test_no_second_formula_expression_in_scan_face(self, repo_root):
        """扫描面内**不得出现第二份公式表达式**（同一算式只准有一处）。

        判据：扫描面内的除法 BinOp 只能出现在 `formulas.py` 与
        `benchmark/runner.py`（后者是规则驱动基准，按设计独立重算同一公式——
        这正是"两条独立实现路径互验"的 B5 对账所要的）。其余位置出现除法即红。
        """
        allowed = {
            os.path.join("src", "rcc", "rules", "formulas.py"),
            os.path.join("benchmark", "runner.py"),
        }
        offenders = []
        for rel in _scan_face_files(repo_root):
            if rel.replace(os.sep, "/") in {a.replace(os.sep, "/") for a in allowed}:
                continue
            source = open(os.path.join(repo_root, rel), "r", encoding="utf-8").read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv)):
                    offenders.append("%s:%d" % (rel.replace(os.sep, "/"), node.lineno))
        assert not offenders, (
            "扫描面内出现第二份公式表达式（除法）——口径必须只有一份:\n  "
            + "\n  ".join(offenders))


def _scan_face_files(repo_root):
    """与 `tools/check_literals.py` 的扫描面同源（整包 + benchmark）。"""
    import sys

    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import check_literals

    for rel, path in check_literals._iter_files():
        yield rel
