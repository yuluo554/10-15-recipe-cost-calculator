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
import time
from decimal import Decimal

from . import cases as cases_mod

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRUTH_DIR = os.path.join(REPO_ROOT, "data", "truth")
MANIFEST_PATH = os.path.join(TRUTH_DIR, "manifest.json")

# 套件注册表（新增基准必须注册在此，否则 --only 传它走 exit 2 而非静默跳过）
SUITES = ("import", "costcard", "alert", "boundary", "reconcile")

# 阈值字段（缺一即配置错误——**不取默认值**）
THRESHOLD_KEYS = ("min_pass_rate", "max_false_positive_rate", "max_duration_seconds",
                  "measures_false_positive")


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


def load_manifest(manifest_path=MANIFEST_PATH):
    """读整份 manifest（门槛 + 覆盖度登记**同一份数据**）。缺失即报配置错误。"""
    if not os.path.isfile(manifest_path):
        raise ConfigError("基准门槛配置缺失: %s（门槛随 manifest 下发，不回落代码默认值）"
                          % _display_path(manifest_path))
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    if not isinstance(manifest, dict):
        raise ConfigError("manifest 根节点必须是对象")
    return manifest


def load_thresholds(manifest_path=MANIFEST_PATH):
    """读验收门槛（数据非代码）。缺失即报配置错误。"""
    thresholds = load_manifest(manifest_path).get("thresholds")
    if not isinstance(thresholds, dict):
        raise ConfigError("manifest 缺少 thresholds 段")
    return thresholds


def load_coverage(manifest_path=MANIFEST_PATH):
    """读覆盖度双登记（**分母形态总数 + 分子采样数**）。

    只写分子即假覆盖（plan/03 §四），故本函数要求两栏都在——缺任一栏即配置错误，
    不静默当作 0。
    """
    coverage = load_manifest(manifest_path).get("coverage")
    if not isinstance(coverage, dict):
        raise ConfigError("manifest 缺少 coverage 段（覆盖度双登记）")
    return coverage


def _check_thresholds(thresholds, suite):
    """校验该套件的门槛项齐备（缺失即配置错误，不取默认值）。"""
    entry = thresholds.get(suite)
    if not isinstance(entry, dict):
        raise ConfigError("manifest 缺少套件 %r 的门槛项" % suite)
    for key in THRESHOLD_KEYS:
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

def _sample_suite(suite, truth_path, workdir):
    """样本驱动套件：读冻结真值库，**把每条用例的输入喂给真引擎活体观测**后对账。

    真值库只存**输入 + 期望**（不含 ``observed``）——若把观测也冻进库，评测就退化
    成"比对两个冻结字典"，**引擎坏掉也照样全绿**（本项目最忌的假门）。故观测一律
    由 ``cases.observe_*`` 在运行时实算。

    真值库不存在或为空 → 走 ``not_enabled`` 分支——**不冒充通过**。
    """
    if not os.path.isfile(truth_path):
        return _suite_not_enabled(
            suite, "该类用例未生成（真值库缺失，请跑 tools/gen_truth.py）")
    with open(truth_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    records = payload.get("cases") if isinstance(payload, dict) else payload
    if not records:
        return _suite_not_enabled(suite, "真值库为空（该类用例未生成）")

    total = len(records)
    failed = 0
    failures = []
    observed_total = 0
    unexpected_total = 0
    for record in records:
        comparison = cases_mod.evaluate_case(suite, record, workdir)
        observed_total += comparison["observed_count"]
        unexpected_total += comparison["unexpected_count"]
        if comparison["match"]:
            continue
        failed += 1
        detail = "用例 %s 不一致: 漏 %s / 多 %s" % (
            comparison.get("id"), comparison["missing"], comparison["unexpected"])
        if comparison.get("error"):
            detail += "（观测异常 %s）" % comparison["error"]
        failures.append(detail)
    # 误报率是**实测值**（观测多出的结论键占比），不是写死的 0——
    # 写死的指标与门槛比较是恒真假门：门槛就算配 0 也永远满足。
    false_positive_rate = (Decimal(unexpected_total) / Decimal(observed_total)
                           if observed_total else Decimal(0))
    return {
        "suite": suite,
        "not_enabled": False,
        "notes": "样本驱动：真值库输入实喂引擎，活体观测对账（非比对冻结观测）",
        "total": total,
        "passed": total - failed,
        "failed": failed,
        "pass_rate": Decimal(total - failed) / Decimal(total) if total else Decimal(0),
        "false_positive_rate": false_positive_rate,
        "failures": failures,
        "ok": failed == 0 and total > 0,
    }


def run_suites(only=None, manifest_path=MANIFEST_PATH, params=None, workdir=None):
    """跑套件。``only`` 为 ``None``/空 时跑全部。

    **时长门槛也判定**（``max_duration_seconds`` 随 manifest 下发）：原先该字段
    既未校验也未使用——登记在门槛里却没人看，等于"登记了却静默不判"。现按
    "实测单套件耗时 ≤ 门槛"判定，超时即该套件未达标（exit 1），并给出实测值
    供读者判断是机器慢还是基准退化了。
    """
    only = list(only or [])
    for name in only:
        if name not in SUITES:
            raise UnknownSuite("未登记的基准套件: %r（已登记: %s）"
                               % (name, ", ".join(SUITES)))

    thresholds = load_thresholds(manifest_path)
    coverage = load_coverage(manifest_path)
    if params is None:
        from rcc.rules.params import load_params

        params = load_params()

    if workdir is None:
        # 用例的内联输入落在**仓库树外**（仓库内 out/ 属忽略区，往那里写会
        # "看着成功其实没写"）。自建的临时目录用完即清，不留给读者收拾。
        import shutil
        import tempfile

        workdir = tempfile.mkdtemp(prefix="rcc-bench-")
        owns_workdir = True
    else:
        owns_workdir = False

    try:
        return _run_registered(only, thresholds, coverage, params, workdir)
    finally:
        if owns_workdir:
            shutil.rmtree(workdir, ignore_errors=True)


def _run_registered(only, thresholds, coverage, params, workdir):
    """按注册顺序跑选定套件，逐套件计时并判定门槛。"""
    suites = []
    for name in SUITES:
        if only and name not in only:
            continue
        started = time.monotonic()
        if name == "boundary":
            result = suite_boundary(params)
        elif name == "reconcile":
            result = suite_reconcile(params)
        else:
            truth_path = os.path.join(TRUTH_DIR, "%s.json" % name)
            result = _sample_suite(name, truth_path, workdir)
        duration = Decimal(repr(round(time.monotonic() - started, 6)))
        result["duration_seconds"] = duration

        # 门槛判定只对**实际跑了的**套件做（--only 部分运行不判定未测指标）
        if result.get("not_enabled"):
            result["threshold_ok"] = False
            result["ok"] = False
        else:
            entry = _check_thresholds(thresholds, name)
            min_rate = Decimal(str(entry["min_pass_rate"]))
            max_duration = Decimal(str(entry["max_duration_seconds"]))
            # 误报率只在**该套件真的测它**时才作判定：规则驱动层（B4/B5）没有
            # "观测键"通道，其误报率结构上不可测——若仍拿一个恒 0 去比门槛，
            # 那个比较是恒真的假门。故由 manifest 显式声明 `measures_false_positive`，
            # 未测即**不冒充"误报率达标"**（登记而非沉默）。
            measures_fp = bool(entry["measures_false_positive"])
            if measures_fp:
                max_fp = Decimal(str(entry["max_false_positive_rate"]))
                fp_ok = result["false_positive_rate"] <= max_fp
            else:
                fp_ok = True
            result["false_positive_measured"] = measures_fp
            result["duration_ok"] = duration <= max_duration
            result["threshold_ok"] = (result["pass_rate"] >= min_rate and fp_ok
                                      and result["duration_ok"])
            result["ok"] = bool(result["ok"] and result["threshold_ok"])
        result["coverage"] = coverage.get(name)
        suites.append(result)

    passed = all(suite["ok"] for suite in suites) if suites else False
    return {
        "suites": suites,
        "passed": passed,
        "partial": bool(only),
        "not_enabled": [s["suite"] for s in suites if s.get("not_enabled")],
        "coverage": coverage,
    }


def render_text(result):
    """文本渲染（部分运行时声明未测指标）。"""
    lines = ["内置基准套件结果", ""]
    for suite in result["suites"]:
        if suite.get("not_enabled"):
            lines.append("[未启用] %s — %s" % (suite["suite"], suite["notes"]))
            continue
        duration = suite.get("duration_seconds")
        timing = "" if duration is None else "  耗时 %ss%s" % (
            duration, "" if suite.get("duration_ok", True) else "（超时长门槛）")
        lines.append("[%s] %s  通过 %d/%d  达标率 %s  误报率 %s%s  %s" % (
            "达标" if suite["ok"] else "未达标",
            suite["suite"], suite["passed"], suite["total"],
            suite["pass_rate"], suite["false_positive_rate"], timing, suite["notes"]))
        coverage = suite.get("coverage")
        if coverage:
            lines.append("    覆盖度: 形态 %s 中采样 %s（%s）"
                         % (coverage.get("forms_total"), coverage.get("forms_sampled"),
                            coverage.get("declaration")))
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
