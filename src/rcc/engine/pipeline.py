"""端到端编排层 —— CLI 与 GUI 的**唯一业务判断入口**。

**编排上收纪律**：表现层（CLI / GUI）只准经本模块的公开函数取数与判断，
前端零判定逻辑。同一业务判断在项目里只能有一处实现。

**门控按计算路径分作用域**（plan/02 §3）：``cost`` / ``pricing`` / ``alert``
各只校验自己引用的条目——不用"整包全 verified"当唯一门。

**报告层不重算**：本模块产出的 ``steps`` 是逐项计算留痕，报告直接渲染它。
"""

import os
from decimal import Decimal

from .. import __version__
from ..alert import threshold as alert_mod
from ..io import csv_import, snapshot
from ..model import quantize_money, quantize_rate, to_decimal
from ..rules import formulas
from ..rules.params import effective_params, load_params, scope_report

# 参数门控的三个计算作用域
SCOPE_ORDER = ("cost", "pricing", "alert")


def _load_bom(path):
    """读菜品配方 BOM：``{"dishes": [{"name":..., "items":[{"food":..., "qty":...}]}]}``。"""
    from ..model import load_json_decimal

    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    data = load_json_decimal(path)
    dishes = data.get("dishes") if isinstance(data, dict) else None
    if not isinstance(dishes, list) or not dishes:
        raise ValueError("BOM 文件缺少 dishes 数组或为空")
    return dishes


def yield_rate_for(cost_params, food):
    """取某食材的净料率。

    ``cost_params`` 是 ``effective_params("cost")`` 的返回值（即参数包的
    ``yield_rates`` 分区本身，键为食材名）。

    ``input_required`` 语义：参数包**本不承载**该食材的净料率时，运行时必须索取，
    **绝不静默取默认值**。此处显式抛错交由 CLI 转成退出码 2。
    """
    entry = cost_params.get(food)
    if not isinstance(entry, dict) or "value" not in entry:
        raise formulas.FormulaError(
            "食材「%s」缺少净料率（本不由参数包承载，需显式提供）" % food)
    return to_decimal(entry["value"]), entry


def compute_costcard(dishes, library, cost_params):
    """成本卡：F1 净料换算 → F2 BOM 汇总。逐行留痕可追溯。"""
    cards = []
    for dish in dishes:
        name = dish.get("name")
        if not name:
            raise ValueError("BOM 中存在缺少 name 的菜品条目")
        items = dish.get("items") or []
        lines, bom_items = [], []
        for item in items:
            food = item.get("food")
            if food not in library:
                raise ValueError("菜品「%s」引用了食材库中不存在的食材: %s" % (name, food))
            qty = to_decimal(item.get("qty", "0"))
            purchase_price = library[food]["ref_price"]
            rate, entry = yield_rate_for(cost_params, food)
            net_price = formulas.net_unit_price(purchase_price, rate)
            line_cost = net_price * qty
            lines.append({
                "food": food,
                "purchase_unit_price": quantize_money(purchase_price),
                "yield_rate": quantize_rate(rate),
                "loss_rate": quantize_rate(formulas.loss_rate(rate)),
                "net_unit_price": quantize_money(net_price),
                "qty": qty,
                "line_cost": quantize_money(line_cost),
                "yield_source": entry.get("source"),
                "price_source": library[food]["source"],
            })
            bom_items.append((net_price, qty))

        cost = formulas.dish_cost(bom_items)
        cards.append({
            "dish": name,
            "lines": lines,
            "cost": quantize_money(cost),
            "cost_exact": cost,
        })
    return cards


def compute_pricing(cards, pricing_params):
    """毛利率定价：F3 反推建议售价 + F4 实际毛利率。"""
    entry = pricing_params.get("target_margin") or {}
    if "value" not in entry:
        raise formulas.FormulaError("参数包缺少目标毛利率（需显式提供）")
    target = to_decimal(entry["value"])
    out = []
    for card in cards:
        price = formulas.suggested_price(card["cost_exact"], target)
        margin = formulas.actual_margin(price, card["cost_exact"])
        out.append({
            "dish": card["dish"],
            "cost": card["cost"],
            "target_margin": quantize_rate(target),
            "suggested_price": price,
            "actual_margin": quantize_rate(margin),
            "margin_source": entry.get("source"),
        })
    return out


def compute_alert(cards, old_snapshot, new_snapshot, alert_params, cost_params):
    """价格波动预警：F5 涨跌幅 → 受影响菜品重算 → 按涨跌幅降序。

    **两期必须是可区分的不同数据日**（M1 实测加）：数据日相同即"两期退化成同一期"，
    此时涨跌幅全为 0 却会以"无异常"的面貌呈现——这正是把 `pubDateStartTime` 写成
    `startDate` 时的静默故障形态（见 data/README §一之二）。故此处显式拒绝，
    交 CLI 转成用法错误（exit 2），不静默产出无意义的"全平"结果。
    """
    entry = alert_params.get("threshold") or {}
    if "value" not in entry:
        raise formulas.FormulaError("参数包缺少波动预警阈值（需显式提供）")
    threshold = to_decimal(entry["value"])

    if old_snapshot["date"] == new_snapshot["date"]:
        raise ValueError(
            "两期快照数据日相同（%s）——对比退化成同一期；"
            "请给出不同数据日的快照（旧→新）" % old_snapshot["date"])

    changes = alert_mod.diff_prices(old_snapshot["prices"], new_snapshot["prices"])
    impacted = alert_mod.impacted_dishes(cards, changes, old_snapshot, new_snapshot,
                                         cost_params)
    flagged = alert_mod.flag(changes, threshold)
    return {
        "changes": changes,
        "impacted": impacted,
        "flagged": flagged,
        "threshold": quantize_rate(threshold),
        "threshold_source": entry.get("source"),
        "old_snapshot": {"date": old_snapshot["date"],
                         "captured_date": old_snapshot.get("captured_date"),
                         "source": old_snapshot["source"],
                         "sha256": old_snapshot["sha256"]},
        "new_snapshot": {"date": new_snapshot["date"],
                         "captured_date": new_snapshot.get("captured_date"),
                         "source": new_snapshot["source"],
                         "sha256": new_snapshot["sha256"]},
    }


def _params_path(args):
    return getattr(args, "params", None)


def _scope_reports(data):
    return [scope_report(data, scope) for scope in SCOPE_ORDER]


def compute_full(args):
    """端到端：导入 → 成本卡 → 定价 →（可选）预警。

    返回可直接 JSON 序列化的字典（``Decimal`` 由 ``default=str`` 兜底）。
    """
    params_path = _params_path(args)
    data = load_params(params_path)
    cost_params = effective_params("cost", params_path)

    warnings = []
    if not getattr(args, "purchases", None):
        raise ValueError("缺少 --purchases 输入")
    parsed = csv_import.parse_purchases(args.purchases)
    warnings.extend(parsed["issues"])
    library = csv_import.build_food_library(parsed["rows"])

    if not getattr(args, "bom", None):
        raise ValueError("缺少 --bom 输入")
    dishes = _load_bom(args.bom)

    cards = compute_costcard(dishes, library, cost_params)
    pricing = compute_pricing(cards, effective_params("pricing", params_path))

    result = {
        "version": __version__,
        "purchases_summary": parsed["summary"],
        "library_size": len(library),
        "cards": cards,
        "pricing": pricing,
        "warnings": warnings,
        "param_scopes": _scope_reports(data),
    }

    if getattr(args, "with_alert", False):
        snapshot_paths = list(getattr(args, "snapshots", None) or [])
        if len(snapshot_paths) < 2:
            raise ValueError("启用预警需要两期快照（--snapshots 旧 新）")
        alert_params = effective_params("alert", params_path)
        old_snapshot = snapshot.load_snapshot(snapshot_paths[0])
        new_snapshot = snapshot.load_snapshot(snapshot_paths[1])
        result["alert"] = compute_alert(cards, old_snapshot, new_snapshot,
                                        alert_params, cost_params)
        result["alert_enabled"] = True
    else:
        result["alert_enabled"] = False

    result["summary"] = render_summary(result)
    return result


def check_inputs(args):
    """校验输入数据（不产出报告）。"""
    params_path = _params_path(args)
    data = load_params(params_path)
    cost_params = effective_params("cost", params_path)

    issues = []
    summary_parts = []
    if getattr(args, "purchases", None):
        parsed = csv_import.parse_purchases(args.purchases)
        issues.extend(parsed["issues"])
        summary_parts.append(parsed["summary"])
        library = csv_import.build_food_library(parsed["rows"])
    else:
        library = {}

    if getattr(args, "bom", None):
        dishes = _load_bom(args.bom)
        cards = compute_costcard(dishes, library, cost_params)
        summary_parts.append("成本卡 %d 道菜" % len(cards))
    else:
        cards = []

    return {
        "issues": issues,
        "summary": "; ".join(summary_parts) or "无输入",
        "param_scopes": _scope_reports(data),
    }


def render_summary(result):
    """人类可读摘要（CLI 默认输出）。"""
    parts = [result["purchases_summary"]]
    price_by_dish = {row["dish"]: row["suggested_price"]
                     for row in result["pricing"]}
    for card in result["cards"]:
        parts.append("菜品「%s」单份成本 %s 元，建议售价 %s 元"
                     % (card["dish"], card["cost"], price_by_dish.get(card["dish"])))
    if result.get("alert_enabled"):
        parts.append("预警：%d 项超阈值" % len(result["alert"]["flagged"]))
    if result["warnings"]:
        parts.append("异常 %d 条（见清单，未静默跳过）" % len(result["warnings"]))
    return "；".join(parts)
