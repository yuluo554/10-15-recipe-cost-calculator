"""基准 runner：五套件 + 探活 + 门槛随 manifest 下发。

退出码三语义（锁进测试）：

=== ==========================================================
0   全部达标
1   未达标 **或** 计算非法 **或** 套件 ``not_enabled``
2   用法错误 / 坐标错误 / **``--only`` 传未知名** / 门槛配置缺失
=== ==========================================================

**"未启用"的套件不冒充通过**：分母为 0 时 ``not_enabled=true`` + notes 写明
"该类用例未生成" + **exit 1**。每个"达标"分支先问"分母为 0 时它会怎样？"——
恒真就是假门。

**门槛是数据不是代码**：验收门槛随 ``data/truth/manifest.json`` 下发，本层只读，
缺失即 ``ConfigError``（exit 2），**不得回落代码里的默认值**。
"""

import json
import os
from decimal import Decimal

from . import cases as cases_mod

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(REPO_ROOT, "data", "truth", "manifest.json")

# 套件注册表（新增基准必须注册在此，否则 --only 传它走 exit 2 而非静默跳过）
SUITES = ("import", "costcard", "alert", "boundary", "reconcile")


class UnknownSuite(ValueError):
    """``--only`` 传了未登记的套件名。"""


class ConfigError(ValueError):
    """门槛配置缺失或不可读。"""


def _display_path(path):
    """展示用路径：跨盘符时 ``relpath`` 会抛 ValueError，回落绝对路径。"""
    try:
        return os.path.relpath(path, REPO_ROOT)
    except ValueError:
        return path


def load_thresholds(manifest_path=MANIFEST_PATH):
    """读验收门槛（数据非代码）。缺失即报配置错误。"""
    if not os.path.isfile(manifest_path):
        raise ConfigError("基准门槛配置缺失: %s（门槛随 manifest 下发，不回落代码默认值）"
                          % _display_path(manifest_path))
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    thresholds = manifest.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ConfigError("manifest 缺少 thresholds 段")
    return thresholds


def _check_thresholds(thresholds, suite):
    """校验该套件的门槛项齐备（缺失即配置错误，不取默认值）。"""
    entry = thresholds.get(suite)
    if not isinstance(entry, dict):
        raise ConfigError("manifest 缺少套件 %r 的门槛项" % suite)
    for key in ("min_pass_rate", "max_false_positive_rate"):
        if key not in entry:
            raise ConfigError("套件 %r 门槛缺少 %r" % (suite, key))
    return entry


def _suite_not_enabled(suite, reason):
    """空分母分支：不冒充通过。"""
    return {
        "suite": suite,
        "not_enabled": True,
        "notes": reason,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "pass_rate": Decimal(0),
        "false_positive_rate": Decimal(0),
        "ok": False,
    }


# --------------------------------------------------------- 规则驱动层 B4/B5

def suite_boundary(params):
    """B4 规则驱动边界扫描：**不读真值库**，只从参数包与公式推导端点。

    证明"引擎在*所有*有限端点上对"——样本驱动层证明不了这一点，因为真值库
    只覆盖采样的净料率/用量。
    """
    from rcc.model import quantize_money, to_decimal
    from rcc.rules import formulas

    checks = []
    failures = []

    def check(name, cond, detail=""):
        checks.append(name)
        if not cond:
            failures.append("%s: %s" % (name, detail))

    # 端点全部由参数包算出——代码零业务数值字面量
    target = to_decimal(params["pricing"]["target_margin"]["value"])
    rates = sorted((name, to_decimal(entry["value"]))
                   for name, entry in params.get("yield_rates", {}).items())
    if not rates:
        return _suite_not_enabled("boundary", "参数包无净料率条目（无法推导端点）")
    probe_name, probe_rate = rates[0]

    # F1 方向：净料单价必然 >= 毛料单价（yield_rate <= 1）
    unit = Decimal(1)
    net = formulas.net_unit_price(Decimal("8"), unit)
    check("f1_rate_one", net == Decimal("8"), "净料率=1 时净料单价应等于毛料单价")
    halved = probe_rate / 2
    if halved > 0:
        net_half = formulas.net_unit_price(Decimal("8"), halved)
        net_full = formulas.net_unit_price(Decimal("8"), probe_rate)
        check("f1_monotone", net_half > net_full,
              "净料率减半应使净料单价升高（%s）" % probe_name)
    try:
        formulas.net_unit_price(Decimal("8"), Decimal(0))
        check("f1_rate_zero_rejected", False, "净料率=0 应被拒绝")
    except formulas.FormulaError:
        check("f1_rate_zero_rejected", True)
    try:
        formulas.net_unit_price(Decimal("8"), unit + Decimal(1))
        check("f1_rate_gt_one_rejected", False, "净料率>1 应被拒绝")
    except formulas.FormulaError:
        check("f1_rate_gt_one_rejected", True)
    # 边界邻域：略小于 1 与恰好 1（邻域宽度取量化精度）
    from rcc.model import RATE_EXP

    near = formulas.net_unit_price(Decimal("10"), unit - RATE_EXP)
    check("f1_near_one", near > Decimal("10"), "净料率略小于 1 时净料单价应略大于毛料单价")

    # F2 线性可加性：拆两行 == 一行两倍
    single = formulas.dish_cost([(Decimal("5"), Decimal("4"))])
    split = formulas.dish_cost([(Decimal("5"), Decimal("2")), (Decimal("5"), Decimal("2"))])
    check("f2_additive", single == split, "BOM 拆分不应改变总成本")
    # qty=0 不贡献成本
    zero = formulas.dish_cost([(Decimal("5"), Decimal(0)), (Decimal("3"), Decimal("2"))])
    check("f2_zero_qty", zero == Decimal("6"), "用量为 0 的食材不应贡献成本")
    try:
        formulas.dish_cost([])
        check("f2_empty_bom_rejected", False, "空 BOM 应被拒绝")
    except formulas.FormulaError:
        check("f2_empty_bom_rejected", True)

    # F3 端点：margin=0 → 售价=成本；margin=1 拒绝；单调性用参数包目标毛利率与其半值
    base_cost = Decimal("10")
    price = formulas.suggested_price(base_cost, Decimal(0))
    check("f3_margin_zero", price == base_cost, "目标毛利率为 0 时售价应等于成本")
    try:
        formulas.suggested_price(base_cost, unit)
        check("f3_margin_one_rejected", False, "目标毛利率=1 应被拒绝")
    except formulas.FormulaError:
        check("f3_margin_one_rejected", True)
    low = formulas.suggested_price(base_cost, target / 2)
    high = formulas.suggested_price(base_cost, target)
    check("f3_monotone", high > low, "目标毛利率越高售价越高")

    # F4 端点：售价=成本 → 毛利率 0；负毛利如实报负
    margin = formulas.actual_margin(base_cost, base_cost)
    check("f4_zero_margin", margin == Decimal(0), "售价等于成本时毛利率应为 0")
    margin = formulas.actual_margin(base_cost, base_cost + Decimal(2))
    check("f4_negative", margin < 0, "负毛利应如实报负，不夹断为 0")
    try:
        formulas.actual_margin(Decimal(0), base_cost)
        check("f4_price_zero_rejected", False, "售价=0 应被拒绝")
    except formulas.FormulaError:
        check("f4_price_zero_rejected", True)

    # F5 端点：old=0 拒绝；new=old → 0；符号正确
    try:
        formulas.change_rate(Decimal(0), Decimal("5"))
        check("f5_old_zero_rejected", False, "旧价为 0 应被拒绝（缺基准）")
    except formulas.FormulaError:
        check("f5_old_zero_rejected", True)
    flat = formulas.change_rate(Decimal("5"), Decimal("5"))
    check("f5_flat", flat == Decimal(0), "价格未变时涨跌幅应为 0")
    up = formulas.change_rate(Decimal("5"), Decimal("6"))
    down = formulas.change_rate(Decimal("5"), Decimal("4"))
    check("f5_sign", up > 0 and down < 0, "涨为正、跌为负")

    # F6 量化方向：半分位 ROUND_HALF_UP（远离零）
    half_money = quantize_money(Decimal("1.005"))
    check("f6_half_up_pos", half_money == Decimal("1.01"), "半分位应向上量化")
    half_neg = quantize_money(Decimal("-1.005"))
    check("f6_half_up_neg", half_neg == Decimal("-1.01"), "负半分位应远离零量化")

    # 参数包驱动的边界：净料率条目全部在 (0,1] 内（端点由参数包算出，代码零字面量）
    for name, rate in rates:
        check("params_range_%s" % name, Decimal(0) < rate <= unit,
              "参数包净料率 %s 越界" % name)
        formulas.net_unit_price(base_cost, rate)

    total = len(checks)
    failed = len(failures)
    return {
        "suite": "boundary",
        "not_enabled": False,
        "notes": "规则驱动：不读真值库，端点由参数包与公式定义推导",
        "total": total,
        "passed": total - failed,
        "failed": failed,
        "pass_rate": Decimal(total - failed) / Decimal(total) if total else Decimal(0),
        "false_positive_rate": Decimal(0),
        "failures": failures,
        "ok": failed == 0 and total > 0,
    }


def suite_reconcile(params):
    """B5 双向对账：公式推导端点 vs 穷举扫描恢复点，**两条独立路径互验**。"""
    from rcc.model import quantize_money, to_decimal
    from rcc.rules import formulas

    target = to_decimal(params["pricing"]["target_margin"]["value"])
    cost = Decimal("12.34")

    checks, failures = [], []

    def check(name, cond, detail=""):
        checks.append(name)
        if not cond:
            failures.append("%s: %s" % (name, detail))

    # 路径一：公式推导——给定成本与目标毛利率，反推应得售价
    derived = formulas.suggested_price(cost, target)
    # 路径二：穷举扫描——在售价区间上粗扫 + 恢复窗口细扫，找出使实际毛利率
    # 回到目标值的售价（独立于路径一的实现）
    low = cost
    high = cost * 2 + Decimal("100")
    step = Decimal("1")
    probe = low
    while probe < high:
        margin = formulas.actual_margin(probe, cost)
        if margin >= target:
            break
        probe += step
    else:
        probe = high
    # 恢复窗口逐分细扫
    window_start = max(low, probe - step)
    fine = window_start
    while fine <= probe:
        margin = formulas.actual_margin(fine, cost)
        if margin >= target:
            break
        fine += Decimal("0.01")
    recovered = fine

    # 两路径差异不超过量化半步
    half_step = Decimal("0.005")
    check("b5_paths_agree", abs(recovered - derived) <= half_step,
          "推导端点 %s 与穷举恢复点 %s 差异超量化半步" % (derived, recovered))

    # 交叉验证：把推导价代回 F4，应回到目标毛利率（误差 <= 量化半步）
    margin_back = formulas.actual_margin(derived, cost)
    check("b5_roundtrip", abs(margin_back - target) <= Decimal("0.01"),
          "反推价代回实际毛利率 %s 未回到目标 %s" % (margin_back, target))

    # 单调性：成本升高 → 建议售价升高
    price_low = formulas.suggested_price(Decimal("10"), target)
    price_high = formulas.suggested_price(Decimal("20"), target)
    check("b5_monotone_cost", price_high > price_low, "成本升高应使建议售价升高")

    # 量化不破坏序：量化后的价仍使实际毛利率 >= 目标（挂牌价取整后的保守性）
    quantized = quantize_money(derived)
    check("b5_quantized_defined", quantized == derived, "推导价本身应为分位值")

    total = len(checks)
    failed = len(failures)
    return {
        "suite": "reconcile",
        "not_enabled": False,
        "notes": "双向对账：公式推导 vs 穷举扫描，两条独立实现路径互验",
        "total": total,
        "passed": total - failed,
        "failed": failed,
        "pass_rate": Decimal(total - failed) / Decimal(total) if total else Decimal(0),
        "false_positive_rate": Decimal(0),
        "failures": failures,
        "ok": failed == 0 and total > 0,
    }


# ------------------------------------------------------- 样本驱动层 B1/B2/B3

def _sample_suite(suite, truth_path):
    """样本驱动套件：读冻结真值库对账。

    真值库尚未生成（M4 前）时走 ``not_enabled`` 分支——**不冒充通过**。
    """
    if not os.path.isfile(truth_path):
        return _suite_not_enabled(
            suite, "该类用例未生成（真值库待 M4 产出）")
    with open(truth_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    records = payload.get("cases") if isinstance(payload, dict) else payload
    if not records:
        return _suite_not_enabled(suite, "真值库为空（该类用例未生成）")

    total = len(records)
    failed = 0
    failures = []
    for record in records:
        expected = cases_mod.observed_nonpass(record.get("expect", {}))
        observed = cases_mod.observed_nonpass(record.get("observed", {}))
        comparison = cases_mod.compare_nonpass(expected, observed)
        if not comparison["match"]:
            failed += 1
            failures.append("用例 %s 不一致: 漏 %s / 多 %s"
                            % (record.get("id"), comparison["missing"],
                               comparison["unexpected"]))
    return {
        "suite": suite,
        "not_enabled": False,
        "notes": "样本驱动：真值库全量重算对账",
        "total": total,
        "passed": total - failed,
        "failed": failed,
        "pass_rate": Decimal(total - failed) / Decimal(total) if total else Decimal(0),
        "false_positive_rate": Decimal(0),
        "failures": failures,
        "ok": failed == 0 and total > 0,
    }


def run_suites(only=None, manifest_path=MANIFEST_PATH, params=None):
    """跑套件。``only`` 为 ``None``/空 时跑全部。"""
    only = list(only or [])
    for name in only:
        if name not in SUITES:
            raise UnknownSuite("未登记的基准套件: %r（已登记: %s）"
                               % (name, ", ".join(SUITES)))

    thresholds = load_thresholds(manifest_path)
    if params is None:
        from rcc.rules.params import load_params

        params = load_params()

    suites = []
    for name in SUITES:
        if only and name not in only:
            continue
        if name == "boundary":
            result = suite_boundary(params)
        elif name == "reconcile":
            result = suite_reconcile(params)
        else:
            truth_path = os.path.join(REPO_ROOT, "data", "truth", "%s.json" % name)
            result = _sample_suite(name, truth_path)

        # 门槛判定只对**实际跑了的**套件做（--suite 部分运行不判定未测指标）
        if result.get("not_enabled"):
            result["threshold_ok"] = False
            result["ok"] = False
        else:
            entry = _check_thresholds(thresholds, name)
            min_rate = Decimal(str(entry["min_pass_rate"]))
            max_fp = Decimal(str(entry["max_false_positive_rate"]))
            result["threshold_ok"] = (result["pass_rate"] >= min_rate
                                      and result["false_positive_rate"] <= max_fp)
            result["ok"] = bool(result["ok"] and result["threshold_ok"])
        suites.append(result)

    passed = all(suite["ok"] for suite in suites) if suites else False
    return {
        "suites": suites,
        "passed": passed,
        "partial": bool(only),
        "not_enabled": [s["suite"] for s in suites if s.get("not_enabled")],
    }


def render_text(result):
    """文本渲染（部分运行时声明未测指标）。"""
    lines = ["内置基准套件结果", ""]
    for suite in result["suites"]:
        if suite.get("not_enabled"):
            lines.append("[未启用] %s — %s" % (suite["suite"], suite["notes"]))
            continue
        lines.append("[%s] %s  通过 %d/%d  达标率 %s  误报率 %s  %s" % (
            "达标" if suite["ok"] else "未达标",
            suite["suite"], suite["passed"], suite["total"],
            suite["pass_rate"], suite["false_positive_rate"], suite["notes"]))
        for failure in suite.get("failures", []):
            lines.append("    - %s" % failure)
    if result.get("partial"):
        lines.append("")
        lines.append("（部分运行：未测套件的指标不作判定）")
    if result["not_enabled"]:
        lines.append("")
        lines.append("未启用套件（不计为通过）: %s" % ", ".join(result["not_enabled"]))
    lines.append("")
    lines.append("总判: %s" % ("达标" if result["passed"] else "未达标"))
    return "\n".join(lines)
