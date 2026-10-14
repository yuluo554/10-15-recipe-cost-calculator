"""CLI 端到端与退出码语义测试。

**退出码语义锁进测试**（重构不漂移）：

=== ==========================================
0   完成 / 全部合规 / 基准达标
1   降级完成（有异常行或未启用套件）/ 检出问题
2   输入不可用 / 用法错误
3   缺可选依赖
=== ==========================================
"""

import os
import subprocess
import sys

import pytest


def _run_cli(repo_root, *args):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # 子进程不继承测试进程的 sys.path——显式指向 src/，让套件在
    # "未安装该解释器的包"时也能跑（本机 3.8 与 3.12 双通道验证用）。
    src = os.path.join(repo_root, "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run([sys.executable, "-m", "rcc.cli"] + list(args),
                          capture_output=True, cwd=repo_root, env=env)
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


def test_version(repo_root):
    code, out, _err = _run_cli(repo_root, "--version")
    assert code == 0
    assert "recipe-cost-calculator" in out


def test_no_command_is_usage_error(repo_root):
    code, _out, _err = _run_cli(repo_root)
    assert code == 2, "无子命令应返回用法错误 2"


def test_run_with_samples_is_degraded(repo_root):
    """样例含刻意注入的异常行 → 退出码 1（降级完成，明示语义）。"""
    code, out, err = _run_cli(repo_root, "run",
                              "--purchases", "data/samples/purchases-demo.csv",
                              "--bom", "data/samples/bom-demo.json")
    assert code == 1, err
    assert "异常" in out and "未静默跳过" in out


def test_run_reports_anomaly_rows_not_silently_skipped(repo_root):
    """**异常行必须列入清单并计数**，绝不静默丢弃后报告"导入成功"。"""
    code, out, _err = _run_cli(repo_root, "run", "--json",
                               "--purchases", "data/samples/purchases-demo.csv",
                               "--bom", "data/samples/bom-demo.json")
    assert code == 1
    import json

    payload = json.loads(out)
    assert payload["warnings"], "异常行清单为空（被静默跳过了？）"
    reasons = " ".join(w["reason"] for w in payload["warnings"])
    assert "非数值" in reasons, "非数值行未列入清单"
    assert "mapping_uncertain" in reasons, "未登记列名未列入清单（第三态缺失）"
    assert "为空" in reasons, "必填列为空未列入清单"


def test_run_missing_input_is_usage_error(repo_root):
    code, _out, err = _run_cli(repo_root, "run", "--purchases", "nope.csv",
                               "--bom", "data/samples/bom-demo.json")
    assert code == 2, err


def test_run_alert_without_two_snapshots_is_usage_error(repo_root):
    code, _out, err = _run_cli(repo_root, "run", "--with-alert",
                               "--purchases", "data/samples/purchases-demo.csv",
                               "--bom", "data/samples/bom-demo.json")
    assert code == 2, err
    assert "两期快照" in err


def test_check_reports_issues(repo_root):
    code, out, _err = _run_cli(repo_root, "check",
                               "--purchases", "data/samples/purchases-demo.csv",
                               "--bom", "data/samples/bom-demo.json")
    assert code == 1, "check 检出问题应返回 1"


def test_bench_unknown_suite_is_usage_error(repo_root):
    """``--only`` 传未知名必须走 exit 2——否则"跑了个不存在的基准"会被读成成功。"""
    code, _out, err = _run_cli(repo_root, "bench", "--only", "nope")
    assert code == 2, err
    assert "未登记" in err


def test_bench_registered_suites_run(repo_root):
    """已登记套件应可跑（真值库未生成 → 样本驱动套件 not_enabled，退出码 1）。"""
    code, out, _err = _run_cli(repo_root, "bench", "--only", "boundary")
    assert code == 0, out
    assert "达标" in out

    code, out, _err = _run_cli(repo_root, "bench", "--only", "reconcile")
    assert code == 0, out


def test_bench_not_enabled_does_not_fake_pass(repo_root):
    """**未启用套件不冒充通过**：空分母 → exit 1 + 显式声明。"""
    code, out, _err = _run_cli(repo_root, "bench", "--only", "import")
    assert code == 1, "空分母套件应返回 1（不冒充通过），实际 %d\n%s" % (code, out)
    assert "未启用" in out


def test_selftest_passes_in_source_mode(repo_root):
    code, out, _err = _run_cli(repo_root, "selftest")
    assert code == 0, out
    assert '"frozen": false' in out


def test_selftest_writes_file_when_out_given(repo_root, tmp_path):
    """窗口版无 stdout——``--out`` 是唯一能脚本化验收的通路。"""
    import json

    out_file = tmp_path / "selftest.json"
    code, _out, _err = _run_cli(repo_root, "selftest", "--out", str(out_file))
    assert code == 0
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["frozen"] is False


def test_report_files_written(repo_root, tmp_path):
    prefix = str(tmp_path / "report")
    code, _out, err = _run_cli(repo_root, "run", "--report", prefix,
                               "--purchases", "data/samples/purchases-demo.csv",
                               "--bom", "data/samples/bom-demo.json")
    assert code == 1, err
    assert os.path.isfile(prefix + ".md")
    assert os.path.isfile(prefix + ".xlsx")


def test_missing_ingredient_yield_rate_is_usage_error(repo_root, tmp_path):
    """``input_required`` 语义：本不由参数包承载的输入缺失 → exit 2，**不静默取默认值**。"""
    bom = tmp_path / "bom.json"
    with open(str(bom), "w", encoding="utf-8", newline="\n") as fh:
        fh.write('{"dishes": [{"name": "测试菜", "items": [{"food": "未知食材X", "qty": "1"}]}]}')
    purchases = tmp_path / "p.csv"
    with open(str(purchases), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("日期,品名,类别,数量,单位,单价,金额\n2026-10-01,未知食材X,其他,10,斤,3.00,30.00\n")
    code, _out, err = _run_cli(repo_root, "run",
                               "--purchases", str(purchases), "--bom", str(bom))
    assert code == 2, err
    assert "净料率" in err


def test_pending_param_blocks_with_exit_1(repo_root, tmp_path):
    """pending 条目阻断判定路径 → exit 1 + 打印未启用清单。"""
    import json

    params = json.loads(
        open(os.path.join(repo_root, "data", "rules", "params.json"),
             encoding="utf-8").read())
    first_food = sorted(params["yield_rates"])[0]
    params["yield_rates"][first_food]["status"] = "pending"
    path = tmp_path / "params-pending.json"
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(params, ensure_ascii=False, indent=2))

    code, _out, err = _run_cli(repo_root, "run", "--params", str(path),
                               "--purchases", "data/samples/purchases-demo.csv",
                               "--bom", "data/samples/bom-demo.json")
    assert code == 1, err
    assert "门控拦截" in err
