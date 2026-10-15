"""端到端编排层 —— CLI 与 GUI 的**唯一业务判断入口**。

**编排上收纪律**：表现层（CLI / GUI）只准经本模块的公开函数取数与判断，
前端零判定逻辑。同一业务判断在项目里只能有一处实现。

**门控按计算路径分作用域**（plan/02 §3）：``cost`` / ``pricing`` / ``alert``
各只校验自己引用的条目——不用"整包全 verified"当唯一门。

**报告层不重算**：本模块产出的 ``steps`` 是逐项计算留痕，报告直接渲染它。
"""

import os
from decimal import Decimal, InvalidOperation

from .. import __version__
from ..alert import threshold as alert_mod
from ..io import csv_import, snapshot
from ..model import (
    STATUS_INVALID,
    SourceMissing,
    quantize_money,
    quantize_rate,
    to_decimal,
    validate_source,
)
from ..rules import formulas
from ..rules.params import (
    ParamsInputRequired,
    effective_params,
    load_params,
    scope_report,
)

# 参数门控的三个计算作用域
SCOPE_ORDER = ("cost", "pricing", "alert")

# 成本卡行级异常代码（机读判据）。
# **行级与文件级不混用**（K28）：本代码描述"某道菜的某个食材行算不出净料单价"，
# 与 csv_import 的进货单行级代码、以及 line=0 的文件级代码（`no_usable_rows`）
# 语义各不相同，故各自独立登记。
ISSUE_YIELD_OUT_OF_RANGE = "yield_rate_out_of_range"
ISSUE_QTY_INVALID = "qty_invalid"
# 文件级结论：全部菜品都因行级问题被排除 → 成本卡为空
ISSUE_NO_USABLE_DISHES = "no_usable_dishes"


def _line_issue(dish, food, code, reason):
    """成本卡行级异常条目。

    ``where`` 是**人读定位标签**（菜品·食材），与进货单的行号定位并列而不混用：
    成本卡的行不是 CSV 的行，没有行号可指，硬填一个行号会让读者去查一个不存在的位置。
    """
    return {"line": None, "where": "菜品「%s」·食材「%s」" % (dish, food),
            "status": STATUS_INVALID, "code": code, "reason": reason}


def _load_bom(path):
    """读菜品配方 BOM，返回 ``(dishes, source)``。

    形态：``{"dishes": [{"name":..., "items":[{"food":..., "qty":...}]}]}``。

    形态失败（缺 ``dishes`` / 空数组 / 非 JSON 对象）一律抛错 → CLI exit 2：
    这是整份文件的形态问题，不是某一行的问题（同 K20 的进货单口径）。

    **用量（``qty``）也必须挂来源**（plan/02 §二：每个进入计算路径的参数必须挂
    ``source``，``qty`` 的承载位置就是菜品 BOM、``kind = user``）。来源挂在
    **文件级**——同一份 BOM 里所有用量共享同一出处（"这份用户配方"），逐行重复
    同一个来源对象只是噪声，不是更强的保证。
    """
    from ..model import load_json_decimal, make_source

    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    data = load_json_decimal(path)
    dishes = data.get("dishes") if isinstance(data, dict) else None
    if not isinstance(dishes, list) or not dishes:
        raise ValueError("BOM 文件缺少 dishes 数组或为空")
    source = make_source("user", os.path.basename(path),
                         note="用户配方 BOM（用量来源）")
    return dishes, source


def _sourced(source, label):
    """在**消费点**显式校验来源标记（plan/02 §二：未挂来源的参数不得进入计算路径）。

    与 ``make_source`` 的构造期校验是两件事：来源对象可能来自**解析后的 JSON**
    （参数包条目、快照元数据、进货单行），那条路径不经过 ``make_source``。只在
    构造期校验等于**只守了自己造的那一半**——来自外部文件的来源对象会静默溜过。

    ``label`` 进报错文案，点明**是哪个参数**没挂来源——只报"参数未挂来源标记"
    会让用户不知道该补哪个（同 K24：错误必须指向正确的对象）。
    """
    try:
        validate_source(source)
    except SourceMissing as exc:
        raise SourceMissing("参数「%s」的来源标记不合法（%s）" % (label, exc))
    return source


def yield_rate_for(cost_params, food):
    """取某食材的净料率。

    ``cost_params`` 是 ``effective_params("cost")`` 的返回值（即参数包的
    ``yield_rates`` 分区本身，键为食材名）。

    ``input_required`` 语义（plan/02 §三：**放行门控，但运行时必索，绝不静默取
    默认值**）：参数包**本不承载**该食材的净料率时，此处显式抛
    ``ParamsInputRequired`` 交由 CLI 转成退出码 2。注意这与 ``effective_params``
    的门控不是同一步——门控放行（不阻断该作用域），索取发生在**取数点**。

    注意区分两种"净料率有问题"（plan/02 §一）：

    - **缺条目**（本不由参数包承载）→ 缺输入 → exit 2（本函数抛错）；
    - **有条目但值越界** ∉ (0,1] → **该行 invalid 并入清单** → exit 1
      （由 ``compute_costcard`` 记 issue，不在此处抛错）。
    """
    entry = cost_params.get(food)
    if not isinstance(entry, dict) or "value" not in entry:
        raise ParamsInputRequired(
            "cost", [food],
            detail="食材「%s」缺少净料率（本不由参数包承载，需显式提供）" % food)
    return to_decimal(entry["value"]), entry


def compute_costcard(dishes, library, cost_params, qty_source):
    """成本卡：F1 净料换算 → F2 BOM 汇总。逐行留痕可追溯。

    返回 ``{"cards": [...], "issues": [...]}``。

    **行级前提校验的失败形态**（plan/02 §一：越界一律判该行 ``invalid`` 并列入
    异常清单，不静默跳过、不静默取 0/1）：

    - 某食材的净料率越界 ∉ (0,1] → 记一条行级 issue；
    - 某食材的用量非数值或为负 → 记一条行级 issue。

    此时**整道菜**（而非仅该行）被排除出成本卡：成本是各行之和，丢掉一行再报出
    一个"看起来完整"的合计，等于把一个自洽但偏低的数字当成对的（plan/02 §5 红线
    同旨）。**该判断登记为口径**——否则下一个人会把"丢行求和"实现成另一种，
    两者都能自圆其说。

    ``qty_source`` 是用量的来源标记（挂在 BOM 文件级，见 ``_load_bom``）：在
    **消费点**显式校验，未挂来源即抛 ``SourceMissing``。
    """
    _sourced(qty_source, "BOM 用量")
    cards, issues = [], []
    for dish in dishes:
        name = dish.get("name")
        if not name:
            raise ValueError("BOM 中存在缺少 name 的菜品条目")
        items = dish.get("items") or []
        lines, bom_items, dish_issues = [], [], []
        for item in items:
            food = item.get("food")
            if food not in library:
                raise ValueError("菜品「%s」引用了食材库中不存在的食材: %s" % (name, food))

            rate, entry = yield_rate_for(cost_params, food)
            if not (Decimal(0) < rate <= Decimal(1)):
                dish_issues.append(_line_issue(
                    name, food, ISSUE_YIELD_OUT_OF_RANGE,
                    "净料率越界（须 ∈ (0,1]，实为 %s）" % rate))
                continue

            try:
                qty = to_decimal(item.get("qty", "0"))
            except (InvalidOperation, TypeError, ValueError):
                dish_issues.append(_line_issue(
                    name, food, ISSUE_QTY_INVALID,
                    "用量非数值: %r" % item.get("qty")))
                continue
            if qty < 0:
                dish_issues.append(_line_issue(
                    name, food, ISSUE_QTY_INVALID, "用量为负: %s" % qty))
                continue

            purchase_price = library[food]["ref_price"]
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
                "yield_source": _sourced(entry.get("source"), "净料率"),
                "price_source": _sourced(library[food]["source"], "进货单价"),
                "qty_source": qty_source,
            })
            bom_items.append((net_price, qty))

        if dish_issues:
            # 有任何一行不成立，整道菜的成本都不可信 → 排除并列出原因
            issues.extend(dish_issues)
            continue

        cost = formulas.dish_cost(bom_items)
        cards.append({
            "dish": name,
            "lines": lines,
            "cost": quantize_money(cost),
            "cost_exact": cost,
        })
    return {"cards": cards, "issues": issues}


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


def _require_usable_rows(parsed, label):
    """零可用行时给出**指向真因**的报错。

    全部行判 ``invalid``/``unknown`` 时食材库为空，若放任下游继续，报错会变成
    "BOM 引用了食材库中不存在的食材"——**把读者引向 BOM 去改，而真因在进货单**。
    这类"错误指向错误的对象"比沉默更坏：用户会照着提示改错文件。

    退出码语义不变（输入不可用 = 2），只是把原因说准。
    """
    if parsed["rows"]:
        return
    counts = parsed.get("status_counts") or {}
    raise ValueError(
        "%s无任何可用行（%d 行全部异常：invalid %d / unknown %d）——"
        "请先修正进货单" % (label, len(parsed["issues"]),
                          counts.get("invalid", 0), counts.get("unknown", 0)))


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
    _require_usable_rows(parsed, "进货单")
    library = csv_import.build_food_library(parsed["rows"])

    if not getattr(args, "bom", None):
        raise ValueError("缺少 --bom 输入")
    dishes, qty_source = _load_bom(args.bom)

    costcard = compute_costcard(dishes, library, cost_params, qty_source)
    cards = costcard["cards"]
    warnings.extend(costcard["issues"])
    if not cards:
        # 全部菜品都因行级问题被排除 → 成本卡为空，无法进入定价。
        # 这是**输入数据不可用**（exit 2），不是"算出了 0 道菜"。
        raise ValueError(
            "BOM 中 %d 道菜全部存在行级问题，成本卡为空——请先修正 BOM 或净料率参数"
            % len(dishes))
    pricing = compute_pricing(cards, effective_params("pricing", params_path))

    result = {
        "version": __version__,
        "purchases_summary": parsed["summary"],
        "library_size": len(library),
        "duplicate_food_names": csv_import.duplicate_names(parsed["rows"]),
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
    """校验输入数据（不产出报告）。

    **与 ``compute_full`` 共用同一分派点**：两者都只经 ``csv_import.parse_purchases``
    取三态判定，本模块**不另写一份列名映射或判定逻辑**（plan/06 硬纪律）。

    与 ``run`` 的差别只在**失败后的语义**：``run`` 零可用行即无法继续 → exit 2；
    ``check`` 的职责就是"报告问题"，零可用行正是它要报的问题 → 记入 issues 后
    **不抛错**（exit 1）。此时**不做 BOM 交叉核对**——食材库为空是进货单造成的，
    拿它去比对 BOM 只会报出"BOM 引用了不存在的食材"，把读者引向错误的文件。
    """
    params_path = _params_path(args)
    data = load_params(params_path)
    cost_params = effective_params("cost", params_path)

    issues = []
    summary_parts = []
    library = {}
    if getattr(args, "purchases", None):
        parsed = csv_import.parse_purchases(args.purchases)
        issues.extend(parsed["issues"])
        summary_parts.append(parsed["summary"])
        duplicates = csv_import.duplicate_names(parsed["rows"])
        if duplicates:
            summary_parts.append("重复品名 %d 个（食材库取最后一条价）: %s"
                                 % (len(duplicates), "、".join(duplicates)))
        if parsed["rows"]:
            library = csv_import.build_food_library(parsed["rows"])
        else:
            issues.append({
                "line": 0, "status": STATUS_INVALID,
                "code": csv_import.ISSUE_NO_USABLE_ROWS,
                "reason": "进货单无任何可用行——食材库为空，已跳过 BOM 交叉核对",
            })

    cards = []
    if getattr(args, "bom", None):
        dishes, qty_source = _load_bom(args.bom)
        if library:
            costcard = compute_costcard(dishes, library, cost_params, qty_source)
            cards = costcard["cards"]
            issues.extend(costcard["issues"])
            excluded = len(dishes) - len(cards)
            summary_parts.append("成本卡 %d 道菜%s"
                                 % (len(cards),
                                    "（%d 道因行级问题被排除）" % excluded if excluded else ""))
            if not cards:
                # 文件级结论（同 K28：行级代码与文件级代码不混用）——
                # "全部菜都算不出来"不是"某道菜有问题"，它不指向任何一道具体的菜。
                issues.append({
                    "line": 0, "status": STATUS_INVALID,
                    "code": ISSUE_NO_USABLE_DISHES,
                    "reason": "BOM 全部菜品均存在行级问题——成本卡为空",
                })
        else:
            summary_parts.append("BOM %d 道菜（未核对：食材库为空）" % len(dishes))

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
    if result.get("duplicate_food_names"):
        parts.append("重复品名 %d 个（食材库取最后一条价）: %s"
                     % (len(result["duplicate_food_names"]),
                        "、".join(result["duplicate_food_names"])))
    return "；".join(parts)


def render_issues(issues):
    """异常行清单的**人类可读渲染**（CLI 非 JSON 通路用；JSON 通路直接用原清单）。

    摘要里写着"见清单"，那就必须真有清单可看——否则读者拿到的是一句指向空处的
    指路语。报告层与 CLI 都消费本函数，**不各写一份格式**。

    三种定位形态各有其位，**不得互相冒充**（同 K28 的行级/文件级不混用）：

    - ``line`` 为正整数 → 进货单的第 N 行；
    - ``line == 0`` → **文件级结论**（如零可用行），不指向具体某行；
    - ``line`` 为 ``None`` 且有 ``where`` → **成本卡的行级问题**（按"菜品·食材"定位，
      没有 CSV 行号可指——硬填一个行号会让读者去查一个不存在的位置）。

    返回行列表（不含换行），便于调用方决定缩进与流。
    """
    if not issues:
        return []
    lines = ["异常清单（逐条列出，未静默跳过）:"]
    for issue in issues:
        line_no = issue.get("line")
        if line_no is None and issue.get("where"):
            where = issue["where"]
        elif line_no is None:
            where = "未知位置"
        elif int(line_no):
            where = "第 %s 行" % line_no
        else:
            where = "文件级"
        lines.append("  %s  [%s] %s" % (where, issue.get("status", ""),
                                        issue.get("reason", "")))
    return lines

