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

    def test_full_run_enables_all_five_suites(self):
        """M4 起真值库已入库——**五套件全部启用**（不再有 not_enabled）。"""
        result = runner.run_suites()
        assert result["not_enabled"] == [], (
            "真值库已产出，样本驱动套件不应再是未启用: %s" % result["not_enabled"])
        assert result["passed"] is True, result
        assert {s["suite"] for s in result["suites"]} == set(runner.SUITES)
        for suite in result["suites"]:
            assert suite["total"] > 0, "%s 的分母为 0（恒真假门）" % suite["suite"]


class TestLiveObservationNotFrozenComparison:
    """**M4 关键**：观测必须在运行时实算，不是比对两个冻结字典。

    若把观测也冻进真值库，评测就退化成"两个冻结字典相等"，**引擎坏掉也照样全绿**。
    """

    def test_broken_engine_makes_sample_suites_fail(self, monkeypatch, params_path):
        """把 F1 方向弄反 → **样本驱动套件也必须报未达标**（不是只有规则驱动层红）。"""
        from rcc.rules import formulas

        original = formulas.net_unit_price
        monkeypatch.setattr(formulas, "net_unit_price",
                            lambda price, rate: original(price, rate) * rate)
        result = runner.run_suites(only=["costcard"])
        assert not result["passed"], (
            "F1 被弄反后成本卡样本套件仍报达标——观测是冻的，不是活的")

    def test_import_suite_observes_live_parser(self, monkeypatch):
        """把解析器的三态判定弄坏 → B1 必须报未达标。"""
        from rcc.io import csv_import

        original = csv_import.parse_purchases

        def bad_parser(path, *args, **kwargs):
            parsed = original(path, *args, **kwargs)
            # 静默丢弃全部异常行（正是"unknown 不等于 ok"要防的那类改动）
            parsed["issues"] = []
            return parsed

        monkeypatch.setattr(csv_import, "parse_purchases", bad_parser)
        result = runner.run_suites(only=["import"])
        assert not result["passed"], "解析器静默丢弃异常行后 B1 仍达标（观测是死的）"

    def test_alert_suite_observes_live_sorting(self, monkeypatch):
        """把排序规则弄反（降序→升序）→ B3 必须报未达标（plan/03 §七 的 B3 探活）。"""
        from rcc.alert import threshold as alert_mod

        original = alert_mod.diff_prices

        def reversed_sort(old_prices, new_prices):
            rows = original(old_prices, new_prices)
            rows.reverse()
            return rows

        monkeypatch.setattr(alert_mod, "diff_prices", reversed_sort)
        result = runner.run_suites(only=["alert"])
        assert not result["passed"], "排序被弄反后 B3 仍达标（假门）"


class TestTruthTamperProbes:
    """plan/03 §七 的探活表：**篡改冻结期望 → 基准必须报未达标**。

    这一组直接改真值库副本里的期望键（B1 篡改真值 / B2 篡改成本期望 /
    B3 篡改分类期望），验证"期望与引擎解耦"这条前提真成立：期望独立时，
    篡改期望立刻让基准变红。
    """

    def _tampered_suite(self, tmp_path, suite, mutate):
        """把一套真值库复制到树外、施加篡改，再对同一批输入跑该套件。"""
        import json

        src = os.path.join(os.path.dirname(_manifest_path()), "%s.json" % suite)
        with open(src, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        mutate(payload)
        target = tmp_path / ("%s.json" % suite)
        with open(str(target), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return runner._sample_suite(suite, str(target), str(tmp_path))

    def test_import_tampered_expectation_is_detected(self, tmp_path):
        """B1 探活：把某条用例的期望换成不存在的列名异常 → 必须报未达标。"""
        def mutate(payload):
            for case in payload["cases"]:
                if case["id"] == "imp-ok-row":
                    case["expect_keys"] = ["issue:L2:mapping_uncertain:unknown"]

        result = self._tampered_suite(tmp_path, "import", mutate)
        assert not result["ok"], "篡改真值期望后 B1 仍达标（期望与引擎同源？）"

    def test_costcard_tampered_expectation_is_detected(self, tmp_path):
        """B2 探活：把某道菜的期望成本改掉 → 必须报未达标。"""
        def mutate(payload):
            for case in payload["cases"]:
                if case["id"] == "cc-single-food":
                    case["expect_keys"] = ["pipeline:ok", "cost:醋溜白菜=999.99"]

        result = self._tampered_suite(tmp_path, "costcard", mutate)
        assert not result["ok"], "篡改成本期望后 B2 仍达标（假门）"

    def test_alert_tampered_expectation_is_detected(self, tmp_path):
        """B3 探活：把某食材的分类期望改反 → 必须报未达标。"""
        def mutate(payload):
            for case in payload["cases"]:
                if case["id"] == "al-status-up":
                    case["expect_keys"] = ["status:莴笋=down"]

        result = self._tampered_suite(tmp_path, "alert", mutate)
        assert not result["ok"], "篡改分类期望后 B3 仍达标（假门）"


class TestDurationThresholdIsEnforced:
    """``max_duration_seconds`` 随 manifest 下发，原先**未被校验也未使用**。

    "登记在门槛里却没人看"等于登记了却静默不判——故本项必须真判。
    """

    def test_duration_is_measured_and_reported(self):
        result = runner.run_suites(only=["boundary"])
        suite = result["suites"][0]
        assert "duration_seconds" in suite
        assert suite["duration_ok"] is True

    def test_duration_threshold_failure_marks_suite_not_ok(self, monkeypatch):
        """时长超门槛 → 该套件必须未达标（证明时长**真参与判定**）。

        用可控时钟（每次调用前进 100 秒）而非真实计时——真实计时下"极快套件"
        可能恰好等于门槛（如门槛 0 与实测 0.0），测出来的是计时抖动不是判定逻辑。
        """
        ticks = {"n": 0}

        def fake_monotonic():
            ticks["n"] += 1
            return ticks["n"] * 100.0

        monkeypatch.setattr(runner.time, "monotonic", fake_monotonic)
        result = runner.run_suites(only=["boundary"])
        suite = result["suites"][0]
        assert suite["duration_seconds"] > 10, suite["duration_seconds"]
        assert suite["duration_ok"] is False, "时长超门槛却判为达标（门槛没被用上）"
        assert suite["ok"] is False

    def test_missing_duration_key_is_config_error(self, tmp_path):
        """门槛字段缺一即配置错误——**不回落代码默认值**。"""
        import json

        path = tmp_path / "manifest.json"
        payload = json.loads(open(_manifest_path(), encoding="utf-8").read())
        del payload["thresholds"]["boundary"]["max_duration_seconds"]
        with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False))
        with pytest.raises(runner.ConfigError):
            runner.run_suites(only=["boundary"], manifest_path=str(path))


class TestFalsePositiveIsMeasuredNotHardcoded:
    """误报率若写死为 0，与门槛比较就是恒真假门（门槛配 0 也永远满足）。"""

    def test_sample_suites_report_measured_false_positive_channel(self):
        result = runner.run_suites(only=["import"])
        suite = result["suites"][0]
        assert suite["false_positive_measured"] is True

    def test_rule_driven_suites_declare_unmeasured(self):
        """规则驱动层没有观测键通道 → 显式声明未测，不拿恒 0 冒充达标。"""
        result = runner.run_suites(only=["boundary", "reconcile"])
        for suite in result["suites"]:
            assert suite["false_positive_measured"] is False

    def test_false_positive_rate_reacts_to_extra_observations(self, monkeypatch):
        """观测多出结论键 → 误报率必须 > 0（不是恒 0）。"""
        from benchmark import cases as cases_mod

        original = cases_mod.observe_import

        def noisy_observer(record, workdir):
            observed = original(record, workdir)
            observed["issue:L999:invented:unknown"] = cases_mod.OK
            return observed

        monkeypatch.setitem(cases_mod.SUITE_OBSERVERS, "import", noisy_observer)
        result = runner.run_suites(only=["import"])
        suite = result["suites"][0]
        assert suite["false_positive_rate"] > 0, "误报率未随观测变化（写死的？）"
        assert suite["passed"] < suite["total"]


def _manifest_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "data", "truth", "manifest.json")


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

    def test_missing_threshold_key_is_config_error(self, tmp_path):
        path = tmp_path / "manifest.json"
        with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"thresholds": {"boundary": {}}}))
        with pytest.raises(runner.ConfigError):
            runner.run_suites(only=["boundary"], manifest_path=str(path))

    def test_missing_coverage_section_is_config_error(self, tmp_path):
        """覆盖度双登记缺失即配置错误——不静默当作"没这回事"。"""
        path = tmp_path / "manifest.json"
        with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"thresholds": {"boundary": {
                "min_pass_rate": "1.0", "max_false_positive_rate": "0.0",
                "max_duration_seconds": "10", "measures_false_positive": False}}}))
        with pytest.raises(runner.ConfigError):
            runner.run_suites(only=["boundary"], manifest_path=str(path))

    def test_thresholds_are_strings_not_floats(self):
        """门槛用字符串表示 Decimal，防 float 尾差。"""
        thresholds = runner.load_thresholds()
        for suite, entry in thresholds.items():
            assert isinstance(entry["min_pass_rate"], str), suite
            assert isinstance(entry["max_false_positive_rate"], str), suite
            assert isinstance(entry["max_duration_seconds"], str), suite


class TestFalsifiability:
    """**探活（阴性对照）**：注入缺陷 → 基准必须报未达标。

    期望的独立来源 = 冻结参数包与冻结真值库，不是引擎代码。
    """

    def test_boundary_probe_catches_broken_direction(self, monkeypatch, params_path):
        """B4 探活：把 F1 方向弄反（改除为乘）→ 边界套件必须报未达标。"""
        from rcc.rules import formulas

        original = formulas.net_unit_price
        monkeypatch.setattr(formulas, "net_unit_price",
                            lambda price, rate: original(price, rate) * rate)
        from rcc.rules.params import load_params

        params = load_params(params_path)
        result = runner.suite_boundary(params)
        assert not result["ok"], "F1 方向被弄反后边界套件仍报达标（假门）"

    def test_boundary_probe_catches_broken_quantize(self, monkeypatch, params_path):
        """B4 探活：量化方向反了（HALF_UP → HALF_DOWN）→ 套件必须**报未达标**。

        M4 前这条探活偏弱：只断言了坏实现本身给出不同结果，**没断言套件报未达标**。
        探活的判据必须是"基准报了未达标"——否则坏实现照样全绿。
        """
        from decimal import ROUND_HALF_DOWN, Decimal

        import rcc.model as model

        def bad_quantize(value):
            return model.to_decimal(value).quantize(model.MONEY_EXP,
                                                    rounding=ROUND_HALF_DOWN)

        # 前提断言：坏量化确实与正本不同（否则探活无从谈起，是恒真假门）
        assert bad_quantize(Decimal("1.005")) != Decimal("1.01"), "坏量化实现与正本相同"

        monkeypatch.setattr(model, "quantize_money", bad_quantize)
        import benchmark.runner as runner_mod

        monkeypatch.setattr(runner_mod, "quantize_money", bad_quantize, raising=False)
        from rcc.rules.params import load_params

        params = load_params(params_path)
        result = runner.suite_boundary(params)
        assert not result["ok"], "量化方向被弄反后边界套件仍报达标（假门）"

    def test_reconcile_probe_catches_broken_roundtrip(self, monkeypatch, params_path):
        """B5 探活：破坏 F4 使反推价无法回到目标毛利率 → 对账套件必须报未达标。"""
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

    def test_truth_libraries_are_independent_of_engine(self, repo_root):
        """B1–B3 探活前提：真值库**不含观测**，故引擎改动不会同时改动期望。"""
        import sys

        sys.path.insert(0, os.path.join(repo_root, "tools"))
        import gen_truth

        for suite in ("import", "costcard", "alert"):
            path = os.path.join(repo_root, "data", "truth", "%s.json" % suite)
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            for case in payload["cases"]:
                assert "observed" not in case, (
                    "%s/%s 冻结了观测——探活会两边一起变、永远绿" % (suite, case.get("id")))
        assert gen_truth.TRUTH_FILES, "真值库登记表为空（门形同虚设）"


class TestNotEnabledIsHonest:
    def test_zero_denominator_is_not_pass(self):
        """空分母分支必须 not_enabled + ok=False（恒真就是假门）。"""
        result = runner._suite_not_enabled("import", "该类用例未生成")
        assert result["not_enabled"] is True
        assert result["ok"] is False
        assert result["total"] == 0

    def test_missing_truth_library_is_not_enabled(self, tmp_path):
        """真值库缺失 → not_enabled（**不冒充通过**）。"""
        result = runner._sample_suite("import", str(tmp_path / "nope.json"), str(tmp_path))
        assert result["not_enabled"] is True
        assert result["ok"] is False

    def test_render_text_declares_not_enabled(self):
        """未启用套件必须显式打印，总判不得为达标。"""
        result = {"suites": [runner._suite_not_enabled("import", "该类用例未生成")],
                  "passed": False, "partial": False, "not_enabled": ["import"]}
        text = runner.render_text(result)
        assert "未启用" in text
        assert "未达标" in text

    def test_missing_truth_files_make_full_run_not_pass(self, tmp_path, monkeypatch):
        """把真值库目录换成空目录 → 总判必须未达标（空分母不冒充通过）。"""
        monkeypatch.setattr(runner, "TRUTH_DIR", str(tmp_path / "no-truth"))
        result = runner.run_suites()
        assert set(result["not_enabled"]) == {"import", "costcard", "alert"}
        assert result["passed"] is False


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
