"""自检（源码态与冻结态通用）。

冻结态的价值在"离开开发机仍能证明自己完整"——所以核心断言是
**数据目录必须落在 exe 目录之内**（打包最常见的失效模式是"数据没随包走、
exe 回头读了开发机的仓库"，本地看着能跑、换机器就废）。
非冻结态该项返回 ``None`` 而非 FAIL，不让源码运行被误判。
"""

import os
import sys

from . import __version__
from .packaging import find_data_dir, frozen_data_is_inside_dist, is_frozen


def run_selftest():
    """跑自检，返回结果字典（含 ``ok`` 总判）。"""
    checks = []

    def add(name, ok, detail=""):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("version", True, __version__)
    add("frozen", True, str(is_frozen()))

    # 数据目录定位
    data_dir = None
    try:
        data_dir = find_data_dir()
        add("data_dir", os.path.isdir(data_dir), data_dir)
    except Exception as exc:  # noqa: BLE001 - 自检要把失败如实回传
        add("data_dir", False, "%s: %s" % (type(exc).__name__, exc))

    # 冻结态专属：数据目录必须落在 exe 目录之内
    if is_frozen():
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        inside = frozen_data_is_inside_dist(exe_dir, data_dir or "")
        add("frozen_data_inside_dist", bool(inside),
            "exe=%s data=%s" % (exe_dir, data_dir))

    # 参数包可加载 + 生效条目数 > 0
    param_count = 0
    try:
        from .rules.params import effective_params, load_params

        data = load_params()
        effective_params("cost")
        param_count = sum(len(data.get(section, {}))
                          for section in ("yield_rates", "pricing", "alert"))
        add("params_loadable", param_count > 0, "参数条目 %d" % param_count)
    except Exception as exc:  # noqa: BLE001
        add("params_loadable", False, "%s: %s" % (type(exc).__name__, exc))

    # 核心公式通路可跑（探针数值取自参数包，**不手写业务数值**——plan/02 禁
    # 第二份口径，含注释与示例数值；手写示例值即等于在代码里长了第二份真相）
    try:
        from decimal import Decimal

        from .model import MONEY_EXP, to_decimal
        from .rules import formulas

        data = load_params()
        cost_params = effective_params("cost")
        probe_name = sorted(cost_params)[0]
        rate = to_decimal(cost_params[probe_name]["value"])
        purchase = Decimal(1)
        net = formulas.net_unit_price(purchase, rate)
        # F1 方向纪律：净料率 ∈ (0,1] ⇒ 净料单价必然 ≥ 毛料单价
        direction_ok = net >= purchase
        # F3→F4 往返：建议售价先量化，据此反算的实际毛利率应回到目标（误差 ≤ 量化一步）
        target = to_decimal(data["pricing"]["target_margin"]["value"])
        price = formulas.suggested_price(purchase, target)
        margin_back = formulas.actual_margin(price, purchase)
        roundtrip_ok = abs(margin_back - target) <= MONEY_EXP
        add("formulas_ok", bool(direction_ok and roundtrip_ok),
            "净料单价≥毛料单价=%s 反算毛利率回到目标=%s（探针取自参数包条目 %s）"
            % (direction_ok, roundtrip_ok, probe_name))
    except Exception as exc:  # noqa: BLE001
        add("formulas_ok", False, "%s: %s" % (type(exc).__name__, exc))

    return {
        "version": __version__,
        "frozen": is_frozen(),
        "data_dir": data_dir,
        "param_count": param_count,
        "checks": checks,
        "ok": all(check["ok"] for check in checks),
    }
