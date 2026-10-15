"""核算引擎（M3）的边界与失败路径测试。

对应 plan/04 §三 的三类必测失败路径：

- **公式边界**：``target_margin = 1.0`` 拒绝（**非除零**）、``old_price = 0`` 拒绝、
  ``yield_rate`` 越界 → **该行 invalid 并入清单**（不静默取 0/1，不中断整批）；
- **BOM 形态失败**：缺 ``dishes`` 数组 / 空数组 / 菜品缺 ``name`` / 引用不存在的
  食材 —— 四条各有断言；
- **门控**：``input_required`` 放行门控但运行时必索（缺失 exit 2，不静默取默认值）。

**退出码语义**（plan/04 §二）：行级问题 → exit 1（降级完成）；形态/输入不可用 → exit 2。
"""

import json
import os
from decimal import Decimal

import pytest

from rcc.engine import pipeline
from rcc.model import SourceMissing
from rcc.rules import formulas, params as params_mod

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLE_PURCHASES = os.path.join(REPO_ROOT, "data", "samples", "purchases-demo.csv")
SAMPLE_BOM = os.path.join(REPO_ROOT, "data", "samples", "bom-demo.json")


class _Args(object):
    """最小 args 替身（与 CLI 的 argparse.Namespace 同形）。"""

    def __init__(self, purchases=SAMPLE_PURCHASES, bom=SAMPLE_BOM, params=None,
                 snapshots=None, with_alert=False):
        self.purchases = purchases
        self.bom = bom
        self.params = params
        self.snapshots = snapshots or []
        self.with_alert = with_alert


def _params_with(tmp_path, mutate, name="params.json"):
    """复制随包参数包并施加一处改动，落盘为临时参数包。"""
    with open(os.path.join(REPO_ROOT, "data", "rules", "params.json"),
              "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    mutate(payload)
    path = tmp_path / name
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return str(path)


def _write_bom(tmp_path, payload, name="bom.json"):
    path = tmp_path / name
    text = payload if isinstance(payload, str) else json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return str(path)


# --------------------------------------------------------------- 公式边界

class TestFormulaBoundaries:
    def test_target_margin_one_is_rejected_not_div_by_zero(self):
        """``target_margin = 1.0`` → 拒绝（**非除零**）：等 1 时售价无解。"""
        with pytest.raises(formulas.FormulaError, match="小于 1"):
            formulas.suggested_price(Decimal("10"), Decimal("1"))

    def test_target_margin_above_one_is_rejected(self):
        with pytest.raises(formulas.FormulaError):
            formulas.suggested_price(Decimal("10"), Decimal("1.5"))

    def test_old_price_zero_is_rejected_not_div_by_zero(self):
        """``old_price = 0`` → 拒绝（**非除零**，是缺对比基准）。"""
        with pytest.raises(formulas.FormulaError, match="大于 0"):
            formulas.change_rate(Decimal("0"), Decimal("5"))

    def test_yield_rate_out_of_range_rejects_that_row(self):
        """``yield_rate`` 越界 ∉ (0,1] → 拒绝（该行判 invalid，**不静默取 0/1**）。"""
        with pytest.raises(formulas.FormulaError):
            formulas.net_unit_price(Decimal("8"), Decimal("0"))
        with pytest.raises(formulas.FormulaError):
            formulas.net_unit_price(Decimal("8"), Decimal("1.2"))


# ------------------------------------------------------- yield_rate 越界处置

class TestYieldRateOutOfRange:
    """**"缺条目"与"值越界"是两回事**（plan/02 §一，M3 登记）：

    前者是"没给"（缺输入 → exit 2），后者是"给了但不对"（该行 invalid → exit 1）。
    """

    def test_out_of_range_rate_is_a_line_issue_not_a_run_abort(self, tmp_path):
        """值越界 → 该行（该菜）判 invalid 并列入清单，**整批不中断**。

        仓库样例有 5 道菜，其中「醋溜白菜」用大白菜。把大白菜的净料率改越界后：
        其余 4 道菜必须照常算出（不中断整批），「醋溜白菜」被排除且原因可见。
        """
        path = _params_with(tmp_path, lambda p: p["yield_rates"]["大白菜"].update(
            {"value": "1.5"}))
        result = pipeline.compute_full(_Args(params=path))

        dishes = [card["dish"] for card in result["cards"]]
        assert "醋溜白菜" not in dishes, "净料率越界的那道菜必须被排除"
        assert len(result["cards"]) == 4, "其余菜品必须照常算出（不中断整批）"

        codes = [w.get("code") for w in result["warnings"]]
        assert pipeline.ISSUE_YIELD_OUT_OF_RANGE in codes, "越界未列入异常清单"
        issue = [w for w in result["warnings"]
                 if w.get("code") == pipeline.ISSUE_YIELD_OUT_OF_RANGE][0]
        assert "醋溜白菜" in issue["where"] and "大白菜" in issue["where"], \
            "行级 issue 必须能定位到菜品与食材"

    def test_out_of_range_rate_does_not_take_zero_or_one(self, tmp_path):
        """**不静默取 0/1**：越界的净料率不得被当成 0 或 1 继续算。"""
        path = _params_with(tmp_path, lambda p: p["yield_rates"]["大白菜"].update(
            {"value": "2"}))
        result = pipeline.compute_full(_Args(params=path))
        assert all(card["dish"] != "醋溜白菜" for card in result["cards"]), \
            "越界值被静默当成了 0 或 1（不该出数）"

    def test_all_dishes_out_of_range_is_input_unusable(self, tmp_path):
        """**全部**菜品都被排除 → 成本卡为空 → 输入不可用（不产出"0 道菜"空结果）。"""
        path = _params_with(
            tmp_path,
            lambda p: [p["yield_rates"][k].update({"value": "1.5"})
                       for k in p["yield_rates"]])
        with pytest.raises(ValueError, match="成本卡为空"):
            pipeline.compute_full(_Args(params=path))

    def test_missing_rate_entry_is_asked_at_runtime_not_defaulted(self, tmp_path):
        """**缺条目**（本不由参数包承载）→ 运行时索取，缺失 exit 2，不静默取默认值。"""
        bom = _write_bom(tmp_path, {"dishes": [
            {"name": "测试菜", "items": [{"food": "未知食材X", "qty": "1"}]}]})
        purchases = tmp_path / "p.csv"
        with open(str(purchases), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("日期,品名,类别,数量,单位,单价,金额\n"
                     "2026-10-01,未知食材X,其他,10,斤,3.00,30.00\n")
        with pytest.raises(params_mod.ParamsInputRequired):
            pipeline.compute_full(_Args(purchases=str(purchases), bom=bom))

    def test_non_numeric_qty_is_a_line_issue(self, tmp_path):
        """用量非数值 → 该行 invalid 并入清单（不是整单崩）。"""
        bom = _write_bom(tmp_path, {"dishes": [
            {"name": "测试菜", "items": [{"food": "大白菜", "qty": "abc"}]}]})
        purchases = tmp_path / "p.csv"
        with open(str(purchases), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("日期,品名,类别,数量,单位,单价,金额\n"
                     "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n")
        with pytest.raises(ValueError, match="成本卡为空"):
            pipeline.compute_full(_Args(purchases=str(purchases), bom=bom))

    def test_negative_qty_is_a_line_issue(self, tmp_path):
        bom = _write_bom(tmp_path, {"dishes": [
            {"name": "测试菜", "items": [{"food": "大白菜", "qty": "-1"}]}]})
        purchases = tmp_path / "p.csv"
        with open(str(purchases), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("日期,品名,类别,数量,单位,单价,金额\n"
                     "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n")
        with pytest.raises(ValueError, match="成本卡为空"):
            pipeline.compute_full(_Args(purchases=str(purchases), bom=bom))


# ----------------------------------------------------------- BOM 形态失败

class TestBomShapeFailures:
    """BOM 形态问题 → 抛错（CLI → exit 2）。四条各有断言。"""

    def test_missing_dishes_array(self, tmp_path):
        bom = _write_bom(tmp_path, "{}")
        with pytest.raises(ValueError, match="缺少 dishes"):
            pipeline.compute_full(_Args(bom=bom))

    def test_empty_dishes_array(self, tmp_path):
        bom = _write_bom(tmp_path, {"dishes": []})
        with pytest.raises(ValueError, match="缺少 dishes 数组或为空"):
            pipeline.compute_full(_Args(bom=bom))

    def test_dish_without_name(self, tmp_path):
        bom = _write_bom(tmp_path, {"dishes": [
            {"items": [{"food": "大白菜", "qty": "1"}]}]})
        with pytest.raises(ValueError, match="缺少 name"):
            pipeline.compute_full(_Args(bom=bom))

    def test_item_referencing_unknown_food(self, tmp_path):
        bom = _write_bom(tmp_path, {"dishes": [
            {"name": "测试菜", "items": [{"food": "不存在的食材", "qty": "1"}]}]})
        with pytest.raises(ValueError, match="不存在的食材"):
            pipeline.compute_full(_Args(bom=bom))

    def test_non_object_bom_is_shape_failure(self, tmp_path):
        """BOM 根节点不是对象（如裸数组）→ 形态失败。"""
        bom = _write_bom(tmp_path, "[]")
        with pytest.raises(ValueError):
            pipeline.compute_full(_Args(bom=bom))


# ------------------------------------------------------------- source 门控

class TestQuantizationExceptionIsLocked:
    """F3 是**唯一"量化作用于中间量"的例外**（plan/02 §一 注记 3）。

    口径：建议售价是**对外挂牌价**，必须先 quantize，再据此算 F4 实际毛利率
    （真实挂牌价是分位值）。若实现改成"先算 F4 再量化"或"用未量化的价算 F4"，
    实际毛利率会与挂牌价不自洽——**这条必须锁进测试，否则下一个人会"优化"掉它**。
    """

    def test_f3_result_is_quantized_to_money_exp(self):
        from rcc.model import MONEY_EXP

        price = formulas.suggested_price(Decimal("12.34"), Decimal("0.6"))
        assert price == price.quantize(MONEY_EXP), "F3 建议售价未先量化"

    def test_f4_consumes_the_quantized_price_not_the_raw_one(self):
        """F4 的入参必须是 F3 **量化后**的价——这是量化作用于中间量的唯一例外。

        注意口径的边界：**只有价（F3 输出）是量化例外**；``dish_cost`` 按 plan/02
        §一 注记 3 仍是全精度（量化只作用于对外呈现）。所以断言的是"F4 用挂牌价
        而非原始比值价"，不是"F4 用量化后的成本"。
        """
        cost = Decimal("10")
        target = Decimal("0.3")
        price = formulas.suggested_price(cost, target)
        margin = formulas.actual_margin(price, cost)

        raw_price = cost / (Decimal(1) - target)
        raw_margin = (raw_price - cost) / raw_price
        assert raw_price != price, "探活前提失效：该用例的原始价与挂牌价相等"
        assert margin != raw_margin, "F4 用的是未量化的价（量化例外被破坏）"

    def test_cost_stays_full_precision_while_price_is_quantized(self):
        """对照口径：成本保持全精度、价被量化——两者不得混为一谈。"""
        from rcc.model import MONEY_EXP

        cost = Decimal("10")
        target = Decimal("0.3")
        price = formulas.suggested_price(cost, target)
        # 价是分位值
        assert price == price.quantize(MONEY_EXP)
        # 成本未被量化（此处传入即原值，函数不改写入参）
        assert cost == Decimal("10")

    def test_engine_pricing_path_uses_full_precision_cost(self):
        """端到端：实际毛利率由**挂牌价 + 全精度成本**反算（不是显示用的量化成本）。

        显示用的 ``cost`` 是分位值；若 F4 拿它当输入，会引入"展示误差进入计算"
        的隐性漂移——这条断言把这个边界钉住。
        """
        result = pipeline.compute_full(_Args())
        exact_by_dish = {card["dish"]: card["cost_exact"]
                         for card in result["cards"]}
        from rcc.model import quantize_rate

        for row in result["pricing"]:
            expected = quantize_rate(formulas.actual_margin(
                row["suggested_price"], exact_by_dish[row["dish"]]))
            assert row["actual_margin"] == expected, (
                "实际毛利率不是由「挂牌价 + 全精度成本」反算的（口径漂移）")


class TestB5RoundtripIsExercised:
    """B5 双向对账的 F3→F4 往返断言必须真被基准跑到（plan/03 §五）。"""

    def test_reconcile_suite_has_roundtrip_check(self):
        from rcc.rules.params import load_params

        from benchmark import runner

        result = runner.suite_reconcile(load_params())
        assert result["ok"], result.get("failures")
        assert result["total"] >= 1

    def test_reconcile_catches_broken_f4(self, monkeypatch):
        """探活：破坏 F4 → B5 必须报未达标（否则是假门）。"""
        from rcc.rules.params import load_params

        from benchmark import runner

        original = formulas.actual_margin
        monkeypatch.setattr(formulas, "actual_margin",
                            lambda price, cost: original(price, cost) / 2)
        result = runner.suite_reconcile(load_params())
        assert not result["ok"], "F4 被破坏后 B5 仍报达标（假门）"


class TestSourceGateOnEnginePaths:
    def test_missing_yield_rate_source_blocks_run(self, tmp_path):
        path = _params_with(tmp_path, lambda p: p["yield_rates"]["大白菜"].pop("source"))
        with pytest.raises(SourceMissing):
            pipeline.compute_full(_Args(params=path))

    def test_missing_margin_source_blocks_run(self, tmp_path):
        path = _params_with(tmp_path, lambda p: p["pricing"]["target_margin"].pop("source"))
        with pytest.raises(SourceMissing):
            pipeline.compute_full(_Args(params=path))

    def test_qty_source_is_attached_and_validated(self):
        """用量（``qty``）必须挂来源，且在消费点被校验（plan/02 §二 早已列入）。"""
        dishes, source = pipeline._load_bom(SAMPLE_BOM)
        assert dishes
        assert source["kind"] == "user"
        # 消费点校验：伪造缺来源的 qty_source → 拒绝
        with pytest.raises(SourceMissing):
            pipeline.compute_costcard(dishes, {}, {}, None)

    def test_every_card_line_carries_all_three_sources(self):
        """每行留痕都必须挂三类来源（进货单价 / 净料率 / 用量）——缺一类即不可追溯。"""
        result = pipeline.compute_full(_Args())
        for card in result["cards"]:
            for line in card["lines"]:
                for key in ("price_source", "yield_source", "qty_source"):
                    assert line.get(key), "%s·%s 缺 %s" % (card["dish"], line["food"], key)
