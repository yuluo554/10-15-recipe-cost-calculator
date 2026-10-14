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
        """input_required 放行门控，但运行时必须索取——绝不静默取默认值。"""
        path = _write_params(tmp_path, _base_payload(status="input_required"))
        with pytest.raises(params_mod.ParamsInputRequired):
            params_mod.effective_params("cost", path)

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
