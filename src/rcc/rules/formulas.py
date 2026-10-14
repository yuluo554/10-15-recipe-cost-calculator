"""换算公式 F1–F6 —— 数值口径的单一定义点。

本模块是 plan/02 的代码化身：引擎、报告、基准、文档一律引用此处，
**禁止任何地方手写第二份口径**（含 docstring 与注释里的示例数值）。

全部公式接受/返回 ``Decimal``；前提校验失败一律抛 ``FormulaError``，
由调用方列入异常清单——**不静默跳过、不静默取 0/1**。
"""

from decimal import Decimal

from ..model import quantize_money, to_decimal


class FormulaError(ValueError):
    """公式前提校验失败。"""


def _require(cond, msg):
    if not cond:
        raise FormulaError(msg)


def net_unit_price(purchase_unit_price, yield_rate):
    """F1 净料单价 = 毛料进货单价 ÷ 净料率。

    ``yield_rate`` 是"净料重 / 毛料重"，取值域 ``(0, 1]``——因此净料单价
    **必然 ≥ 毛料单价**。方向反了会算出净料单价 < 毛料单价，属实现缺陷。

    注：损耗率不是第二个参数，``loss_rate = 1 - yield_rate`` 是同一参数的
    换算面，只在呈现层由它导出（避免同一事实两份真相）。
    """
    price = to_decimal(purchase_unit_price)
    rate = to_decimal(yield_rate)
    _require(price >= 0, "毛料单价不得为负")
    _require(rate > 0, "净料率必须大于 0")
    _require(rate <= 1, "净料率不得超过 1（净料重不能多于毛料重）")
    return price / rate


def loss_rate(yield_rate):
    """净料率的换算面：损耗率 = 1 − 净料率。仅用于呈现，不参与计算。"""
    rate = to_decimal(yield_rate)
    _require(rate > 0, "净料率必须大于 0")
    _require(rate <= 1, "净料率不得超过 1")
    return Decimal(1) - rate


def dish_cost(items):
    """F2 单份成本 = Σ(净料单价 × 用量)。

    ``items`` 为 ``(net_price, qty)`` 序列。BOM 不得为空——空 BOM 是数据缺陷，
    不是"成本为 0"。
    """
    items = list(items)
    _require(items, "菜品配方 BOM 不得为空")
    total = Decimal(0)
    for net_price, qty in items:
        price = to_decimal(net_price)
        quantity = to_decimal(qty)
        _require(price >= 0, "净料单价不得为负")
        _require(quantity >= 0, "用量不得为负")
        total += price * quantity
    return total


def suggested_price(cost, target_margin):
    """F3 建议售价 = 成本 ÷ (1 − 目标毛利率)。

    ``target_margin = 1`` 不可解（除零），门控拒绝。
    返回值**先量化**——真实挂牌价是分位值；F4 据此反算实际毛利率，
    这是量化作用于中间量的唯一例外（plan/02 §1 注记 3）。
    """
    cost_value = to_decimal(cost)
    margin = to_decimal(target_margin)
    _require(cost_value >= 0, "成本不得为负")
    _require(margin >= 0, "目标毛利率不得为负")
    _require(margin < 1, "目标毛利率必须小于 1（等于 1 时售价无解）")
    return quantize_money(cost_value / (Decimal(1) - margin))


def actual_margin(price, cost):
    """F4 实际毛利率 = (售价 − 成本) ÷ 售价。

    售价为 0 不可解，门控拒绝。负毛利**如实报负**，不夹断为 0。
    """
    price_value = to_decimal(price)
    cost_value = to_decimal(cost)
    _require(price_value > 0, "售价必须大于 0")
    _require(cost_value >= 0, "成本不得为负")
    return (price_value - cost_value) / price_value


def change_rate(old_price, new_price):
    """F5 涨跌幅 = (新价 − 旧价) ÷ 旧价。

    旧价为 0 不可解（不是除零错误，是缺基准），门控拒绝。
    涨为正、跌为负，符号如实。
    """
    old = to_decimal(old_price)
    new = to_decimal(new_price)
    _require(old > 0, "旧价格必须大于 0（缺对比基准）")
    _require(new >= 0, "新价格不得为负")
    return (new - old) / old
