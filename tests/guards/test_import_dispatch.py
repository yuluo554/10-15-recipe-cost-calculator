"""``check`` 与 ``run`` 共用同一分派点（plan/06 硬纪律）。

**为什么这是一道门**：两条通路各写一份判定逻辑时，两边会**各自演进**——修了 ``run``
忘了修 ``check``，于是"校验说没问题、跑起来报异常"。更坏的是这种漂移**不产生任何
报错**：两条通路的结论各自自洽，只有用户同时用两个命令时才会撞见矛盾。

判定"共用"不能靠读代码（`assert "parse_purchases" in source` 证明不了它被调用）。
本门的判据分三层：

1. **AST**：``pipeline`` 模块内**不得出现第二份列名映射**（中文列表名与内部字段名的
   映射只准存在于 ``csv_import.COLUMN_MAP``）；
2. **行为计数**：两条通路都必须**真的调用**同一个 ``csv_import.parse_purchases``
   （以计数探针观测，而非看源码里有没有这个词）；
3. **结论等同**：同一份输入，两条通路拿到的三态判定**逐条相同**。
"""

import ast
import os
import sys

import pytest

from rcc.engine import pipeline
from rcc.io import csv_import

# 列名白名单里的中文列名——它们只准出现在 csv_import 模块
COLUMN_NAMES = tuple(csv_import.COLUMN_MAP)


def _pipeline_tree(repo_root):
    path = os.path.join(repo_root, "src", "rcc", "engine", "pipeline.py")
    with open(path, "r", encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _string_literals(tree):
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


class _Args(object):
    """最小 args 替身（与 CLI 的 argparse.Namespace 同形）。"""

    def __init__(self, purchases, bom, **kw):
        self.purchases = purchases
        self.bom = bom
        self.params = kw.get("params")
        self.snapshots = kw.get("snapshots", [])
        self.with_alert = kw.get("with_alert", False)


@pytest.fixture
def anomaly_csv(tmp_path):
    path = tmp_path / "p.csv"
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("日期,品名,类别,数量,单位,单价,金额,备注\n"
                 "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00,x\n"
                 "2026-10-01,,蔬菜,10,斤,0.50,5.00,x\n"
                 "2026-10-01,土豆,蔬菜,abc,斤,1.50,0,x\n"
                 "2026-10-01,莲藕,蔬菜,4,斤,3.50,14.00,x,多余\n"
                 "2026-10-01,冬瓜,蔬菜,5,克拉,1.20,6.00,x\n")
    return str(path)


def test_pipeline_has_no_second_column_map(repo_root):
    """AST：列名映射只准存在于 ``csv_import``——第二份映射就是第二份口径。"""
    tree = _pipeline_tree(repo_root)
    literals = _string_literals(tree)
    offenders = [name for name in COLUMN_NAMES if name in literals]
    assert not offenders, (
        "pipeline 里出现列名字面量 %s——列名映射必须只有 csv_import.COLUMN_MAP 一份"
        % offenders)


def test_guard_detection_is_not_vacuous(tmp_path):
    """机制探活：把一份假源码交给同一判据，必须能抓出里面的列名映射。"""
    fake = ast.parse("MAP = {'品名': 'name', '数量': 'qty'}\n")
    literals = _string_literals(fake)
    assert any(name in literals for name in COLUMN_NAMES), \
        "列名判据失效：假源码里的列名没被抓到"


def test_both_paths_call_the_single_parser(repo_root, anomaly_csv, monkeypatch):
    """行为计数：两条通路都必须**真调用** ``csv_import.parse_purchases``。

    计数探针而非源码字符串匹配——后者证明不了函数被调用。
    """
    calls = []
    original = csv_import.parse_purchases

    def _counting(path, *args, **kwargs):
        calls.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(csv_import, "parse_purchases", _counting)

    bom = os.path.join(repo_root, "src", "rcc", "data", "samples", "bom-demo.json")

    pipeline.check_inputs(_Args(anomaly_csv, None))
    assert calls, "check 通路未调用 parse_purchases（另一份判定逻辑？）"

    calls[:] = []
    with pytest.raises(ValueError):
        # 全行异常 → run 通路必须因"无可用行"而报错（此处只要它先调用解析器）
        pipeline.compute_full(_Args(anomaly_csv, bom))
    assert calls, "run 通路未调用 parse_purchases（另一份判定逻辑？）"


def test_both_paths_agree_on_three_state_verdict(repo_root):
    """结论等同：同一份输入，两条通路的异常清单**逐条相同**。

    这是本门最硬的一条——即便有人另写一份"等价的"判定逻辑，只要它在任何一个
    边界上与正本不同（比如把表头级 unknown 也当成行级、或漏掉结构不可解析），
    这里就会红。

    用仓库样例作输入：它同时含 ok / invalid / unknown（表头级与行级）与重复品名，
    且覆盖 BOM 引用的全部食材，故两条通路都能跑完（不是"都在同一处报错"的假一致）。
    """
    purchases = os.path.join(repo_root, "src", "rcc", "data", "samples", "purchases-demo.csv")
    bom = os.path.join(repo_root, "src", "rcc", "data", "samples", "bom-demo.json")
    args = _Args(purchases, bom)

    check_report = pipeline.check_inputs(args)
    run_result = pipeline.compute_full(args)

    direct = csv_import.parse_purchases(purchases)
    # check 在零可用行时会补一条汇总条目；此输入有可用行，故应逐条等同
    assert check_report["issues"] == direct["issues"], (
        "check 的异常清单与解析器正本不一致——出现了第二份判定逻辑")
    assert run_result["warnings"] == direct["issues"], (
        "run 的异常清单与解析器正本不一致——出现了第二份判定逻辑")


def test_both_paths_agree_on_anomaly_only_input(repo_root, anomaly_csv):
    """异常行占多数的输入上，两条通路同样要一致（不是只在样例上凑巧相同）。"""
    args = _Args(anomaly_csv, None)
    check_report = pipeline.check_inputs(args)
    direct = csv_import.parse_purchases(anomaly_csv)
    assert check_report["issues"] == direct["issues"]


def test_check_surfaces_zero_usable_rows_instead_of_blaming_bom(repo_root, tmp_path):
    """零可用行时，``check`` 必须**指向进货单**，不得报"BOM 引用了不存在的食材"。

    错误指向错误的对象比沉默更坏：用户会照着提示去改 BOM，而真因在进货单。
    """
    path = tmp_path / "allbad.csv"
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("日期,品名,类别,数量,单位,单价,金额\n"
                 "2026-10-01,,蔬菜,10,斤,0.50,5.00\n"
                 "2026-10-01,土豆,蔬菜,abc,斤,1.50,0\n")

    args = _Args(str(path), os.path.join(repo_root, "src", "rcc", "data", "samples", "bom-demo.json"))
    report = pipeline.check_inputs(args)

    reasons = " ".join(issue["reason"] for issue in report["issues"])
    assert "无任何可用行" in reasons, "零可用行未被明确指出"
    assert "不存在的食材" not in reasons, "把进货单的问题误报成了 BOM 的问题"
    assert "未核对" in report["summary"], "应显式声明 BOM 交叉核对被跳过，而非默默不做"
    codes = [issue["code"] for issue in report["issues"]]
    assert csv_import.ISSUE_NO_USABLE_ROWS in codes, \
        "文件级结论应有独立异常代码（不得借用行级代码 required_empty）"
    file_level = [issue for issue in report["issues"] if issue["line"] == 0]
    assert [issue["code"] for issue in file_level] == [csv_import.ISSUE_NO_USABLE_ROWS], \
        "文件级条目（line=0）必须是独立代码——借行级代码会让下游去定位一个不存在的行"


def test_run_zero_usable_rows_names_the_purchases_file(repo_root, tmp_path):
    """``run`` 零可用行 → exit 2 语义，且报错指向进货单而非 BOM。"""
    path = tmp_path / "allbad.csv"
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("日期,品名,类别,数量,单位,单价,金额\n"
                 "2026-10-01,,蔬菜,10,斤,0.50,5.00\n")

    args = _Args(str(path), os.path.join(repo_root, "src", "rcc", "data", "samples", "bom-demo.json"))
    with pytest.raises(ValueError) as excinfo:
        pipeline.compute_full(args)
    message = str(excinfo.value)
    assert "无任何可用行" in message
    assert "不存在的食材" not in message


def test_duplicate_names_are_surfaced_by_both_paths(repo_root, tmp_path):
    """重复品名的取舍口径（取最后一条）必须在两条通路上都可见。"""
    purchases = tmp_path / "dup.csv"
    with open(str(purchases), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("日期,品名,类别,数量,单位,单价,金额\n"
                 "2026-10-01,土豆,蔬菜,10,斤,1.00,10.00\n"
                 "2026-10-05,土豆,蔬菜,10,斤,2.00,20.00\n")

    bom = tmp_path / "bom.json"
    with open(str(bom), "w", encoding="utf-8", newline="\n") as fh:
        fh.write('{"dishes": [{"name": "测试菜", "items": '
                 '[{"food": "土豆", "qty": "1"}]}]}')

    args = _Args(str(purchases), str(bom))
    check_report = pipeline.check_inputs(args)
    assert "重复品名" in check_report["summary"]

    result = pipeline.compute_full(args)
    assert result["duplicate_food_names"] == ["土豆"]
    # 取最后一条 = 2.00，故成本卡用的是后到价
    assert str(result["cards"][0]["lines"][0]["purchase_unit_price"]) == "2.00"
