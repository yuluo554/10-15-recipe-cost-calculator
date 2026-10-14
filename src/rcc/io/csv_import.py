"""进货单解析（CSV）。

三态语义（plan/02 §5）：``ok`` / ``invalid``（越界、非数值、必填列空）/
``unknown``（列名未登记 → ``mapping_uncertain``）。

**红线**：``unknown`` 不等于 ``ok``；异常行一律**列入清单并计数**，绝不静默丢弃后
报告"导入成功"。批量解析单行异常**不中断整批**。
"""

import csv
import os
from decimal import Decimal, InvalidOperation

from ..model import (
    STATUS_INVALID,
    STATUS_OK,
    STATUS_UNKNOWN,
    make_source,
    to_decimal,
)

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

# 单位白名单：仅作一致性提示，不做换算（换算规则属扩展项）
KNOWN_UNITS = ("斤", "公斤", "千克", "克", "个", "只", "把", "棵", "袋", "盒")


class RowResult(dict):
    """单行解析结果（dict 子类，便于直接 JSON 序列化）。"""


def parse_purchases(path, source_kind="user"):
    """解析进货单 CSV。

    返回 ``{"rows": [...], "issues": [...], "summary": str}``。
    ``issues`` 逐条含 ``line`` / ``status`` / ``reason``，**不静默跳过任何行**。
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    rows, issues = [], []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("进货单为空或缺少表头")
        header = [h.strip() if h else "" for h in reader.fieldnames]
        unknown_cols = [h for h in header if h and h not in COLUMN_MAP]
        for col in unknown_cols:
            issues.append({"line": 1, "status": STATUS_UNKNOWN,
                           "reason": "未登记列名（mapping_uncertain）: %s" % col})

        for line_no, raw in enumerate(reader, start=2):
            row = {}
            for key, value in raw.items():
                key = (key or "").strip()
                if key in COLUMN_MAP:
                    row[COLUMN_MAP[key]] = (value or "").strip()

            name = row.get("name", "")
            if not name:
                issues.append({"line": line_no, "status": STATUS_INVALID,
                               "reason": "必填列「品名」为空"})
                continue

            try:
                qty = to_decimal(row.get("qty", ""))
            except (InvalidOperation, TypeError, ValueError):
                issues.append({"line": line_no, "status": STATUS_INVALID,
                               "reason": "数量非数值: %r" % row.get("qty")})
                continue

            try:
                unit_price = to_decimal(row.get("unit_price", ""))
            except (InvalidOperation, TypeError, ValueError):
                issues.append({"line": line_no, "status": STATUS_INVALID,
                               "reason": "单价非数值: %r" % row.get("unit_price")})
                continue

            if qty < 0 or unit_price < 0:
                issues.append({"line": line_no, "status": STATUS_INVALID,
                               "reason": "数量/单价为负"})
                continue

            unit = row.get("unit", "")
            if unit and unit not in KNOWN_UNITS:
                issues.append({"line": line_no, "status": STATUS_UNKNOWN,
                               "reason": "单位未登记: %s" % unit})

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

    summary = "进货单 %s: 解析成功 %d 行，异常 %d 条" % (
        os.path.basename(path), len(rows), len(issues))
    return {"rows": rows, "issues": issues, "summary": summary,
            "unknown_columns": unknown_cols}


def build_food_library(rows):
    """由进货行构建食材库：品名 → 类别/单位/参考价（同品名取最后一条价）。"""
    library = {}
    for row in rows:
        library[row["name"]] = {
            "category": row.get("category"),
            "unit": row.get("unit"),
            "ref_price": row["unit_price"],
            "source": row["source"],
        }
    return library


def _unused_decimal_guard():
    # 保留 Decimal 引用，避免 linters 误判未使用导入
    return Decimal(0)
