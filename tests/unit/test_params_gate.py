"""参数门控测试：三态语义 + 按作用域分门控。

**"未核对"与"本不由参数包承载"是两回事**——前者挂 pending 拦门，
后者挂 input_required 放行但运行时必索。
"""

import json
from decimal import Decimal

import pytest

from rcc.rules import params as params_mod


def _write_params(tmp_path, payload):
    path = tmp_path / "params.json"
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2))
    return str(path)


def _base_payload(status="verified"):
    return {
        "schema_version": "1",
        "yield_rates": {
            "大白菜": {"value": "0.85", "status": status,
                      "source": {"kind": "builtin_experience", "ref": "plan/02"}},
        },
        "pricing": {
            "target_margin": {"value": "0.6", "status": status,
                              "source": {"kind": "user", "ref": "plan/02"}},
        },
        "alert": {
            "threshold": {"value": "0.1", "status": status,
                          "source": {"kind": "user", "ref": "plan/02"}},
        },
    }


class TestScopeGate:
    def test_verified_passes(self, tmp_path):
        path = _write_params(tmp_path, _base_payload())
        assert "大白菜" in params_mod.effective_params("cost", path)

    def test_pending_blocks_scope(self, tmp_path):
        """pending 条目阻断该作用域的判定路径。"""
        path = _write_params(tmp_path, _base_payload(status="pending"))
        with pytest.raises(params_mod.ParamsPending) as exc:
            params_mod.effective_params("cost", path)
        assert exc.value.scope == "cost"
        assert "大白菜" in exc.value.items

    def test_input_required_passes_gate_but_must_be_asked(self, tmp_path):
        """``input_required`` **放行门控**（不阻断该作用域），但运行时必须索取。

        与 ``pending`` 的区别是本条纪律的核心（plan/02 §三）：
        "未核对"（pending）拦门，"本不由参数包承载"（input_required）放行——
        但**放行不等于静默取默认值**：它的值不进可用集，运行时由取数点显式索取，
        缺失即 exit 2。
        """
        path = _write_params(tmp_path, _base_payload(status="input_required"))
        # 门控放行（不抛错）——这就是"放行"的含义
        effective = params_mod.effective_params("cost", path)
        # 但该条目的值**不进入可用集**（值不由参数包承载，不得被当成默认值用）
        assert "大白菜" not in effective, "input_required 条目的值不得进入计算路径"

    def test_input_required_is_not_silently_defaulted_at_runtime(self, tmp_path):
        """运行时索取：取数点必须显式抛错，绝不静默取默认值。"""
        from rcc.engine import pipeline

        path = _write_params(tmp_path, _base_payload(status="input_required"))
        cost_params = params_mod.effective_params("cost", path)
        with pytest.raises(params_mod.ParamsInputRequired) as exc:
            pipeline.yield_rate_for(cost_params, "大白菜")
        assert "大白菜" in str(exc.value)

    def test_gate_is_per_scope_not_whole_pack(self, tmp_path):
        """**门控按计算路径分作用域**：无关作用域的 pending 不得阻断核算路径。"""
        payload = _base_payload()
        payload["alert"]["threshold"]["status"] = "pending"
        path = _write_params(tmp_path, payload)
        # cost 与 pricing 仍可用（未被 alert 的 pending 阻断）
        assert params_mod.effective_params("cost", path)
        assert params_mod.effective_params("pricing", path)
        # 只有 alert 被拦
        with pytest.raises(params_mod.ParamsPending):
            params_mod.effective_params("alert", path)

    @pytest.mark.parametrize("blocking_scope,section", [
        ("cost", "yield_rates"),
        ("pricing", "pricing"),
        ("alert", "alert"),
    ])
    def test_pending_blocks_each_scope_independently(self, tmp_path, blocking_scope, section):
        """**三个作用域各自都要被 pending 拦**——只测一个等于没测其余两个。

        每个 scope 的 pending 只拦自己，其余两个必须照常放行；这样"分作用域"
        才是真性质，而不是"恰好 cost 是第一个被查的"。
        """
        payload = _base_payload()
        if section == "yield_rates":
            payload[section]["大白菜"]["status"] = "pending"
        else:
            payload[section]["threshold" if section == "alert" else "target_margin"][
                "status"] = "pending"
        path = _write_params(tmp_path, payload)

        with pytest.raises(params_mod.ParamsPending) as exc:
            params_mod.effective_params(blocking_scope, path)
        assert exc.value.scope == blocking_scope

        for other in ("cost", "pricing", "alert"):
            if other == blocking_scope:
                continue
            assert params_mod.effective_params(other, path), (
                "%s 的 pending 不应阻断 %s 作用域" % (blocking_scope, other))

    @pytest.mark.parametrize("scope,section,key", [
        ("cost", "yield_rates", "大白菜"),
        ("pricing", "pricing", "target_margin"),
        ("alert", "alert", "threshold"),
    ])
    def test_input_required_passes_each_scope_gate(self, tmp_path, scope, section, key):
        """``input_required`` 在**三个作用域**都放行门控（值不进可用集）。

        与 pending 的关键差别："本不由参数包承载"不阻断该作用域，只把值的提供
        责任推给运行时。若某一 scope 把它当成 pending 处理，就是"放行"语义漏了一半。
        """
        payload = _base_payload()
        payload[section][key]["status"] = "input_required"
        path = _write_params(tmp_path, payload)

        effective = params_mod.effective_params(scope, path)
        assert key not in effective, "%s 的 input_required 条目值不得进入计算路径" % scope

    def test_scope_report_lists_all_three_states(self, tmp_path):
        payload = _base_payload()
        payload["alert"]["threshold"]["status"] = "pending"
        payload["yield_rates"]["娃娃菜"] = {
            "value": "0.88", "status": "input_required",
            "source": {"kind": "builtin_experience", "ref": "plan/02"},
        }
        path = _write_params(tmp_path, payload)
        data = params_mod.load_params(path)
        cost_report = params_mod.scope_report(data, "cost")
        assert "大白菜" in cost_report["verified"]
        assert "娃娃菜" in cost_report["input_required"]
        alert_report = params_mod.scope_report(data, "alert")
        assert "threshold" in alert_report["pending"]

    def test_unregistered_scope_rejected(self, tmp_path):
        path = _write_params(tmp_path, _base_payload())
        with pytest.raises(params_mod.ParamsError):
            params_mod.effective_params("nope", path)

    def test_unregistered_status_rejected(self, tmp_path):
        path = _write_params(tmp_path, _base_payload(status="whatever"))
        data = params_mod.load_params(path)
        with pytest.raises(params_mod.ParamsError):
            params_mod.scope_report(data, "cost")


class TestSourceRequirement:
    def test_missing_source_rejected(self, tmp_path):
        """未挂来源的参数不得进入计算路径。"""
        payload = _base_payload()
        del payload["yield_rates"]["大白菜"]["source"]
        path = _write_params(tmp_path, payload)
        with pytest.raises(params_mod.SourceMissing):
            params_mod.effective_params("cost", path)

    def test_unregistered_source_kind_rejected(self, tmp_path):
        payload = _base_payload()
        payload["yield_rates"]["大白菜"]["source"]["kind"] = "official"
        path = _write_params(tmp_path, payload)
        with pytest.raises(params_mod.SourceMissing):
            params_mod.effective_params("cost", path)

    @pytest.mark.parametrize("scope,section,key", [
        ("cost", "yield_rates", "大白菜"),
        ("pricing", "pricing", "target_margin"),
        ("alert", "alert", "threshold"),
    ])
    def test_source_missing_blocks_every_scope(self, tmp_path, scope, section, key):
        """**每个 scope 都要有 source 门**——只守 cost 会让 pricing/alert 静默溜过。"""
        payload = _base_payload()
        del payload[section][key]["source"]
        path = _write_params(tmp_path, payload)
        with pytest.raises(params_mod.SourceMissing):
            params_mod.effective_params(scope, path)

    def test_source_missing_is_a_value_error(self):
        """``SourceMissing`` 必须能被 CLI 的 ``except ValueError`` 捕获。

        继承裸 ``Exception`` 会让它从 CLI 逃逸成未捕获 traceback——那等于把
        "该报的错（exit 2）"变成"崩了"。plan/04 §三 明确列为失败路径。
        """
        from rcc.model import SourceMissing

        assert issubclass(SourceMissing, ValueError)
        assert SourceMissing.code == "source_missing"

    def test_source_is_validated_at_consumption_point_not_only_construction(self):
        """**消费点校验**：来源对象来自解析后的外部文件时也必须被校验。

        ``make_source`` 的构造期校验只守"自己造的那一半"；来自 JSON 的来源对象
        不经过它。故 ``pipeline._sourced`` 在消费点显式调用 ``validate_source``。
        """
        from rcc.engine import pipeline
        from rcc.model import SourceMissing

        with pytest.raises(SourceMissing):
            pipeline._sourced(None, "测试参数")
        with pytest.raises(SourceMissing):
            pipeline._sourced({"kind": "official", "ref": "x"}, "测试参数")
        # 合法来源透传返回
        good = {"kind": "user", "ref": "plan/02", "date": None, "note": None}
        assert pipeline._sourced(good, "测试参数") is good

    def test_source_error_names_the_parameter(self):
        """报错必须**点名是哪个参数**没挂来源——只报"参数未挂来源"用户不知道该补哪个。"""
        from rcc.engine import pipeline
        from rcc.model import SourceMissing

        with pytest.raises(SourceMissing) as exc:
            pipeline._sourced(None, "净料率")
        assert "净料率" in str(exc.value)


class TestFrozenParams:
    def test_shipped_params_is_verified(self, params_path):
        """随包参数包必须可加载且三作用域均放行。"""
        data = params_mod.load_params(params_path)
        for scope in ("cost", "pricing", "alert"):
            assert params_mod.effective_params(scope, params_path), scope
        assert data["yield_rates"]

    def test_shipped_params_rates_in_range(self, params_path):
        from rcc.model import to_decimal

        data = params_mod.load_params(params_path)
        for name, entry in data["yield_rates"].items():
            rate = to_decimal(entry["value"])
            assert Decimal(0) < rate <= Decimal(1), name
