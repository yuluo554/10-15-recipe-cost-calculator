"""换算公式 F1–F6 的单元测试。

边界与方向断言——F1 方向反了（净料单价 < 毛料单价）是最容易犯的实现缺陷。
"""

from decimal import Decimal

import pytest

from rcc.model import quantize_money, quantize_rate, to_decimal
from rcc.rules import formulas


class TestF1NetUnitPrice:
    def test_rate_one_equals_purchase_price(self):
        assert formulas.net_unit_price(Decimal("8"), Decimal("1")) == Decimal("8")

    def test_net_price_never_below_purchase_price(self):
        """方向纪律：净料率 <= 1 ⇒ 净料单价必然 >= 毛料单价。"""
        for rate in ("0.1", "0.5", "0.85", "1"):
            net = formulas.net_unit_price(Decimal("10"), Decimal(rate))
            assert net >= Decimal("10"), "净料率 %s 时净料单价低于毛料单价（方向反了）" % rate

    def test_rate_halved_doubles_price(self):
        assert formulas.net_unit_price(Decimal("8"), Decimal("0.5")) == Decimal("16")

    def test_zero_rate_rejected(self):
        with pytest.raises(formulas.FormulaError):
            formulas.net_unit_price(Decimal("8"), Decimal("0"))

    def test_rate_above_one_rejected(self):
        with pytest.raises(formulas.FormulaError):
            formulas.net_unit_price(Decimal("8"), Decimal("1.5"))

    def test_negative_price_rejected(self):
        with pytest.raises(formulas.FormulaError):
            formulas.net_unit_price(Decimal("-1"), Decimal("0.8"))

    def test_loss_rate_is_complement(self):
        """损耗率是净料率的换算面，不是第二个独立参数。"""
        assert formulas.loss_rate(Decimal("0.8")) == Decimal("0.2")


class TestF2DishCost:
    def test_additive(self):
        one = formulas.dish_cost([(Decimal("5"), Decimal("4"))])
        two = formulas.dish_cost([(Decimal("5"), Decimal("2")), (Decimal("5"), Decimal("2"))])
        assert one == two

    def test_zero_qty_contributes_nothing(self):
        total = formulas.dish_cost([(Decimal("5"), Decimal("0")), (Decimal("3"), Decimal("2"))])
        assert total == Decimal("6")

    def test_empty_bom_rejected(self):
        """空 BOM 是数据缺陷，不是"成本为 0"。"""
        with pytest.raises(formulas.FormulaError):
            formulas.dish_cost([])

    def test_negative_qty_rejected(self):
        with pytest.raises(formulas.FormulaError):
            formulas.dish_cost([(Decimal("5"), Decimal("-1"))])


class TestF3SuggestedPrice:
    def test_zero_margin_price_equals_cost(self):
        assert formulas.suggested_price(Decimal("10"), Decimal("0")) == Decimal("10")

    def test_margin_one_rejected(self):
        with pytest.raises(formulas.FormulaError):
            formulas.suggested_price(Decimal("10"), Decimal("1"))

    def test_monotone_in_margin(self):
        low = formulas.suggested_price(Decimal("10"), Decimal("0.3"))
        high = formulas.suggested_price(Decimal("10"), Decimal("0.7"))
        assert high > low

    def test_result_is_quantized(self):
        """建议售价先量化（真实挂牌价是分位值）——这是量化作用于中间量的唯一例外。"""
        price = formulas.suggested_price(Decimal("10"), Decimal("0.6"))
        assert price == price.quantize(Decimal("0.01"))


class TestF4ActualMargin:
    def test_price_equals_cost_gives_zero(self):
        assert formulas.actual_margin(Decimal("10"), Decimal("10")) == Decimal("0")

    def test_negative_margin_reported_as_negative(self):
        """负毛利如实报负，不夹断为 0。"""
        assert formulas.actual_margin(Decimal("10"), Decimal("12")) < 0

    def test_zero_price_rejected(self):
        with pytest.raises(formulas.FormulaError):
            formulas.actual_margin(Decimal("0"), Decimal("10"))

    def test_roundtrip_with_f3(self):
        """F3 反推的价代入 F4 应回到目标毛利率（误差 <= 量化半步）。"""
        cost = Decimal("12.34")
        target = Decimal("0.6")
        price = formulas.suggested_price(cost, target)
        margin = formulas.actual_margin(price, cost)
        assert abs(margin - target) <= Decimal("0.01")


class TestF5ChangeRate:
    def test_old_price_zero_rejected(self):
        with pytest.raises(formulas.FormulaError):
            formulas.change_rate(Decimal("0"), Decimal("5"))

    def test_flat(self):
        assert formulas.change_rate(Decimal("5"), Decimal("5")) == Decimal("0")

    def test_sign(self):
        assert formulas.change_rate(Decimal("5"), Decimal("6")) > 0
        assert formulas.change_rate(Decimal("5"), Decimal("4")) < 0


class TestF6Quantize:
    def test_money_half_up_positive(self):
        assert quantize_money(Decimal("1.005")) == Decimal("1.01")

    def test_money_half_up_negative(self):
        """半分位远离零。"""
        assert quantize_money(Decimal("-1.005")) == Decimal("-1.01")

    def test_rate_quantize(self):
        assert quantize_rate(Decimal("0.123456")) == Decimal("0.1235")


class TestDecimalConversion:
    def test_float_goes_through_str(self):
        """float 必须先经 str 再转 Decimal，否则带二进制尾差。"""
        assert to_decimal(0.1) == Decimal("0.1")
        assert to_decimal(0.1) != Decimal(0.1)

    def test_bool_rejected(self):
        with pytest.raises(TypeError):
            to_decimal(True)
