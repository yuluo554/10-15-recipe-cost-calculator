"""进货单解析三态测试。

**红线**：``unknown`` 不等于 ``ok``；异常行一律列入清单，绝不静默丢弃。
"""

import os

import pytest

from rcc.io import csv_import


def _write(tmp_path, text, name="p.csv"):
    # 不用 Path.write_text(newline=)——该参数是 3.10+，本项目底线是 3.8
    path = tmp_path / name
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return str(path)


HEADER = "日期,品名,类别,数量,单位,单价,金额\n"


class TestThreeState:
    def test_valid_rows_are_ok(self, tmp_path):
        path = _write(tmp_path, HEADER + "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert len(parsed["rows"]) == 1
        assert not parsed["issues"]

    def test_non_numeric_qty_is_invalid(self, tmp_path):
        path = _write(tmp_path, HEADER + "2026-10-01,大白菜,蔬菜,abc,斤,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert not parsed["rows"]
        assert parsed["issues"][0]["status"] == "invalid"
        assert "非数值" in parsed["issues"][0]["reason"]

    def test_empty_name_is_invalid(self, tmp_path):
        path = _write(tmp_path, HEADER + "2026-10-01,,蔬菜,10,斤,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert not parsed["rows"]
        assert parsed["issues"][0]["status"] == "invalid"

    def test_unknown_column_is_unknown_not_ok(self, tmp_path):
        """未登记列名 → unknown（mapping_uncertain），**绝不猜**。"""
        path = _write(tmp_path, "日期,品名,类别,数量,单位,单价,金额,备注\n"
                                "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00,x\n")
        parsed = csv_import.parse_purchases(path)
        statuses = {issue["status"] for issue in parsed["issues"]}
        assert "unknown" in statuses
        assert "mapping_uncertain" in parsed["issues"][0]["reason"]
        assert parsed["unknown_columns"] == ["备注"]
        # 行本身仍可解析（列名未知不影响已登记列）
        assert len(parsed["rows"]) == 1

    def test_unknown_unit_is_unknown(self, tmp_path):
        path = _write(tmp_path, HEADER + "2026-10-01,大白菜,蔬菜,10,克拉,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert any(i["status"] == "unknown" for i in parsed["issues"])

    def test_negative_values_invalid(self, tmp_path):
        path = _write(tmp_path, HEADER + "2026-10-01,大白菜,蔬菜,-5,斤,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert parsed["issues"][0]["status"] == "invalid"


class TestBatchIsolation:
    def test_bad_row_does_not_abort_batch(self, tmp_path):
        """失败隔离：单行异常不中断整批。"""
        path = _write(tmp_path, HEADER
                      + "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n"
                      + "2026-10-01,坏行,蔬菜,abc,斤,0.50,5.00\n"
                      + "2026-10-01,土豆,蔬菜,8,斤,1.50,12.00\n")
        parsed = csv_import.parse_purchases(path)
        assert len(parsed["rows"]) == 2, "坏行不应中断整批"
        assert len(parsed["issues"]) == 1

    def test_issues_carry_line_numbers(self, tmp_path):
        path = _write(tmp_path, HEADER + "2026-10-01,坏行,蔬菜,abc,斤,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert parsed["issues"][0]["line"] == 2


class TestMissingFile:
    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            csv_import.parse_purchases("definitely-not-here.csv")


class TestFoodLibrary:
    def test_library_has_source(self, tmp_path):
        """入库参数必须挂来源标记。"""
        path = _write(tmp_path, HEADER + "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        library = csv_import.build_food_library(parsed["rows"])
        assert "大白菜" in library
        assert library["大白菜"]["source"]["kind"] == "user"

    def test_prices_are_decimal(self, tmp_path):
        from decimal import Decimal

        path = _write(tmp_path, HEADER + "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert parsed["rows"][0]["unit_price"] == Decimal("0.50")
        assert isinstance(parsed["rows"][0]["unit_price"], Decimal)


class TestSampleFile:
    def test_demo_sample_has_injected_anomalies(self, repo_root):
        """样例文件刻意注入异常行——供"不静默跳过"的演示与测试。"""
        path = os.path.join(repo_root, "data", "samples", "purchases-demo.csv")
        parsed = csv_import.parse_purchases(path)
        assert parsed["rows"], "样例应含正常行"
        assert parsed["issues"], "样例应含刻意注入的异常行"
        statuses = {issue["status"] for issue in parsed["issues"]}
        assert "invalid" in statuses
        assert "unknown" in statuses
