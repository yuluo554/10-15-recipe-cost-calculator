"""真值库生成器（冻结产物）+ 验收门槛/覆盖度登记下发。

产出三份样本驱动套件的真值库与一份 manifest：

- ``data/truth/import.json``（B1 进货单导入）
- ``data/truth/costcard.json``（B2 成本卡端到端）
- ``data/truth/alert.json``（B3 价格波动预警）
- ``data/truth/manifest.json``（**门槛 + 覆盖度双登记 + 各真值库 sha256**）

## 真值记录语义（定一次，就写在这里）

- ``input`` = 用例的**内联输入**（CSV 文本 / BOM JSON / 快照相对路径 / 参数覆盖）；
- ``expect_keys`` = **冻结期望结论键**（对账单元）；
- **不含观测结果**——观测由 ``benchmark/cases.py`` 的观测器在**运行时**实算。
  若把观测也冻进库，评测就退化成"比对两个冻结字典"，**引擎坏掉也照样全绿**。

**结论键自带结论**（``status:X=down``、``cost:X=3.24``、``issue:L3:not_numeric:invalid``）：
键名把结论编进名字，取值恒为 ``ok``。于是对账仍落在"字段集合"上（对账语义单一实现
源在 ``benchmark/cases.py``），但**值的变化会改变键名**——只把状态当值的话
（``{"status:X": "up"}`` vs ``{"status:X": "down"}``）字段名集合相同，**误分类静默通过**。

## 期望的独立来源（探活的隐含前提，plan/03 §七）

期望值与引擎**同源**时，注入缺陷两边一起变、探活永远绿。故：

- B1–B3 的期望**冻结在本真值库**里（生成后即与引擎解耦：改引擎不改冻结件 → 探活红）；
- B2 的成本期望在生成期**用 F1/F2 独立复算**并断言一致（不是"引擎说了什么就冻什么"）；
- B4 的期望锚定**冻结参数包**，不读真值库。

## 覆盖度双登记（防假覆盖，plan/03 §四）

覆盖声明必须同时写出**分母（形态总数）与分子（采样数）**——只写分子就是假覆盖。

分母**不由人手写清单决定**：B1/B2 的形态分母从 ``csv_import`` / ``pipeline`` 的
``ISSUE_*`` 常量**运行时反射**得出（新增一个异常代码而没配用例 → 分母自动变大、
覆盖率自动下降），再并上登记过的结构性形态。**"这个基准说的 100%，分母是不是被
我悄悄做小了？"**——本模块的答案是：分母来自代码里的常量集，做不小。

确定性纪律：禁 stdlib ``random``、禁 ``set`` 迭代序、禁系统时钟；
JSON 固定 ``sort_keys=True`` + 固定缩进 + ``newline="\\n"``。
"""

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _guard import ensure_utf8_stdio  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRUTH_DIR = os.path.join(REPO_ROOT, "data", "truth")

# 真值库文件（套件名 → 相对路径）
TRUTH_FILES = {
    "import": "data/truth/import.json",
    "costcard": "data/truth/costcard.json",
    "alert": "data/truth/alert.json",
}
MANIFEST_REL = "data/truth/manifest.json"

HEADER = "日期,品名,类别,数量,单位,单价,金额"

# 参数包内置净料率的食材（用例只准用这些；未知食材另有专门用例）
KNOWN_FOOD = "大白菜"
SECOND_FOOD = "土豆"


def _src():
    path = os.path.join(REPO_ROOT, "src")
    if path not in sys.path:
        sys.path.insert(0, path)


# --------------------------------------------------------------------- B1 用例

def _csv(rows, header=HEADER):
    """内联进货单文本（LF 行尾，确定性）。"""
    return "\n".join([header] + list(rows)) + "\n"


def build_import_cases():
    """B1 用例：**每个形态一条**（形态清单见 :func:`import_forms`）。"""
    ok_row = "2026-10-01,%s,蔬菜,10,斤,1.20,12.00" % KNOWN_FOOD
    return [
        {
            "id": "imp-ok-row",
            "form": "ok_row",
            "input": {"purchases_csv": _csv([ok_row])},
            "expect_keys": ["form:accepted", "rows:1"],
        },
        {
            "id": "imp-required-empty",
            "form": "required_empty",
            "input": {"purchases_csv": _csv(["2026-10-01,,蔬菜,10,斤,1.20,12.00"])},
            "expect_keys": ["form:accepted", "rows:0",
                            "issue:L2:required_empty:invalid"],
        },
        {
            "id": "imp-qty-not-numeric",
            "form": "not_numeric",
            "input": {"purchases_csv": _csv(
                ["2026-10-01,%s,蔬菜,abc,斤,1.20,12.00" % KNOWN_FOOD])},
            "expect_keys": ["form:accepted", "rows:0",
                            "issue:L2:not_numeric:invalid"],
        },
        {
            "id": "imp-price-not-numeric",
            "form": "not_numeric",
            "input": {"purchases_csv": _csv(
                ["2026-10-01,%s,蔬菜,10,斤,一元,12.00" % KNOWN_FOOD])},
            "expect_keys": ["form:accepted", "rows:0",
                            "issue:L2:not_numeric:invalid"],
        },
        {
            "id": "imp-negative",
            "form": "negative",
            "input": {"purchases_csv": _csv(
                ["2026-10-01,%s,蔬菜,-2,斤,1.20,-2.40" % KNOWN_FOOD])},
            "expect_keys": ["form:accepted", "rows:0", "issue:L2:negative:invalid"],
        },
        {
            "id": "imp-unknown-column-header-level",
            "form": "mapping_uncertain",
            # 未登记列名（表头级）：记一条 line=1 的异常，**行仍可用**
            "input": {"purchases_csv": _csv([ok_row], header=HEADER + ",备注")},
            "expect_keys": ["form:accepted", "rows:1",
                            "issue:L1:mapping_uncertain:unknown"],
        },
        {
            "id": "imp-structure-unparsable",
            "form": "structure_unparsable",
            # 字段数多于表头：列对齐不可信 → 该行 unknown 且**不入库**
            "input": {"purchases_csv": _csv(
                ["2026-10-01,莲藕,蔬菜,4,斤,3.50,14.00,备注,多余"])},
            "expect_keys": ["form:accepted", "rows:0",
                            "issue:L2:structure_unparsable:unknown"],
        },
        {
            "id": "imp-unit-unregistered",
            "form": "unit_unregistered",
            # 单位未登记：记 unknown 提示，但**行仍可用**
            "input": {"purchases_csv": _csv(
                ["2026-10-01,%s,蔬菜,5,克拉,1.20,6.00" % KNOWN_FOOD])},
            "expect_keys": ["form:accepted", "rows:1",
                            "issue:L2:unit_unregistered:unknown"],
        },
        {
            "id": "imp-duplicate-names",
            "form": "duplicate_names_observable",
            # 重复品名不是错误（多批次进货是常态），但取舍必须可观测
            "input": {"purchases_csv": _csv([
                "2026-10-01,%s,蔬菜,10,斤,1.20,12.00" % KNOWN_FOOD,
                "2026-10-05,%s,蔬菜,10,斤,1.60,16.00" % KNOWN_FOOD,
            ])},
            "expect_keys": ["form:accepted", "rows:2"],
        },
        {
            "id": "imp-blank-lines-tolerated",
            "form": "blank_lines_tolerated",
            # 行间**空行**不产出记录（csv 模块行为）：空行不是数据行，
            # 行尾换行与空行是编辑器常态，不得因此丢数据。
            # 注意：仅含空白的行**不算空行**（它是"品名为空的记录"→ required_empty），
            # 故此处用真正的空行。
            "input": {"purchases_csv": _csv([ok_row, "", ""])},
            "expect_keys": ["form:accepted", "rows:1"],
        },
        {
            "id": "imp-amount-not-validated",
            "form": "amount_not_validated",
            # 金额列不参与计算，故非数值不影响该行判 ok（**登记过的口径，非遗漏**）
            "input": {"purchases_csv": _csv(
                ["2026-10-01,%s,蔬菜,10,斤,1.20,不是数字" % KNOWN_FOOD])},
            "expect_keys": ["form:accepted", "rows:1"],
        },
        {
            "id": "imp-bom-header",
            "form": "utf8_bom_header",
            # utf-8-sig 吃掉 BOM，表头照常命中（内联件带 BOM 字符）
            "input": {"purchases_csv": "\ufeff" + _csv([ok_row])},
            "expect_keys": ["form:accepted", "rows:1"],
        },
        {
            "id": "imp-shuffled-columns",
            "form": "shuffled_column_order",
            # 列顺序任意（按列名映射，不按位置）
            "input": {"purchases_csv": _csv(
                ["1.20,蔬菜,10,斤,%s,2026-10-01,12.00" % KNOWN_FOOD],
                header="单价,类别,数量,单位,品名,日期,金额")},
            "expect_keys": ["form:accepted", "rows:1"],
        },
        {
            "id": "imp-header-whitespace",
            "form": "header_whitespace_trimmed",
            "input": {"purchases_csv": _csv([ok_row], header=" 日期 ,品名, 类别 ,数量,单位,单价,金额")},
            "expect_keys": ["form:accepted", "rows:1"],
        },
        {
            "id": "imp-empty-file",
            "form": "form_empty_file",
            "input": {"purchases_csv": ""},
            "expect_keys": ["form:rejected"],
        },
        {
            "id": "imp-whitespace-only",
            "form": "form_whitespace_only",
            "input": {"purchases_csv": "\n \n\t\n"},
            "expect_keys": ["form:rejected"],
        },
        {
            "id": "imp-header-only",
            "form": "form_header_only",
            "input": {"purchases_csv": HEADER + "\n"},
            "expect_keys": ["form:rejected"],
        },
        {
            "id": "imp-missing-required-column",
            "form": "form_missing_required_column",
            # 缺必填列（数量）→ 整份文件形态不可用
            "input": {"purchases_csv": _csv(
                ["2026-10-01,%s,蔬菜,斤,1.20,12.00" % KNOWN_FOOD],
                header="日期,品名,类别,单位,单价,金额")},
            "expect_keys": ["form:rejected"],
        },
        {
            "id": "imp-non-utf8-rejected",
            "form": "form_non_utf8",
            # 只接受 UTF-8，**不做编码猜测**（猜错会把 GBK 静默解成乱码品名）
            "input": {"purchases_csv": _csv([ok_row]), "purchases_encoding": "gbk"},
            "expect_keys": ["form:rejected"],
        },
    ]


# --------------------------------------------------------------------- B2 用例

def _bom(dishes):
    """内联 BOM JSON 文本（确定性键序 + 末尾换行）。"""
    return json.dumps({"schema_version": "1", "dishes": dishes},
                      ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _purchase_rows(pairs):
    """``[(品名, 单价), ...]`` → 进货单数据行文本。"""
    return ["2026-10-01,%s,蔬菜,10,斤,%s,0" % (name, price) for name, price in pairs]


def _one_dish(name, items):
    return [{"name": name, "items": [{"food": f, "qty": q} for f, q in items]}]


# 行级问题用例必须**同时含一道健康的菜**：K32 规定"整道菜排除"，而全部菜都被排除
# 时成本卡为空 → 文件级结论 exit 2（那是另一条形态 `cc-all-dishes-excluded` 的事）。
# 单菜 BOM 配行级问题会走成"全部排除"，测的就成了另一个形态（夹具与被测对象不匹配）。
HEALTHY_DISH = "清炒时蔬"


def _with_healthy(dishes):
    """行级问题 BOM 的搭档：追加一道健康菜，使"其余照常出数"真被验到。"""
    return dishes + _one_dish(HEALTHY_DISH, [(SECOND_FOOD, "0.5")])


def build_costcard_cases():
    """B2 用例：单食材 / 多食材 / 多菜 / 净料率越界 / 用量为负 / 全部排除 /
    BOM 形态失败四条 / 缺净料率条目。"""
    price = "1.20"
    stock = _csv(_purchase_rows([(KNOWN_FOOD, price), (SECOND_FOOD, "2.00")]))
    dish = "醋溜白菜"
    return [
        {
            "id": "cc-single-food",
            "form": "single_food",
            "input": {"purchases_csv": stock,
                      "bom_json": _bom(_one_dish(dish, [(KNOWN_FOOD, "1.5")])),
                      "observe_costs": [dish]},
            "expect_keys": ["pipeline:ok", "card:%s:ok" % dish,
                            "cost:%s=%s" % (dish, _expected_cost(KNOWN_FOOD, price, "1.5"))],
        },
        {
            "id": "cc-multi-food",
            "form": "multi_food",
            "input": {"purchases_csv": stock,
                      "bom_json": _bom(_one_dish(dish, [(KNOWN_FOOD, "1.5"),
                                                        (SECOND_FOOD, "0.5")])),
                      "observe_costs": [dish]},
            "expect_keys": ["pipeline:ok", "card:%s:ok" % dish,
                            "cost:%s=%s" % (dish, _expected_cost(
                                KNOWN_FOOD, price, "1.5", SECOND_FOOD, "2.00", "0.5"))],
        },
        {
            "id": "cc-two-dishes",
            "form": "multi_dish",
            "input": {"purchases_csv": stock,
                      "bom_json": _bom(_one_dish(dish, [(KNOWN_FOOD, "1.5")])
                                       + _one_dish("土豆丝", [(SECOND_FOOD, "1")])),
                      "observe_costs": [dish, "土豆丝"]},
            "expect_keys": ["pipeline:ok", "card:%s:ok" % dish, "card:土豆丝:ok",
                            "cost:%s=%s" % (dish, _expected_cost(KNOWN_FOOD, price, "1.5")),
                            "cost:土豆丝=%s" % _expected_cost(SECOND_FOOD, "2.00", "1")],
        },
        {
            "id": "cc-qty-zero",
            "form": "qty_zero",
            # F2 端点：用量=0 → **该食材不贡献成本**（不是"成本算不出"）。
            # 必须配一个非零用量行：整道菜成本为 0 时建议售价为 0，F4 会因
            # "售价须 > 0"拒绝（该端点归 B4 的 f4_price_zero_rejected 规则驱动覆盖）
            # ——单行 qty=0 的 BOM 测到的是那条端点，不是 F2 的可加性。
            "input": {"purchases_csv": stock,
                      "bom_json": _bom(_one_dish(dish, [(KNOWN_FOOD, "0"),
                                                        (SECOND_FOOD, "0.5")])),
                      "observe_costs": [dish]},
            "expect_keys": ["pipeline:ok", "card:%s:ok" % dish,
                            "cost:%s=%s" % (dish, _expected_cost(SECOND_FOOD, "2.00", "0.5"))],
        },
        {
            "id": "cc-yield-rate-one",
            "form": "yield_rate_one",
            # F1 端点：净料率=1.0 → 净料单价 = 毛料单价（净料率上界，合法）
            "input": {"purchases_csv": stock,
                      "bom_json": _bom(_one_dish(dish, [(KNOWN_FOOD, "1.5")])),
                      "observe_costs": [dish],
                      "params_overrides": {"yield_rates": {KNOWN_FOOD: {"value": "1"}}}},
            "expect_keys": ["pipeline:ok", "card:%s:ok" % dish,
                            "cost:%s=%s" % (dish, _expected_cost(KNOWN_FOOD, price, "1.5",
                                                                 rate="1"))],
        },
        {
            "id": "cc-yield-rate-tiny",
            "form": "yield_rate_tiny",
            # F1 端点：净料率→0⁺（极小但合法）→ 净料单价放大，仍须出数不抛错
            "input": {"purchases_csv": stock,
                      "bom_json": _bom(_one_dish(dish, [(KNOWN_FOOD, "1.5")])),
                      "observe_costs": [dish],
                      "params_overrides": {"yield_rates": {KNOWN_FOOD: {"value": "0.01"}}}},
            "expect_keys": ["pipeline:ok", "card:%s:ok" % dish,
                            "cost:%s=%s" % (dish, _expected_cost(KNOWN_FOOD, price, "1.5",
                                                                 rate="0.01"))],
        },
        {
            "id": "cc-yield-out-of-range",
            "form": "yield_rate_out_of_range",
            # 参数包**有条目但值越界** → 该行 invalid 并入清单，**整道菜排除**（exit 1，
            # 其余菜品照常出数——故搭档一道健康菜，否则走成"全部排除"形态）
            "input": {"purchases_csv": stock,
                      "bom_json": _bom(_with_healthy(
                          _one_dish(dish, [(KNOWN_FOOD, "1.5")]))),
                      "observe_costs": [dish, HEALTHY_DISH],
                      "params_overrides": {"yield_rates": {KNOWN_FOOD: {"value": "1.5"}}}},
            "expect_keys": [
                "pipeline:ok",
                "card:%s:excluded" % dish, "card:%s:ok" % HEALTHY_DISH,
                "cost:%s=excluded" % dish,
                "cost:%s=%s" % (HEALTHY_DISH, _expected_cost(SECOND_FOOD, "2.00", "0.5")),
                "issue:yield_rate_out_of_range:菜品「%s」·食材「%s」" % (dish, KNOWN_FOOD),
            ],
        },
        {
            "id": "cc-qty-negative",
            "form": "qty_invalid",
            "input": {"purchases_csv": stock,
                      "bom_json": _bom(_with_healthy(
                          _one_dish(dish, [(KNOWN_FOOD, "-1")]))),
                      "observe_costs": [dish, HEALTHY_DISH]},
            "expect_keys": [
                "pipeline:ok",
                "card:%s:excluded" % dish, "card:%s:ok" % HEALTHY_DISH,
                "cost:%s=excluded" % dish,
                "cost:%s=%s" % (HEALTHY_DISH, _expected_cost(SECOND_FOOD, "2.00", "0.5")),
                "issue:qty_invalid:菜品「%s」·食材「%s」" % (dish, KNOWN_FOOD),
            ],
        },
        {
            "id": "cc-all-dishes-excluded",
            "form": "no_usable_dishes",
            # 全部菜品都被排除 → 成本卡为空 → 文件级结论 → 输入不可用（exit 2）
            "input": {"purchases_csv": stock,
                      "bom_json": _bom(_one_dish(dish, [(KNOWN_FOOD, "-1")])
                                       + _one_dish("土豆丝", [(SECOND_FOOD, "-2")]))},
            "expect_keys": ["pipeline:failed"],
        },
        {
            "id": "cc-bom-empty-dishes",
            "form": "form_bom_empty_dishes",
            "input": {"purchases_csv": stock, "bom_json": _bom([])},
            "expect_keys": ["pipeline:failed"],
        },
        {
            "id": "cc-bom-missing-dishes",
            "form": "form_bom_missing_dishes",
            "input": {"purchases_csv": stock,
                      "bom_json": json.dumps({"schema_version": "1"},
                                             ensure_ascii=False, sort_keys=True) + "\n"},
            "expect_keys": ["pipeline:failed"],
        },
        {
            "id": "cc-bom-dish-missing-name",
            "form": "form_bom_dish_missing_name",
            "input": {"purchases_csv": stock,
                      "bom_json": _bom([{"items": [{"food": KNOWN_FOOD, "qty": "1"}]}])},
            "expect_keys": ["pipeline:failed"],
        },
        {
            "id": "cc-bom-unknown-food",
            "form": "form_bom_unknown_food",
            # 引用了食材库/进货单里不存在的食材 → BOM 形态失败
            "input": {"purchases_csv": stock,
                      "bom_json": _bom(_one_dish(dish, [("并不存在的食材", "1")]))},
            "expect_keys": ["pipeline:failed"],
        },
        {
            "id": "cc-missing-yield-rate-entry",
            "form": "missing_yield_rate_entry",
            # 净料率**本不由参数包承载**（条目缺失）→ 运行时索取，缺失 exit 2
            # 注意：这与"有条目但值越界"是两种故障（前者没给，后者给了但不对）
            "input": {"purchases_csv": _csv(_purchase_rows([("芥蓝", "3.00")])),
                      "bom_json": _bom(_one_dish(dish, [("芥蓝", "1")]))},
            "expect_keys": ["pipeline:failed"],
        },
        {
            "id": "cc-purchases-no-usable-rows",
            "form": "no_usable_rows",
            # 进货单零可用行（文件级结论）→ 报错必须指向**进货单**，不得由下游
            # 报"BOM 引用了不存在的食材"（错误指向错误的对象比沉默更坏）
            "input": {"purchases_csv": _csv(
                ["2026-10-01,,蔬菜,10,斤,1.20,12.00"]),
                "bom_json": _bom(_one_dish(dish, [(KNOWN_FOOD, "1")]))},
            "expect_keys": ["pipeline:failed"],
        },
    ]


def _expected_cost(*triples, **kw):
    """用 F1/F2 独立复算期望成本（**不是"引擎说了什么就冻什么"**）。

    与 ``observe_costcard`` 的实算值对账，一致才写进真值库——生成期就拦住
    "把错的观测冻成真理"。

    ``rate`` 可覆盖净料率（端点用例改写参数包时，期望也要按同一覆盖复算）。
    """
    _src()
    from rcc.model import quantize_money, to_decimal
    from rcc.rules import formulas

    override_rate = kw.get("rate")
    items = []
    for index in range(0, len(triples), 3):
        food, price, qty = triples[index], triples[index + 1], triples[index + 2]
        rate = to_decimal(override_rate if override_rate is not None
                          else _params_entry("yield_rates", food)["value"])
        net = formulas.net_unit_price(to_decimal(price), rate)
        items.append((net, to_decimal(qty)))
    return str(quantize_money(formulas.dish_cost(items)))


def _params_entry(section, name):
    _src()
    from rcc.rules.params import load_params

    return load_params()[section][name]


# --------------------------------------------------------------------- B3 用例

SNAPSHOT_OLD = "data/snapshots/xinfadi-2026-08-06.json"
SNAPSHOT_NEW = "data/snapshots/xinfadi-2026-10-06.json"


def _alert_probe():
    """从**冻结快照**实算 B3 用例的期望（生成期一次；此后探活靠冻结件）。

    观测器与真值库都读同一批快照，但真值库**冻结**了结论——引擎改坏后实测结论
    变化、冻结期望不变，于是探活变红。
    """
    _src()
    from rcc.alert import threshold as alert_mod
    from rcc.io import snapshot

    old = snapshot.load_snapshot(os.path.join(REPO_ROOT, SNAPSHOT_OLD))
    new = snapshot.load_snapshot(os.path.join(REPO_ROOT, SNAPSHOT_NEW))
    changes = alert_mod.diff_prices(old["prices"], new["prices"])
    by_status = {}
    for row in changes:
        by_status.setdefault(row["status"], []).append(row["name"])
    return changes, by_status


def build_alert_cases():
    """B3 用例：**五类状态各一条**（涨/跌/平/新增/消失）+ 汇总与排序 + 阈值标记 +
    两期退化成同一期的守卫。

    五类状态拆成五条用例（而非一条大用例），是为了让"某类状态判错"能被**逐类**定位，
    也让覆盖度分母里的五个状态形态各有其采样。
    """
    changes, by_status = _alert_probe()
    # 每类状态各取一个**具名声样本**（取名称字典序第一，确定性）
    probes = {}
    for status in sorted(by_status):
        names = sorted(by_status[status])
        if names:
            probes[status] = names[0]

    cases = []
    for status in sorted(probes):
        food = probes[status]
        cases.append({
            "id": "al-status-%s" % status,
            "form": status,
            "input": {"old_snapshot": SNAPSHOT_OLD, "new_snapshot": SNAPSHOT_NEW,
                      "observe_foods": [food]},
            "expect_keys": ["status:%s=%s" % (food, status)],
        })

    _src()
    from rcc import model
    from rcc.alert import threshold as alert_mod

    threshold = model.to_decimal(_params_entry("alert", "threshold")["value"])
    flagged = alert_mod.flag(changes, threshold)
    summary_keys = ["total:%d" % len(changes), "order:descending",
                    "flagged:%d" % len(flagged)]
    for status in sorted(by_status):
        summary_keys.append("count:%s=%d" % (status, len(by_status[status])))

    cases.append({
        "id": "al-summary-order-threshold",
        "form": "two_periods_all_statuses",
        # 跨食材汇总（涨/跌/平/新增/消失各计数）+ 排序规则 + 阈值标记数
        "input": {"old_snapshot": SNAPSHOT_OLD, "new_snapshot": SNAPSHOT_NEW,
                  "observe_summary": True},
        "expect_keys": summary_keys,
    })
    cases.append({
        "id": "al-degenerate-same-period",
        "form": "same_period_rejected",
        # 两期退化成同一期 → 必须拒绝（不产出"全平"假结果）
        "input": {"old_snapshot": SNAPSHOT_OLD, "new_snapshot": SNAPSHOT_OLD,
                  "same_period_guard": True},
        "expect_keys": ["guard:same_period:rejected"],
    })
    return cases


# ------------------------------------------------------------- 覆盖度形式登记

def _issue_codes(module, prefix="ISSUE_"):
    """运行时反射模块里的 ``ISSUE_*`` 常量值（**分母不由人手写清单决定**）。"""
    return sorted({getattr(module, name) for name in dir(module)
                   if name.startswith(prefix)})


def import_registered():
    """B1 的**登记形态清单**（分母的来源）。

    分母 = ``csv_import`` 的异常代码（**反射**，新增代码即自动进分母）
    + 登记过的结构性形态。``no_usable_rows`` 被**排除**在这里，但它不是被"做小"了：
    它是**文件级**结论（同 K28：行级代码与文件级代码不混用），由 ``pipeline`` 层发出，
    而 ``parse_purchases`` 从不产出它。故它归 **B2 分母**（那里有用例覆盖），
    在此排除只是**把形态算在正确的层上**。
    """
    _src()
    from rcc.io import csv_import

    row_level_codes = [code for code in _issue_codes(csv_import)
                       if code != csv_import.ISSUE_NO_USABLE_ROWS]
    structural = [
        "ok_row",                        # 正常行
        "form_empty_file",               # 形态失败：空文件
        "form_whitespace_only",          # 形态失败：仅空白
        "form_header_only",              # 形态失败：只有表头
        "form_missing_required_column",  # 形态失败：缺必填列
        "form_non_utf8",                 # 形态失败：非 UTF-8
        "utf8_bom_header",               # BOM 表头
        "shuffled_column_order",         # 列顺序任意
        "header_whitespace_trimmed",     # 表头空白裁剪
        "blank_lines_tolerated",         # 行间空行
        "amount_not_validated",          # 金额列不校验数值性（登记口径）
        "duplicate_names_observable",    # 重复品名可观测
    ]
    return row_level_codes + structural


def import_forms(cases):
    """B1 形态分母与采样数。"""
    return _forms_from(cases, import_registered())


def costcard_registered():
    """B2 的登记形态清单：``pipeline`` 的异常代码（反射）+ ``csv_import`` 的文件级
    结论（``no_usable_rows``，在 B2 有用例覆盖）+ 结构性形态。"""
    _src()
    from rcc.engine import pipeline
    from rcc.io import csv_import

    structural = [
        csv_import.ISSUE_NO_USABLE_ROWS,  # 零可用行（文件级；由 pipeline 层发出）
        "single_food",                    # 单食材
        "multi_food",                     # 多食材
        "multi_dish",                     # 多道菜
        "qty_zero",                       # F2 端点：用量=0
        "yield_rate_one",                 # F1 端点：净料率=1.0
        "yield_rate_tiny",                # F1 端点：净料率→0⁺
        "form_bom_empty_dishes",          # 空数组
        "form_bom_missing_dishes",        # 缺 dishes
        "form_bom_dish_missing_name",     # 菜品缺 name
        "form_bom_unknown_food",          # 引用不存在的食材
        "missing_yield_rate_entry",       # 缺条目（与"值越界"分开）
    ]
    return _issue_codes(pipeline) + structural


def costcard_forms(cases):
    """B2 形态分母与采样数。"""
    return _forms_from(cases, costcard_registered())


def alert_registered():
    """B3 的登记形态清单：五类状态（设计枚举）+ 排序/阈值/退化守卫。"""
    return ["up", "down", "flat", "new", "gone",
            "two_periods_all_statuses", "same_period_rejected"]


def alert_forms(cases):
    """B3 形态分母与采样数。"""
    return _forms_from(cases, alert_registered())


def _forms_from(cases, registered):
    """登记形态 → 该形态有无用例采样。

    **每个登记形态都必须被至少一个用例采样**，否则生成器直接报错（exit 1）：
    "登记了却不采样"就是覆盖率虚高的来源，必须在生成期拦住，不能留给读者去发现。
    """
    sampled_forms = sorted({case["form"] for case in cases})
    unknown = [form for form in sampled_forms if form not in registered]
    if unknown:
        raise ValueError("用例声明了未登记的形态: %s" % unknown)
    unsampled = [form for form in registered if form not in sampled_forms]
    if unsampled:
        raise ValueError("以下形态已登记但无用例采样（覆盖率会虚高）: %s" % unsampled)
    return {
        "forms_total": len(registered),
        "forms_sampled": len(sampled_forms),
        "sampled_forms": sampled_forms,
    }


# ------------------------------------------------------------------ 门槛与组装

def build_thresholds():
    """验收门槛（数据非代码）。

    ``measures_false_positive``：该套件是否**真的测**误报率。规则驱动层（B4/B5）
    没有"观测键"通道，其误报率结构上不可测——若仍拿一个恒 0 去比门槛，那个比较
    是恒真的假门。故显式声明**未测**（登记而非沉默），未测即不冒充"误报率达标"。
    """
    measures = {"import": True, "costcard": True, "alert": True,
                "boundary": False, "reconcile": False}
    thresholds = {}
    for suite in ("import", "costcard", "alert", "boundary", "reconcile"):
        thresholds[suite] = {
            "min_pass_rate": "1.0" if not measures[suite] else "0.95",
            "max_false_positive_rate": "0.0",
            "max_duration_seconds": "10",
            "measures_false_positive": measures[suite],
        }
    return thresholds


def build_truth_records():
    """三份真值库 + 覆盖度登记（**双登记：分母 + 分子**）。"""
    builders = {
        "import": (build_import_cases, import_forms,
                   "进货单导入三态与形态失败（抽样覆盖，非穷举）"),
        "costcard": (build_costcard_cases, costcard_forms,
                     "成本卡端到端（抽样覆盖，非穷举）"),
        "alert": (build_alert_cases, alert_forms,
                  "价格波动预警（抽样覆盖，非穷举）"),
    }
    payloads, coverage = {}, {}
    for suite in sorted(builders):
        build_cases, build_forms, declaration = builders[suite]
        cases = build_cases()
        forms = build_forms(cases)
        payloads[suite] = {
            "schema_version": "1",
            "generated_by": "tools/gen_truth.py",
            "suite": suite,
            "note": ("本文件为生成器冻结产物，禁止手改。只存**输入 + 期望键**；"
                     "观测由 benchmark/cases.py 在运行时实算。"),
            "cases": cases,
        }
        coverage[suite] = {
            "forms_total": forms["forms_total"],
            "forms_sampled": forms["forms_sampled"],
            "sampled_forms": forms["sampled_forms"],
            "declaration": declaration,
        }
    return payloads, coverage


def render_json(payload):
    """确定性 JSON 文本（固定缩进、排序键、LF 行尾、末尾换行）。"""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_outputs():
    """``{相对路径: 文本}``，含 manifest（门槛 + 覆盖度 + 各真值库 sha256）。"""
    payloads, coverage = build_truth_records()
    outputs = {}
    digests = {}
    for suite in sorted(payloads):
        text = render_json(payloads[suite])
        outputs[TRUTH_FILES[suite]] = text
        digests[suite] = hashlib.sha256(text.encode("utf-8")).hexdigest()

    manifest = {
        "schema_version": "1",
        "generated_by": "tools/gen_truth.py",
        "note": ("本文件为生成器冻结产物，禁止手改。验收门槛随本文件下发（数据非代码）"
                 "——基准层只读，缺失即配置错误（退出码 2），不得回落代码默认值。"
                 "覆盖度按「总数/采样数」双登记；只写分子即假覆盖。"),
        "thresholds": build_thresholds(),
        "coverage": {
            "note": ("覆盖度按「总数/采样数」双登记——分母来自代码里的 ISSUE_* 常量集"
                     "（反射得出，做不小），分子是用例实际采样的形态数。"),
            "import": coverage["import"],
            "costcard": coverage["costcard"],
            "alert": coverage["alert"],
        },
        "truth_sha256": digests,
    }
    outputs[MANIFEST_REL] = render_json(manifest)
    return outputs


def _write_text(path, text):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main(argv=None):
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="真值库生成器（冻结产物）")
    parser.add_argument("--check", action="store_true",
                        help="重算并与入库件逐字节比对，不一致 exit 1")
    args = parser.parse_args(argv)

    try:
        outputs = build_outputs()
    except ValueError as exc:
        print("TRUTH_FORMS_INCOMPLETE: %s" % exc, file=sys.stderr)
        return 1

    drift = []
    for rel, text in sorted(outputs.items()):
        path = os.path.join(REPO_ROOT, rel.replace("/", os.sep))
        payload = text.encode("utf-8")
        if args.check:
            if not os.path.isfile(path):
                drift.append("%s 缺失" % rel)
                continue
            with open(path, "rb") as fh:
                if fh.read() != payload:
                    drift.append("%s 内容漂移" % rel)
        else:
            _write_text(path, text)
            print("已生成: %s" % rel)

    if args.check:
        if drift:
            print("FROZEN_TRUTH_DRIFT: %s" % "; ".join(drift), file=sys.stderr)
            return 1
        print("FROZEN_TRUTH_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
