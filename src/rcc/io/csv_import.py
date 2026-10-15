"""进货单解析（CSV）—— ``check`` 与 ``run`` 的**唯一分派点**。

两条通路（``pipeline.compute_full`` 与 ``pipeline.check_inputs``）都只经本模块的
``parse_purchases`` 取判定结果——**项目里不存在第二份列名映射或第二份三态判定逻辑**
（守门见 ``tests/guards/test_import_dispatch.py``）。

三态语义（plan/02 §5）：

========== ========================================================= ==============
状态       触发                                                      计入异常清单
========== ========================================================= ==============
``ok``     列名白名单命中 + 类型校验通过                              否
``invalid`` 数值越界 / 非数值 / 必填列为空                            是
``unknown`` 列名未登记（``mapping_uncertain``）或**整行结构不可解析**   是
========== ========================================================= ==============

**红线**：``unknown`` 不等于 ``ok``（"没看到" ≠ "没有"）；异常行一律**列入清单并
计数**，绝不静默丢弃后报告"导入成功"。批量解析单行异常**不中断整批**。

两处 ``unknown`` 的**行是否仍可用**是分开的口径（别混）：

- **未登记列名**（表头级）：只是"多了一列不认识的"，已登记列照常解析 →
  记一条 line=1 的异常，**行仍可用**；
- **整行结构不可解析**（行级）：字段数多于表头 → 多余值会被 DictReader 塞进
  ``restkey``，**列对齐已不可信** → 该行记 ``unknown`` 且**不入库**（宁可少一行
  可用数据，不可把错位的值当成对的）。

其余已登记的口径（不写就是隐性第二口径）：

- **编码**：只接受 UTF-8（含 BOM，按 ``utf-8-sig`` 读）。**不做编码猜测**——
  猜错会把 GBK 的字节静默解成乱码品名，比报错危险得多；非 UTF-8 一律
  ``ValueError``（CLI 转 exit 2）。
- **空白行**：整行无内容时 ``csv`` 模块本就不产出记录，本模块沿用（不是"静默跳过
  数据行"——空行不是记录；行尾换行与空行是编辑器常态）。
- **金额列**：属**留档参考**，不参与任何计算（成本由 ``数量 × 单价`` 经 F1/F2 得出），
  故本期**不校验其数值性**；该列非数值不影响该行判 ``ok``。此项为显式登记的首期口径。
- **单位列**：非必填；未登记单位记 ``unknown`` 提示，但**行仍可用**（首期不做单位
  换算，换算规则属扩展项）。

失败路径（空文件 / 缺表头 / 缺必填列 / 坏编码 / CSV 结构错）一律**显式抛错**，
交 CLI 转成"输入不可用"（exit 2）——这类是整个文件的形态问题，不是某一行的问题，
把它们混进逐行清单会误导读者去改某一行。
"""

import csv
import io
import os
from decimal import InvalidOperation

from ..model import (
    STATUS_INVALID,
    STATUS_OK,
    STATUS_UNKNOWN,
    make_source,
    to_decimal,
)

# 只读 UTF-8（BOM 由 utf-8-sig 吃掉）——不猜测其它编码
ENCODING = "utf-8-sig"

# 列名白名单 → 内部字段名。**未登记的列名一律 unknown（mapping_uncertain），绝不猜。**
COLUMN_MAP = {
    "日期": "date",
    "品名": "name",
    "类别": "category",
    "数量": "qty",
    "单位": "unit",
    "单价": "unit_price",
    "金额": "amount",
}

REQUIRED_FIELDS = ("name", "qty", "unit_price")

# 表头必备列名（由 COLUMN_MAP 反查得出，**不另写一份映射**）
_FIELD_TO_COLUMN = {field: column for column, field in COLUMN_MAP.items()}
REQUIRED_COLUMNS = tuple(_FIELD_TO_COLUMN[field] for field in REQUIRED_FIELDS)

# 单位白名单：仅作一致性提示，不做换算（换算规则属扩展项）
KNOWN_UNITS = ("斤", "公斤", "千克", "克", "个", "只", "把", "棵", "袋", "盒")

# 异常代码（机读判据；测试断言它，不去匹配中文散文）
ISSUE_MAPPING_UNCERTAIN = "mapping_uncertain"
ISSUE_STRUCTURE = "structure_unparsable"
ISSUE_REQUIRED_EMPTY = "required_empty"
ISSUE_NOT_NUMERIC = "not_numeric"
ISSUE_NEGATIVE = "negative"
ISSUE_UNIT_UNREGISTERED = "unit_unregistered"
# 文件级结论（line=0）：整份进货单零可用行——不是某一行的错，是全行皆异常
ISSUE_NO_USABLE_ROWS = "no_usable_rows"


class RowResult(dict):
    """单行解析结果（dict 子类，便于直接 JSON 序列化）。"""


def _issue(line, status, code, reason):
    """异常清单条目。``code`` 是机读判据，``reason`` 是人读说明（两者都给）。"""
    return {"line": line, "status": status, "code": code, "reason": reason}


def _read_text(path):
    """读进货单文本；非 UTF-8 显式拒绝（不猜测编码）。"""
    try:
        with open(path, "r", encoding=ENCODING, newline="") as fh:
            return fh.read()
    except UnicodeDecodeError as exc:
        raise ValueError(
            "进货单编码不是 UTF-8（%s）——不做编码猜测，请另存为 UTF-8 后重试" % exc)


def _validate_header(fieldnames):
    """表头形态校验：返回 ``(header, unknown_cols)``；形态不可用即抛错。"""
    if not fieldnames:
        raise ValueError("进货单缺少表头")
    header = [(name or "").strip() for name in fieldnames]
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise ValueError(
            "进货单表头缺少必填列: %s（实际表头: %s）"
            % ("、".join(missing), "、".join(name for name in header if name) or "空"))
    unknown_cols = [name for name in header if name and name not in COLUMN_MAP]
    return header, unknown_cols


def parse_purchases(path, source_kind="user"):
    """解析进货单 CSV。

    返回 ``{"rows": [...], "issues": [...], "summary": str,
    "unknown_columns": [...], "status_counts": {...}}``。
    ``issues`` 逐条含 ``line`` / ``status`` / ``code`` / ``reason``，
    **不静默跳过任何行**。
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    text = _read_text(path)
    if not text.strip():
        raise ValueError("进货单为空（0 字节或仅空白）")

    reader = csv.DictReader(io.StringIO(text, newline=""))
    _header, unknown_cols = _validate_header(reader.fieldnames)

    rows, issues = [], []
    for column in unknown_cols:
        issues.append(_issue(1, STATUS_UNKNOWN, ISSUE_MAPPING_UNCERTAIN,
                             "未登记列名（mapping_uncertain）: %s" % column))

    while True:
        try:
            raw = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            # CSV 结构错（如字段内 NUL 字节）——整个文件的形态问题，不是某一行的问题
            raise ValueError("进货单结构不可解析（第 %d 行附近，CSV 格式错误: %s）"
                             % (reader.line_num, exc))

        line_no = reader.line_num

        # 结构判定优先于取值判定：字段数多于表头 → 列对齐不可信，该行不入库
        extras = raw.get(None)
        if extras:
            issues.append(_issue(
                line_no, STATUS_UNKNOWN, ISSUE_STRUCTURE,
                "整行结构不可解析：字段数多于表头（多余 %d 个），列对齐不可信"
                % len(extras)))
            continue

        row = {}
        for key, value in raw.items():
            if key is None:
                continue
            key = key.strip()
            if key in COLUMN_MAP:
                row[COLUMN_MAP[key]] = (value or "").strip()

        name = row.get("name", "")
        if not name:
            issues.append(_issue(line_no, STATUS_INVALID, ISSUE_REQUIRED_EMPTY,
                                 "必填列「品名」为空"))
            continue

        try:
            qty = to_decimal(row.get("qty", ""))
        except (InvalidOperation, TypeError, ValueError):
            issues.append(_issue(line_no, STATUS_INVALID, ISSUE_NOT_NUMERIC,
                                 "数量非数值: %r" % row.get("qty")))
            continue

        try:
            unit_price = to_decimal(row.get("unit_price", ""))
        except (InvalidOperation, TypeError, ValueError):
            issues.append(_issue(line_no, STATUS_INVALID, ISSUE_NOT_NUMERIC,
                                 "单价非数值: %r" % row.get("unit_price")))
            continue

        if qty < 0 or unit_price < 0:
            issues.append(_issue(line_no, STATUS_INVALID, ISSUE_NEGATIVE,
                                 "数量/单价为负"))
            continue

        unit = row.get("unit", "")
        if unit and unit not in KNOWN_UNITS:
            issues.append(_issue(line_no, STATUS_UNKNOWN, ISSUE_UNIT_UNREGISTERED,
                                 "单位未登记: %s" % unit))

        rows.append(RowResult({
            "line": line_no,
            "date": row.get("date") or None,
            "name": name,
            "category": row.get("category") or None,
            "qty": qty,
            "unit": unit or None,
            "unit_price": unit_price,
            "source": make_source(source_kind, os.path.basename(path)),
        }))

    if not rows and not issues:
        # 有表头却一行数据都没有：不是"解析成功 0 行"，是输入不可用
        raise ValueError("进货单只有表头，无数据行")

    counts = {STATUS_OK: len(rows), STATUS_INVALID: 0, STATUS_UNKNOWN: 0}
    for issue in issues:
        counts[issue["status"]] = counts.get(issue["status"], 0) + 1

    summary = "进货单 %s: 解析成功 %d 行，异常 %d 条" % (
        os.path.basename(path), len(rows), len(issues))
    return {"rows": rows, "issues": issues, "summary": summary,
            "unknown_columns": unknown_cols, "status_counts": counts}


def build_food_library(rows):
    """由进货行构建食材库：品名 → 类别/单位/参考价。

    **同品名取舍口径（显式登记，非隐性第二口径）**：同品名出现多条时，
    **取最后一条的价**（后出现者覆盖前者，即"该品名的最新进货价"）。

    这个口径必须写下来：进货单里同一食材可多次出现（不同日期/批次/规格），
    "取第一条"与"取最后一条"会得出不同参考价，而**两者都能自圆其说**——不登记
    就会在别处长出第二份实现（M1 在快照侧踩过同类坑：``prodName`` 同日可重复）。
    重复品名可经 :func:`duplicate_names` 观测。
    """
    library = {}
    for row in rows:
        library[row["name"]] = {
            "category": row.get("category"),
            "unit": row.get("unit"),
            "ref_price": row["unit_price"],
            "source": row["source"],
        }
    return library


def duplicate_names(rows):
    """返回在进货单里出现多次的品名（按首次出现顺序，确定性）。

    重复不是错误（同一食材多批次进货是常态），但**必须可观测**——否则
    "同品名取最后一条"的取舍是隐性的，读者无从知道发生了覆盖。
    """
    seen, duplicates = set(), []
    for row in rows:
        name = row["name"]
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    return duplicates
