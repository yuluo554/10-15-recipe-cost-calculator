"""价格波动：F5 涨跌幅、受影响菜品重算、阈值标记。

**预警 ≠ 判定**：只输出提示清单，**不自动改价**。
重算与排序规则确定（按涨跌幅降序）。
"""

from decimal import Decimal

from ..model import quantize_money, quantize_rate, to_decimal
from ..rules import formulas


def diff_prices(old_prices, new_prices):
    """两期快照的价格差异，按涨跌幅降序。

    返回逐条 ``{name, old_price, new_price, change_rate, status}``；
    ``status`` ∈ ``up``/``down``/``flat``/``new``（仅新期有，无对比基准）/
    ``gone``（仅旧期有）。**缺旧价一律记 ``new``，不臆造涨跌幅。**
    """
    names = set(old_prices) | set(new_prices)
    rows = []
    for name in sorted(names):
        old = old_prices.get(name)
        new = new_prices.get(name)
        if old is None:
            rows.append({"name": name, "old_price": None,
                         "new_price": quantize_money(new), "change_rate": None,
                         "status": "new"})
            continue
        if new is None:
            rows.append({"name": name, "old_price": quantize_money(old),
                         "new_price": None, "change_rate": None,
                         "status": "gone"})
            continue
        rate = formulas.change_rate(old, new)
        if rate > 0:
            status = "up"
        elif rate < 0:
            status = "down"
        else:
            status = "flat"
        rows.append({"name": name, "old_price": quantize_money(old),
                     "new_price": quantize_money(new),
                     "change_rate": quantize_rate(rate), "status": status})

    def sort_key(row):
        rate = row["change_rate"]
        # 无对比基准的（new/gone）排在最后
        return (1, Decimal(0)) if rate is None else (0, -rate)

    rows.sort(key=sort_key)
    return rows


def flag(changes, threshold):
    """标记超过阈值的食材（按绝对涨跌幅比较，涨跌都提示）。"""
    threshold = to_decimal(threshold)
    out = []
    for row in changes:
        rate = row["change_rate"]
        if rate is None:
            continue
        if abs(rate) >= threshold:
            out.append(row)
    return out


def impacted_dishes(cards, changes, old_snapshot, new_snapshot, cost_params):
    """受影响菜品清单：BOM 含该食材者，逐菜重算前后成本差。

    ``cost_params`` 是 ``effective_params("cost")`` 的返回值（净料率分区），
    重算必须用与成本卡同一份净料率——否则前后成本差会把口径差异算进去。
    """
    from ..engine.pipeline import yield_rate_for

    change_by_name = {row["name"]: row for row in changes}
    old_prices = old_snapshot["prices"]
    new_prices = new_snapshot["prices"]

    def dish_cost_with(prices, card):
        items = []
        for line in card["lines"]:
            food = line["food"]
            if food not in prices:
                # 该期快照没有这个食材 → 用成本卡原价（不臆造）
                net_price = line["net_unit_price"]
            else:
                rate, _entry = yield_rate_for(cost_params, food)
                net_price = formulas.net_unit_price(prices[food], rate)
            items.append((net_price, line["qty"]))
        return formulas.dish_cost(items)

    out = []
    for card in cards:
        touched = [line["food"] for line in card["lines"]
                   if line["food"] in change_by_name]
        if not touched:
            continue
        old_cost = dish_cost_with(old_prices, card)
        new_cost = dish_cost_with(new_prices, card)
        delta = new_cost - old_cost
        # 成本涨跌幅走 F5 正本，**不在这里手写 delta/old_cost**——那是第二份口径。
        # 旧成本为 0 时 F5 拒绝（缺基准），此处按"无基准"记 None（不臆造涨跌幅）。
        rate = formulas.change_rate(old_cost, new_cost) if old_cost > 0 else None
        out.append({
            "dish": card["dish"],
            "touched_foods": sorted(touched),
            "old_cost": quantize_money(old_cost),
            "new_cost": quantize_money(new_cost),
            "delta": quantize_money(delta),
            "change_rate": quantize_rate(rate) if rate is not None else None,
        })
    out.sort(key=lambda r: (r["change_rate"] is None,
                            -(r["change_rate"] or Decimal(0))))
    return out
