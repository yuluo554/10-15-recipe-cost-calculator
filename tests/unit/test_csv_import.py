"""进货单解析三态测试矩阵。

**红线**：``unknown`` 不等于 ``ok``；异常行一律列入清单，绝不静默丢弃。

本文件是 M2 的**显式三态矩阵**——每格都要有一个用例，否则"三态语义锁进测试"
只是文档里的一句话。矩阵：

============== ================================================ ========== ==========
状态           触发                                              行是否入库  退出码语义
============== ================================================ ========== ==========
``ok``         列名命中 + 类型校验通过                            是         —
``invalid``    必填列空 / 非数值 / 数值为负                       否         exit 1
``unknown``    未登记列名（mapping_uncertain，表头级）              是         exit 1
``unknown``    整行结构不可解析（字段数多于表头，行级）              否         exit 1
``unknown``    单位未登记                                        是         exit 1
============== ================================================ ========== ==========

**形态问题不是行问题**：空文件 / 缺表头 / 缺必填列 / 坏编码 / CSV 结构错一律抛错
（CLI → exit 2），**不进逐行清单**——把它们混进清单会误导读者去改某一行。
"""

import os

import pytest

from rcc.io import csv_import

HEADER = "日期,品名,类别,数量,单位,单价,金额\n"


def _write(tmp_path, text, name="p.csv"):
    # 不用 Path.write_text(newline=)——该参数是 3.10+，本项目底线是 3.8
    path = tmp_path / name
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return str(path)


def _write_bytes(tmp_path, payload, name="p.csv"):
    path = tmp_path / name
    with open(str(path), "wb") as fh:
        fh.write(payload)
    return str(path)


def _codes(parsed):
    return [issue["code"] for issue in parsed["issues"]]


class TestStateMatrix:
    """三态矩阵：``ok`` / ``invalid`` / ``unknown`` 各自都要有代表。"""

    def test_ok_row_enters_library(self, tmp_path):
        path = _write(tmp_path, HEADER + "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert len(parsed["rows"]) == 1
        assert not parsed["issues"]
        assert parsed["status_counts"] == {"ok": 1, "invalid": 0, "unknown": 0}

    @pytest.mark.parametrize("row,code", [
        ("2026-10-01,,蔬菜,10,斤,0.50,5.00\n", csv_import.ISSUE_REQUIRED_EMPTY),
        ("2026-10-01,大白菜,蔬菜,abc,斤,0.50,5.00\n", csv_import.ISSUE_NOT_NUMERIC),
        ("2026-10-01,大白菜,蔬菜,10,斤,xyz,5.00\n", csv_import.ISSUE_NOT_NUMERIC),
        ("2026-10-01,大白菜,蔬菜,-5,斤,0.50,5.00\n", csv_import.ISSUE_NEGATIVE),
        ("2026-10-01,大白菜,蔬菜,10,斤,-0.50,5.00\n", csv_import.ISSUE_NEGATIVE),
    ])
    def test_invalid_variants(self, tmp_path, row, code):
        parsed = csv_import.parse_purchases(_write(tmp_path, HEADER + row))
        assert not parsed["rows"], "invalid 行不得入库"
        assert _codes(parsed) == [code]
        assert parsed["issues"][0]["status"] == "invalid"
        assert parsed["status_counts"]["invalid"] == 1

    def test_unknown_column_is_header_level_row_still_usable(self, tmp_path):
        """未登记列名 → ``unknown``（mapping_uncertain），**绝不猜**；行仍可用。"""
        path = _write(tmp_path, "日期,品名,类别,数量,单位,单价,金额,备注\n"
                                "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00,x\n")
        parsed = csv_import.parse_purchases(path)
        assert _codes(parsed) == [csv_import.ISSUE_MAPPING_UNCERTAIN]
        assert parsed["issues"][0]["status"] == "unknown"
        assert parsed["issues"][0]["line"] == 1
        assert parsed["unknown_columns"] == ["备注"]
        assert len(parsed["rows"]) == 1, "表头级 unknown 不应让行失效"

    def test_structure_unparsable_row_is_unknown_and_dropped(self, tmp_path):
        """**整行结构不可解析 → unknown 且不入库**（plan/02 §5 补的第三态触发）。

        字段数多于表头时 DictReader 把多余值塞进 ``restkey``，列对齐已不可信——
        宁可少一行可用数据，不可把错位的值当成对的。
        """
        path = _write(tmp_path, HEADER
                      + "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00,多余1,多余2\n"
                      + "2026-10-01,土豆,蔬菜,8,斤,1.50,12.00\n")
        parsed = csv_import.parse_purchases(path)
        assert parsed["issues"][0]["status"] == "unknown"
        assert parsed["issues"][0]["code"] == csv_import.ISSUE_STRUCTURE
        assert parsed["issues"][0]["line"] == 2
        assert [row["name"] for row in parsed["rows"]] == ["土豆"], \
            "结构不可解析的行必须被丢弃，且不中断后续行"
        assert parsed["status_counts"]["unknown"] == 1

    def test_unknown_unit_is_unknown_but_row_usable(self, tmp_path):
        path = _write(tmp_path, HEADER + "2026-10-01,大白菜,蔬菜,10,克拉,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert _codes(parsed) == [csv_import.ISSUE_UNIT_UNREGISTERED]
        assert parsed["issues"][0]["status"] == "unknown"
        assert len(parsed["rows"]) == 1, "单位未登记只提示，不做换算，行仍可用"

    def test_unknown_is_not_ok(self, tmp_path):
        """**红线**：``unknown`` 不得被计成 ``ok``（"没看到" ≠ "没有"）。"""
        path = _write(tmp_path, "日期,品名,类别,数量,单位,单价,金额,备注\n"
                                "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00,x\n")
        parsed = csv_import.parse_purchases(path)
        assert parsed["status_counts"]["unknown"] == 1
        assert parsed["status_counts"]["ok"] == 1, "ok 只数入库行"

    def test_status_counts_are_consistent(self, tmp_path):
        """计数必须与清单一致——计数与清单不一致本身就是一种静默失真。"""
        path = _write(tmp_path, "日期,品名,类别,数量,单位,单价,金额,备注\n"
                                + "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00,x\n"
                                + "2026-10-01,,蔬菜,10,斤,0.50,5.00,x\n"
                                + "2026-10-01,土豆,蔬菜,abc,斤,1.50,0,x\n"
                                + "2026-10-01,莲藕,蔬菜,4,斤,3.50,14.00,x,多余\n")
        parsed = csv_import.parse_purchases(path)
        counts = parsed["status_counts"]
        assert counts["ok"] == len(parsed["rows"]) == 1
        for status in ("invalid", "unknown"):
            assert counts[status] == sum(
                1 for issue in parsed["issues"] if issue["status"] == status)


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

    def test_all_rows_bad_yields_zero_usable_rows(self, tmp_path):
        """全行异常：不抛错（交调用方决定退出码），但可用行为 0 且清单完整。"""
        path = _write(tmp_path, HEADER
                      + "2026-10-01,坏行甲,蔬菜,abc,斤,0.50,5.00\n"
                      + "2026-10-01,,蔬菜,10,斤,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert not parsed["rows"]
        assert parsed["status_counts"]["ok"] == 0
        assert parsed["status_counts"]["invalid"] == 2

    def test_issues_carry_line_numbers(self, tmp_path):
        path = _write(tmp_path, HEADER + "2026-10-01,坏行,蔬菜,abc,斤,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert parsed["issues"][0]["line"] == 2


class TestShapeFailures:
    """**形态问题不是行问题**：整份文件不可用 → 抛错（CLI → exit 2）。"""

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            csv_import.parse_purchases("definitely-not-here.csv")

    def test_empty_file_raises(self, tmp_path):
        with pytest.raises(ValueError, match="为空"):
            csv_import.parse_purchases(_write(tmp_path, ""))

    def test_whitespace_only_file_raises(self, tmp_path):
        with pytest.raises(ValueError, match="为空"):
            csv_import.parse_purchases(_write(tmp_path, "\n \n\t\n"))

    def test_header_only_raises(self, tmp_path):
        """只有表头、零数据行：不是"解析成功 0 行"，是输入不可用。"""
        with pytest.raises(ValueError, match="只有表头"):
            csv_import.parse_purchases(_write(tmp_path, HEADER))

    def test_missing_required_column_raises(self, tmp_path):
        with pytest.raises(ValueError, match="缺少必填列"):
            csv_import.parse_purchases(
                _write(tmp_path, "日期,品名,类别,单位\n2026-10-01,大白菜,蔬菜,斤\n"))

    def test_missing_required_column_names_the_column(self, tmp_path):
        with pytest.raises(ValueError, match="数量"):
            csv_import.parse_purchases(
                _write(tmp_path, "日期,品名,类别,单位,单价,金额\n"
                                 "2026-10-01,大白菜,蔬菜,斤,0.50,5.00\n"))

    def test_non_utf8_encoding_raises(self, tmp_path):
        """**不做编码猜测**：猜错会把 GBK 字节静默解成乱码品名，比报错危险得多。"""
        payload = (HEADER + "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n").encode("gbk")
        with pytest.raises(ValueError, match="不是 UTF-8"):
            csv_import.parse_purchases(_write_bytes(tmp_path, payload))

    def test_gbk_bytes_are_not_silently_misread(self, tmp_path):
        """反面自证：GBK 件若被当 UTF-8 硬读会得到乱码品名——所以必须报错。"""
        payload = (HEADER + "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n").encode("gbk")
        raw = payload.decode("utf-8", "replace")
        assert "大白菜" not in raw, "探活前提失效：GBK 字节竟能被 UTF-8 读成原字"
        with pytest.raises(ValueError):
            csv_import.parse_purchases(_write_bytes(tmp_path, payload))


class TestHeaderVariants:
    def test_utf8_bom_header_is_accepted(self, tmp_path):
        """BOM（``utf-8-sig``）必须能吃下——Excel 另存为 CSV 默认就带 BOM。"""
        path = _write(tmp_path, "\ufeff" + HEADER
                      + "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert len(parsed["rows"]) == 1
        assert parsed["rows"][0]["name"] == "大白菜", "BOM 不得粘进首个列名"
        assert not parsed["unknown_columns"], "BOM 不得让「日期」变成未登记列"

    def test_shuffled_column_order_is_accepted(self, tmp_path):
        """列顺序打乱不影响映射（按列名映射，不按位置）。"""
        path = _write(tmp_path, "金额,单价,单位,数量,类别,品名,日期\n"
                                "5.00,0.50,斤,10,蔬菜,大白菜,2026-10-01\n")
        parsed = csv_import.parse_purchases(path)
        assert len(parsed["rows"]) == 1
        row = parsed["rows"][0]
        assert row["name"] == "大白菜"
        assert str(row["unit_price"]) == "0.50", "列乱序不得把单价与金额串位"
        assert row["qty"] == 10

    def test_extra_empty_column_is_accepted(self, tmp_path):
        """多余空列（无列名）不产生 unknown，也不影响取值。"""
        path = _write(tmp_path, "日期,品名,类别,数量,单位,单价,金额,\n"
                                "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00,\n")
        parsed = csv_import.parse_purchases(path)
        assert len(parsed["rows"]) == 1
        assert not parsed["unknown_columns"], "空列名不算未登记列名"
        assert not parsed["issues"]

    def test_blank_lines_between_rows_are_tolerated(self, tmp_path):
        """行间空行不是数据行（csv 模块本就不产出记录）——不得因此丢数据。"""
        path = _write(tmp_path, HEADER
                      + "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n"
                      + "\n"
                      + "2026-10-01,土豆,蔬菜,8,斤,1.50,12.00\n"
                      + "\n")
        parsed = csv_import.parse_purchases(path)
        assert len(parsed["rows"]) == 2
        assert not parsed["issues"]

    def test_header_whitespace_is_trimmed(self, tmp_path):
        path = _write(tmp_path, " 日期 , 品名 , 类别 , 数量 , 单位 , 单价 , 金额 \n"
                                "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert len(parsed["rows"]) == 1
        assert not parsed["unknown_columns"]


class TestAmountColumnSemantics:
    def test_non_numeric_amount_does_not_invalidate_row(self, tmp_path):
        """**首期登记口径**：金额列是留档参考，不参与计算，故不校验数值性。

        成本由 ``数量 × 单价`` 经 F1/F2 得出，金额列是原始单据的冗余列。
        若哪天要改成校验，改这里同时改 csv_import 模块 docstring。
        """
        path = _write(tmp_path, HEADER + "2026-10-01,大白菜,蔬菜,10,斤,0.50,待核\n")
        parsed = csv_import.parse_purchases(path)
        assert len(parsed["rows"]) == 1, "金额非数值不应让行失效"
        assert not parsed["issues"]


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

    def test_duplicate_name_takes_last_price(self, tmp_path):
        """**同品名取最后一条价**——显式登记的口径，不是隐性行为。"""
        path = _write(tmp_path, HEADER
                      + "2026-10-01,土豆,蔬菜,10,斤,1.00,10.00\n"
                      + "2026-10-05,土豆,蔬菜,10,斤,2.00,20.00\n")
        parsed = csv_import.parse_purchases(path)
        library = csv_import.build_food_library(parsed["rows"])
        assert str(library["土豆"]["ref_price"]) == "2.00"

    def test_duplicate_names_are_observable(self, tmp_path):
        """重复不是错误，但**必须可观测**——否则取舍是隐性的。"""
        path = _write(tmp_path, HEADER
                      + "2026-10-01,土豆,蔬菜,10,斤,1.00,10.00\n"
                      + "2026-10-05,大白菜,蔬菜,10,斤,1.00,10.00\n"
                      + "2026-10-05,土豆,蔬菜,10,斤,2.00,20.00\n"
                      + "2026-10-05,土豆,蔬菜,10,斤,3.00,30.00\n")
        parsed = csv_import.parse_purchases(path)
        assert csv_import.duplicate_names(parsed["rows"]) == ["土豆"], \
            "每个重复品名只登记一次，且按首次出现顺序"

    def test_no_duplicates_reports_empty(self, tmp_path):
        path = _write(tmp_path, HEADER + "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n")
        parsed = csv_import.parse_purchases(path)
        assert csv_import.duplicate_names(parsed["rows"]) == []


class TestColumnMapSingleSource:
    """列名白名单只有一份；必备列由它反查得出（防"加列忘改两处"）。"""

    def test_required_columns_derived_from_column_map(self):
        for column in csv_import.REQUIRED_COLUMNS:
            assert csv_import.COLUMN_MAP[column] in csv_import.REQUIRED_FIELDS

    def test_required_fields_all_have_columns(self):
        for field in csv_import.REQUIRED_FIELDS:
            assert field in csv_import.COLUMN_MAP.values(), \
                "必填字段 %s 不在列名白名单里（永远不可能满足）" % field

    def test_every_issue_code_is_declared(self, tmp_path):
        """异常代码必须是本模块声明的常量之一（防散落的裸字符串）。"""
        declared = {value for name, value in vars(csv_import).items()
                    if name.startswith("ISSUE_")}
        path = _write(tmp_path, "日期,品名,类别,数量,单位,单价,金额,备注\n"
                                + "2026-10-01,,蔬菜,10,斤,0.50,5.00,x\n"
                                + "2026-10-01,土豆,蔬菜,abc,斤,1.50,0,x\n"
                                + "2026-10-01,南瓜,蔬菜,-2,斤,1.80,-3.60,x\n"
                                + "2026-10-01,莲藕,蔬菜,4,斤,3.50,14.00,x,多余\n"
                                + "2026-10-01,冬瓜,蔬菜,5,克拉,1.20,6.00,x\n")
        parsed = csv_import.parse_purchases(path)
        assert _codes(parsed)
        for code in _codes(parsed):
            assert code in declared, "未声明的异常代码: %r" % code

    def test_file_level_code_is_declared_too(self):
        """文件级结论（零可用行）的代码也在声明集合里——它由 pipeline 使用。

        行级代码与文件级代码**语义不同**（"某一行不合格" vs "整份文件没有可用行"），
        借用行级代码当文件级结论会让下游按行号定位到一个不存在的问题行。
        """
        declared = {value for name, value in vars(csv_import).items()
                    if name.startswith("ISSUE_")}
        assert csv_import.ISSUE_NO_USABLE_ROWS in declared
        assert csv_import.ISSUE_NO_USABLE_ROWS != csv_import.ISSUE_REQUIRED_EMPTY


class TestSampleFile:
    def test_demo_sample_has_injected_anomalies(self, repo_root):
        """样例文件刻意注入异常行——供"不静默跳过"的演示与测试。"""
        path = os.path.join(repo_root, "src", "rcc", "data", "samples", "purchases-demo.csv")
        parsed = csv_import.parse_purchases(path)
        assert parsed["rows"], "样例应含正常行"
        assert parsed["issues"], "样例应含刻意注入的异常行"
        statuses = {issue["status"] for issue in parsed["issues"]}
        assert "invalid" in statuses
        assert "unknown" in statuses

    def test_demo_sample_covers_every_state_and_anomaly_class(self, repo_root):
        """样例是三态的**演示载体**：每格都要有代表，否则矩阵在样例上看不见。"""
        path = os.path.join(repo_root, "src", "rcc", "data", "samples", "purchases-demo.csv")
        parsed = csv_import.parse_purchases(path)
        codes = set(_codes(parsed))
        for code in (csv_import.ISSUE_MAPPING_UNCERTAIN,
                     csv_import.ISSUE_STRUCTURE,
                     csv_import.ISSUE_REQUIRED_EMPTY,
                     csv_import.ISSUE_NOT_NUMERIC,
                     csv_import.ISSUE_NEGATIVE,
                     csv_import.ISSUE_UNIT_UNREGISTERED):
            assert code in codes, "样例未覆盖异常类 %s" % code
        assert csv_import.duplicate_names(parsed["rows"]), \
            "样例应含重复品名（让「取最后一条」的取舍可观测）"

    def test_demo_sample_is_reproducible_by_generator(self, repo_root):
        """样例必须**由生成器产出**（禁手改）——手改会让 README 引用的样例漂移。"""
        import sys

        sys.path.insert(0, os.path.join(repo_root, "tools"))
        import gen_samples

        produced = gen_samples.outputs()
        path = "src/rcc/data/samples/purchases-demo.csv"
        assert path in produced
        actual = open(os.path.join(repo_root, path), "rb").read()
        assert actual == produced[path].encode("utf-8"), \
            "样例与生成器输出不一致（被手改过？）"
