"""基准对账语义的**单一实现源** + 样本套件（B1–B3）的**活体观测器**。

真值库测试与基准 runner **共用本模块的函数**——否则会出现"基准说达标、
测试说不过"的双口径漂移。

## 观测是活的，不是冻的（M4 关键）

真值库只存**输入 + 期望**（``input`` + ``expect_keys``），**不含观测结果**。
若把观测也冻进库，评测就退化成"比对两个冻结字典"——**引擎坏掉也照样全绿**，
那正是本项目最忌的假门。故观测一律由本模块 ``observe_*`` 在运行时实算：把用例
的内联输入喂给真引擎，取出实算结论。

## 结论键：字段名自带结论

对账单元是**结论键**（``"issue:L3:not_numeric:invalid"``、``"status:大白菜=up"``、
``"rows:9"``、``"cost:醋溜白菜=3.24"``）。键名**把结论编进名字**，取值恒为
``"ok"``。这样对账仍落在"字段集合"上（同一对账语义），但**值的变化会改变键名**：
若"跌"被误判成"涨"，键从 ``status:X=down`` 变成 ``status:X=up``，于是
"漏一个 + 多一个"同时暴露。

**为什么不能只把状态当值**：``{"status:大白菜": "up"}`` 与
``{"status:大白菜": "down"}`` 的**字段名集合相同**，集合对账看不见差异——
错误方向、误分类全部静默通过。键自带结论才让"值"参与对账。

**期望必须有独立来源**（探活前提，plan/03 §七）：B4 的期望锚定**冻结参数包**
（不读真值库），B1–B3 锚定**冻结真值库**（生成后冻结，引擎改动即失配）。

**严格双向**：观测多出的键也算不一致（漏报/误报都报）。故观测器只产出由用例
``input`` 指令（``observe_foods`` / ``observe_costs`` 一类）**明确要求**的键——
观测器行为是输入的纯函数，期望则是它产出的一次冻结快照。
"""

import os

from rcc import model
from rcc.alert import threshold as alert_mod
from rcc.engine import pipeline
from rcc.io import csv_import, snapshot

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 样本套件 → 观测器（B4/B5 是规则驱动层，不读真值库，故不在本表）
SUITE_OBSERVERS = {}

OK = "ok"


# ------------------------------------------------------------- 对账语义（单一源）

def confirmed_keys(observed):
    """观测结果里**被确认**的结论键集合（取值 ``ok`` 的键）。"""
    if not isinstance(observed, dict):
        return set()
    return {key for key, value in observed.items() if value == OK}


def observed_nonpass(observed):
    """从观测结果里抽出"非 pass 字段集合"。

    ``observed`` 是 ``{字段名: 状态}``；状态为 ``ok`` 的不计入。

    本函数与 :func:`confirmed_keys` 是同一判据的两面：结论键方案里取值恒为
    ``ok``（此时"非 pass 集合"为空，差异全部体现在**键的集合**上），而显式状态
    方案里字段名固定、状态承载结论。
    """
    if not isinstance(observed, dict):
        return set()
    return {key for key, value in observed.items() if value != OK}


def compare_nonpass(expected, observed):
    """对账：返回 ``{"missing": [...], "unexpected": [...], "match": bool}``。

    - ``missing``：期望出现但观测没出现（漏报 / 结论没被证实）；
    - ``unexpected``：观测出现但期望没有（误报 / 结论与冻结期望不符）；
    - ``match``：两者相等。
    """
    expected_set = set(expected)
    observed_set = set(observed)
    missing = sorted(expected_set - observed_set)
    unexpected = sorted(observed_set - expected_set)
    return {"missing": missing, "unexpected": unexpected,
            "match": not missing and not unexpected}


def expected_keys(record):
    """用例的冻结期望结论键。"""
    return list(record.get("expect_keys") or [])


def evaluate_case(suite, record, workdir):
    """跑一个真值用例：**活体观测** → 与冻结期望键对账。

    返回 ``{"id", "missing", "unexpected", "observed_count", "error", "match"}``。
    观测器抛错不炸整轮基准——记为该用例不一致并把原因带上（基准要报的是
    "未达标"，不是让读者去看 traceback）。
    """
    observer = SUITE_OBSERVERS[suite]
    error = None
    try:
        observed = observer(record, workdir)
    except Exception as exc:  # noqa: BLE001 - 基准要把失败如实回传为"未达标"
        observed = {}
        error = "%s: %s" % (type(exc).__name__, exc)

    live = confirmed_keys(observed)
    comparison = compare_nonpass(expected_keys(record), live)
    comparison["id"] = record.get("id")
    comparison["observed_count"] = len(live)
    comparison["unexpected_count"] = len(comparison["unexpected"])
    comparison["error"] = error
    if error:
        comparison["match"] = False
    return comparison


# ------------------------------------------------------------------ 通用小工具

def _write_text(workdir, name, text, encoding="utf-8"):
    """把内联输入落成临时件。

    写在**仓库树外**（同"验证产物不写仓库内 out/"纪律：仓库内 out/ 属忽略区，
    往那里写会"看着成功其实没写")。``encoding`` 供"非 UTF-8 进货单"用例造
    真实字节（只接受 UTF-8 是登记过的口径，必须有用例证明它真被拒绝）。
    """
    path = os.path.join(workdir, name)
    if encoding == "utf-8":
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    else:
        with open(path, "wb") as fh:
            fh.write(text.encode(encoding))
    return path


def input_failure_types():
    """基准视为"输入不可用/被门控"的异常类型集合。

    **只捕这些**，不捕 ``Exception``：把引擎的意外崩溃（如 ``AttributeError``）
    当成"期望的形态失败"会让真缺陷静默通过——观测器抛错必须变成该用例不一致
    （连同原因一起报），那才是基准该说的话。
    """
    from rcc.rules.params import ParamsError, ParamsInputRequired, ParamsPending

    return (ValueError, ParamsError, ParamsPending, ParamsInputRequired)


class _Args(object):
    """最小 args 替身（与 CLI 的 argparse.Namespace 同形）。"""

    def __init__(self, purchases, bom, params=None):
        self.purchases = purchases
        self.bom = bom
        self.params = params
        self.snapshots = []
        self.with_alert = False


def base_params():
    """随包冻结参数包。"""
    from rcc.rules.params import load_params

    return load_params()


def _params_with_overrides(workdir, overrides):
    """把参数包复制一份并施加覆盖，落成临时件（键序固定的确定性 JSON 形态）。"""
    import json

    data = base_params()
    for section, entries in sorted(overrides.items()):
        for name, entry in sorted(entries.items()):
            data[section][name].update(entry)
    path = os.path.join(workdir, "params-override.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return path


def snapshot_path(rel):
    """快照相对路径 → 绝对路径（真值库只存相对路径，跨机可复现）。"""
    return os.path.join(REPO_ROOT, rel.replace("/", os.sep))


# ------------------------------------------------------------ B1 import 观测

def observe_import(record, workdir):
    """B1：把内联进货单喂给**唯一分派点** ``csv_import.parse_purchases``，观测三态判定。

    产出的键：

    - ``form:accepted`` / ``form:rejected``（整份文件形态是否可用，恒有一个）；
    - ``issue:L<行号>:<异常代码>:<状态>``（**每一条**异常，双向严格）；
    - ``rows:<可用行数>``。
    """
    inp = record["input"]
    path = _write_text(workdir, "%s.csv" % record["id"], inp["purchases_csv"],
                       inp.get("purchases_encoding", "utf-8"))
    observed = {}
    try:
        parsed = csv_import.parse_purchases(path)
    except input_failure_types():
        observed["form:rejected"] = OK
        return observed

    observed["form:accepted"] = OK
    for issue in parsed["issues"]:
        observed["issue:L%s:%s:%s" % (issue.get("line"), issue.get("code"),
                                      issue.get("status"))] = OK
    observed["rows:%d" % len(parsed["rows"])] = OK
    return observed


# --------------------------------------------------------- B2 costcard 观测

def observe_costcard(record, workdir):
    """B2：内联 BOM + 进货单（+ 参数覆盖）喂给**端到端编排层**，观测成本卡。

    产出的键：

    - ``pipeline:ok`` / ``pipeline:failed``（整轮是否跑通，恒有一个）；
    - ``card:<菜品>:ok`` / ``card:<菜品>:excluded``（该菜是否出卡）；
    - ``issue:<异常代码>:<定位>``（**仅成本卡的行级代码**——进货单的异常不混入，
      同 K28 的行级/文件级不混用）；
    - ``cost:<菜品>=<成本>``（仅对 ``observe_costs`` 声明的菜品）。
    """
    import json

    inp = record["input"]
    purchases = _write_text(workdir, "%s.csv" % record["id"], inp["purchases_csv"])
    bom = _write_text(workdir, "%s.json" % record["id"], inp["bom_json"])
    params_path = None
    if inp.get("params_overrides"):
        params_path = _params_with_overrides(workdir, inp["params_overrides"])

    observed = {}
    try:
        result = pipeline.compute_full(_Args(purchases, bom, params_path))
    except input_failure_types():
        observed["pipeline:failed"] = OK
        return observed
    observed["pipeline:ok"] = OK

    cards = {card["dish"]: card for card in result["cards"]}
    for dish in json.loads(inp["bom_json"])["dishes"]:
        name = dish["name"]
        observed["card:%s:%s" % (name, "ok" if name in cards else "excluded")] = OK

    costcard_codes = (pipeline.ISSUE_YIELD_OUT_OF_RANGE, pipeline.ISSUE_QTY_INVALID)
    for issue in result.get("warnings") or []:
        if issue.get("code") in costcard_codes:
            observed["issue:%s:%s" % (issue.get("code"), issue.get("where"))] = OK

    for dish in inp.get("observe_costs") or []:
        if dish in cards:
            observed["cost:%s=%s" % (dish, cards[dish]["cost"])] = OK
        else:
            observed["cost:%s=excluded" % dish] = OK
    return observed


# ----------------------------------------------------------- B3 alert 观测

def observe_alert(record, workdir):
    """B3：用**冻结快照**跑预警口径，观测分类、汇总计数、排序与阈值标记。

    观测器**只产出用例声明要看的键**（严格双向：观测多出的键也算不一致）。三档开关：

    - ``guard/same_period``：两期退化成同一期时必须拒绝（只产出该键）；
    - ``observe_foods``：逐个食材的状态分类键 ``status:<食材>=<分类>``；
    - ``observe_summary``：跨食材的汇总键 ``count:<分类>=<条数>`` / ``total:<条数>``
      / ``order:<descending|not_descending>`` / ``flagged:<条数>``（阈值由参数包实算）。
    """
    inp = record["input"]
    old = snapshot.load_snapshot(snapshot_path(inp["old_snapshot"]))
    new = snapshot.load_snapshot(snapshot_path(inp["new_snapshot"]))

    if inp.get("same_period_guard"):
        from rcc.rules.params import effective_params

        observed = {}
        try:
            # 两期同一份快照：必须在动用菜品清单之前就拒绝（成本卡不参与该判定）
            pipeline.compute_alert([], old, old, effective_params("alert"),
                                   effective_params("cost"))
            observed["guard:same_period:not_rejected"] = OK
        except input_failure_types():
            observed["guard:same_period:rejected"] = OK
        return observed

    changes = alert_mod.diff_prices(old["prices"], new["prices"])
    by_name = {row["name"]: row for row in changes}
    observed = {}
    for name in inp.get("observe_foods") or []:
        row = by_name.get(name)
        observed["status:%s=%s" % (name, row["status"] if row else "absent")] = OK

    if not inp.get("observe_summary"):
        return observed

    counts = {}
    for row in changes:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    for status in sorted(counts):
        observed["count:%s=%d" % (status, counts[status])] = OK
    observed["total:%d" % len(changes)] = OK
    observed["order:%s" % ("descending" if _is_descending(changes) else "not_descending")] = OK

    threshold = model.to_decimal(base_params()["alert"]["threshold"]["value"])
    observed["flagged:%d" % len(alert_mod.flag(changes, threshold))] = OK
    return observed


def _is_descending(rows):
    """涨跌幅降序、无对比基准者（``change_rate is None``）垫底——排序规则的观测判据。

    只比较相邻两行的次序关系，**不做任何算术**（本模块不得出现第二份公式实现，
    见 ``tests/guards/test_formula_single_source.py``）。
    """
    seen_none = False
    last = None
    for row in rows:
        rate = row["change_rate"]
        if rate is None:
            seen_none = True
            continue
        if seen_none:
            return False
        if last is not None and rate > last:
            return False
        last = rate
    return True


SUITE_OBSERVERS.update({
    "import": observe_import,
    "costcard": observe_costcard,
    "alert": observe_alert,
})
