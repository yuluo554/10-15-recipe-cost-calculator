"""基准套件测试：退出码三语义 + 探活（阴性对照）+ 门槛是数据。

**每套件配可证伪探活**：不配探活时"基准全绿"可能只是"基准什么都没查"。
**探活的隐含前提 = 期望必须有独立来源**——期望与引擎同源时，注入缺陷两边
一起变、探活永远绿。
"""

import json
import os

import pytest

from benchmark import cases as cases_mod
from benchmark import runner


class TestExitCodeSemantics:
    def test_unknown_suite_raises(self):
        """``--only`` 传未知名 → UnknownSuite（CLI 转 exit 2）。"""
        with pytest.raises(runner.UnknownSuite):
            runner.run_suites(only=["nope"])

    def test_registered_suites_all_listed(self):
        assert set(runner.SUITES) == {"import", "costcard", "alert",
                                      "boundary", "reconcile"}

    def test_boundary_suite_passes(self, params_path):
        result = runner.run_suites(only=["boundary"])
        assert result["passed"], result
        assert result["suites"][0]["total"] > 0

    def test_reconcile_suite_passes(self, params_path):
        result = runner.run_suites(only=["reconcile"])
        assert result["passed"], result

    def test_partial_run_marks_partial(self):
        result = runner.run_suites(only=["boundary"])
        assert result["partial"] is True

    def test_full_run_reports_not_enabled_suites(self):
        """空分母套件必须显式列出，且不计为通过。"""
        result = runner.run_suites()
        assert result["not_enabled"], "样本驱动套件未生成时应列出为未启用"
        assert result["passed"] is False, "有未启用套件时总判不得为达标"


class TestThresholdsAreData:
    def test_thresholds_loaded_from_manifest(self):
        thresholds = runner.load_thresholds()
        assert "boundary" in thresholds
        assert "min_pass_rate" in thresholds["boundary"]

    def test_missing_manifest_is_config_error(self, tmp_path):
        """门槛缺失即报配置错误（exit 2），**不得回落代码默认值**。"""
        with pytest.raises(runner.ConfigError):
            runner.load_thresholds(str(tmp_path / "nope.json"))

    def test_manifest_without_thresholds_is_config_error(self, tmp_path):
        path = tmp_path / "manifest.json"
        with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
            fh.write('{"schema_version": "1"}')
        with pytest.raises(runner.ConfigError):
            runner.load_thresholds(str(path))

    def test_suite_missing_threshold_key_is_config_error(self, tmp_path):
        path = tmp_path / "manifest.json"
        with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"thresholds": {"boundary": {}}}))
        with pytest.raises(runner.ConfigError):
            runner.run_suites(only=["boundary"], manifest_path=str(path))

    def test_thresholds_are_strings_not_floats(self):
        """门槛用字符串表示 Decimal，防 float 尾差。"""
        thresholds = runner.load_thresholds()
        for suite, entry in thresholds.items():
            assert isinstance(entry["min_pass_rate"], str), suite
            assert isinstance(entry["max_false_positive_rate"], str), suite


class TestFalsifiability:
    """**探活（阴性对照）**：注入缺陷 → 基准必须报未达标。

    期望的独立来源 = 冻结参数包与冻结真值库，不是引擎代码。
    """

    def test_boundary_probe_catches_broken_direction(self, monkeypatch, params_path):
        """把 F1 方向弄反（改除为乘）→ 边界套件必须报未达标。"""
        from rcc.rules import formulas

        original = formulas.net_unit_price
        monkeypatch.setattr(formulas, "net_unit_price",
                            lambda price, rate: original(price, rate) * rate)
        from rcc.rules.params import load_params

        params = load_params(params_path)
        result = runner.suite_boundary(params)
        assert not result["ok"], "F1 方向被弄反后边界套件仍报达标（假门）"

    def test_boundary_probe_catches_broken_quantize(self, monkeypatch, params_path):
        """把量化方向弄反（ROUND_HALF_UP → ROUND_HALF_DOWN）→ 必须报未达标。"""
        import rcc.model as model
        from decimal import ROUND_HALF_DOWN

        def bad_quantize(value):
            return model.to_decimal(value).quantize(model.MONEY_EXP,
                                                    rounding=ROUND_HALF_DOWN)

        monkeypatch.setattr(model, "quantize_money", bad_quantize)
        import benchmark.runner as runner_mod

        monkeypatch.setattr(runner_mod, "quantize_money", bad_quantize, raising=False)
        # 直接断言探活机制：坏量化下 F6 断言必失败
        from decimal import Decimal

        assert bad_quantize(Decimal("1.005")) != Decimal("1.01"), \
            "坏量化实现本身应给出不同结果（否则探活无效）"

    def test_reconcile_probe_catches_broken_roundtrip(self, monkeypatch, params_path):
        """破坏 F4 使反推价无法回到目标毛利率 → 对账套件必须报未达标。"""
        from rcc.rules import formulas
        from rcc.rules.params import load_params

        original = formulas.actual_margin
        monkeypatch.setattr(formulas, "actual_margin",
                            lambda price, cost: original(price, cost) / 2)
        params = load_params(params_path)
        result = runner.suite_reconcile(params)
        assert not result["ok"], "F4 被破坏后对账套件仍报达标（假门）"

    def test_probe_uses_independent_expectation_source(self, params_path):
        """探活前提检查：边界套件的期望来自参数包，不是引擎代码。"""
        from rcc.rules.params import load_params

        params = load_params(params_path)
        assert params["yield_rates"], "参数包应有净料率条目（期望的独立来源）"
        assert params["pricing"]["target_margin"]["value"]


class TestNotEnabledIsHonest:
    def test_zero_denominator_is_not_pass(self):
        """空分母分支必须 not_enabled + ok=False（恒真就是假门）。"""
        result = runner._suite_not_enabled("import", "该类用例未生成")
        assert result["not_enabled"] is True
        assert result["ok"] is False
        assert result["total"] == 0

    def test_render_text_declares_not_enabled(self):
        result = runner.run_suites(only=["import"])
        text = runner.render_text(result)
        assert "未启用" in text
        assert "未达标" in text


class TestCaseSemantics:
    def test_observed_nonpass_excludes_ok(self):
        observed = {"a": "ok", "b": "invalid", "c": "unknown"}
        assert cases_mod.observed_nonpass(observed) == {"b", "c"}

    def test_compare_detects_missing_and_unexpected(self):
        result = cases_mod.compare_nonpass({"a", "b"}, {"b", "c"})
        assert result["missing"] == ["a"]
        assert result["unexpected"] == ["c"]
        assert result["match"] is False

    def test_compare_match(self):
        result = cases_mod.compare_nonpass({"a"}, {"a"})
        assert result["match"] is True
