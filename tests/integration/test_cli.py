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


# --------------------------------------------------- 导入失败路径（M2）
#
# **形态问题 = exit 2，行问题 = exit 1**：整份文件不可用（空/坏编码/缺表头）与
# "文件可读但某几行不合格"是两种不同的退出码语义。把前者混进逐行清单，读者会去
# 改某一行；把后者报成 exit 2，则"部分可用"被当成"完全不可用"。

BOM = "data/samples/bom-demo.json"
SAMPLE = "data/samples/purchases-demo.csv"


def _write_bytes(tmp_path, payload, name):
    path = tmp_path / name
    with open(str(path), "wb") as fh:
        fh.write(payload)
    return str(path)


def _write_text(tmp_path, text, name):
    path = tmp_path / name
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return str(path)


def _bom_for(tmp_path, *foods):
    """写一个只引用给定食材的最小 BOM。

    小进货单测试必须配小 BOM：拿仓库样例 BOM（引用 10 种食材）去配 1-2 行的小进货单，
    失败原因会变成"BOM 引用了库里没有的食材"——**那测的就不是被测的那件事了**。
    """
    import json

    payload = {"schema_version": "1", "shop": "示例食堂甲",
               "dishes": [{"name": "测试菜",
                           "items": [{"food": food, "qty": "1"} for food in foods]}]}
    path = tmp_path / "bom-min.json"
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return str(path)


@pytest.mark.parametrize("name,payload,expect", [
    ("empty.csv", b"", "为空"),
    ("blank.csv", "\n \n".encode("utf-8"), "为空"),
    ("header-only.csv", "日期,品名,类别,数量,单位,单价,金额\n".encode("utf-8"),
     "只有表头"),
    ("gbk.csv", ("日期,品名,类别,数量,单位,单价,金额\n"
                 "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n").encode("gbk"),
     "不是 UTF-8"),
    ("missing-col.csv", "日期,品名,类别,单位\n2026-10-01,大白菜,蔬菜,斤\n".encode("utf-8"),
     "缺少必填列"),
])
def test_run_shape_failures_are_exit_2(repo_root, tmp_path, name, payload, expect):
    """整份文件不可用 → exit 2（**不进逐行清单**），且报错说明真因。"""
    path = _write_bytes(tmp_path, payload, name)
    code, _out, err = _run_cli(repo_root, "run", "--purchases", path, "--bom", BOM)
    assert code == 2, "形态问题应为 exit 2，实际 %d\n%s" % (code, err)
    assert expect in err, "报错未说明真因（期望含 %r）:\n%s" % (expect, err)


@pytest.mark.parametrize("name,payload,expect", [
    ("empty.csv", b"", "为空"),
    ("header-only.csv", "日期,品名,类别,数量,单位,单价,金额\n".encode("utf-8"),
     "只有表头"),
    ("gbk.csv", ("日期,品名,类别,数量,单位,单价,金额\n"
                 "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n").encode("gbk"),
     "不是 UTF-8"),
])
def test_check_shape_failures_are_exit_2(repo_root, tmp_path, name, payload, expect):
    """``check`` 与 ``run`` 对同一形态问题必须给**同一退出码**（不漂移）。"""
    path = _write_bytes(tmp_path, payload, name)
    code, _out, err = _run_cli(repo_root, "check", "--purchases", path)
    assert code == 2, "形态问题应为 exit 2，实际 %d\n%s" % (code, err)
    assert expect in err


def test_all_rows_invalid_is_exit_2_not_silent_success(repo_root, tmp_path):
    """全行异常 → 食材库为空，**不得**把错误指向 BOM。

    "BOM 引用了食材库中不存在的食材"会让用户去改 BOM——真因在进货单。
    """
    path = _write_text(tmp_path,
                       "日期,品名,类别,数量,单位,单价,金额\n"
                       "2026-10-01,,蔬菜,10,斤,0.50,5.00\n"
                       "2026-10-01,土豆,蔬菜,abc,斤,1.50,0\n", "allbad.csv")
    code, _out, err = _run_cli(repo_root, "run", "--purchases", path, "--bom", BOM)
    assert code == 2, err
    assert "无任何可用行" in err, "未指出进货单零可用行:\n%s" % err
    assert "不存在的食材" not in err, "把进货单的问题误报成了 BOM 的问题:\n%s" % err


def test_check_reports_all_rows_invalid_as_issue(repo_root, tmp_path):
    """``check`` 的职责是报告问题：零可用行 → exit 1 + 清单里有它。"""
    path = _write_text(tmp_path,
                       "日期,品名,类别,数量,单位,单价,金额\n"
                       "2026-10-01,,蔬菜,10,斤,0.50,5.00\n", "allbad.csv")
    code, out, _err = _run_cli(repo_root, "check", "--purchases", path,
                               "--bom", BOM)
    assert code == 1, "check 检出问题应 exit 1"
    assert "无任何可用行" in out


def test_structure_unparsable_row_is_reported_not_silently_dropped(repo_root, tmp_path):
    """整行结构不可解析 → 记 unknown 且**列入清单**（不静默丢弃）。

    BOM 只引用**幸存的那一行**（土豆）：结构错行的大白菜不入库，若 BOM 引用它，
    报错会变成"引用了不存在的食材"——那测的就不是"结构错行被列入清单"了。
    """
    path = _write_text(tmp_path,
                       "日期,品名,类别,数量,单位,单价,金额\n"
                       "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00,多余\n"
                       "2026-10-01,土豆,蔬菜,8,斤,1.50,12.00\n", "struct.csv")
    code, out, _err = _run_cli(repo_root, "run", "--json", "--purchases", path,
                               "--bom", _bom_for(tmp_path, "土豆"))
    assert code == 1, "有异常行应 exit 1（降级完成）"
    import json

    payload = json.loads(out)
    codes = [w["code"] for w in payload["warnings"]]
    assert "structure_unparsable" in codes, "结构不可解析的行被静默丢弃了"
    assert payload["library_size"] == 1, "仅土豆可用（结构错行不入库）"


def test_bom_header_csv_is_accepted(repo_root, tmp_path):
    """BOM（Excel 另存 CSV 的默认形态）必须能跑通——否则最常见的用户路径直接挂。"""
    payload = ("\ufeff日期,品名,类别,数量,单位,单价,金额\n"
               "2026-10-01,大白菜,蔬菜,10,斤,0.50,5.00\n").encode("utf-8")
    path = _write_bytes(tmp_path, payload, "bom.csv")
    code, out, err = _run_cli(repo_root, "check", "--purchases", path)
    assert code == 0, "带 BOM 的 CSV 应无异常，实际 %d\n%s%s" % (code, out, err)


def test_duplicate_name_uses_last_price_and_is_surfaced(repo_root, tmp_path):
    """同品名多次进货：取**最后一条**价，且该取舍在输出里可见（非隐性）。"""
    path = _write_text(tmp_path,
                       "日期,品名,类别,数量,单位,单价,金额\n"
                       "2026-10-01,土豆,蔬菜,10,斤,1.00,10.00\n"
                       "2026-10-05,土豆,蔬菜,10,斤,2.00,20.00\n", "dup.csv")
    code, out, _err = _run_cli(repo_root, "run", "--json", "--purchases", path,
                               "--bom", _bom_for(tmp_path, "土豆"))
    assert code == 0, "两行均合格，无异常行 → exit 0"
    import json

    payload = json.loads(out)
    assert payload["duplicate_food_names"] == ["土豆"]
    assert str(payload["cards"][0]["lines"][0]["purchase_unit_price"]) == "2.00", \
        "未取最后一条价"



def test_sample_import_is_reproducible_across_runs(repo_root):
    """样例导入复跑通过（M2 DoD）：同输入两次 JSON 输出逐字节一致。"""
    args = ("run", "--json", "--purchases", SAMPLE, "--bom", BOM)
    first = _run_cli(repo_root, *args)
    second = _run_cli(repo_root, *args)
    assert first[0] == second[0] == 1, first[2]
    assert first[1] == second[1], "同输入的 JSON 输出不逐字节一致（引入了非确定性）"


def test_sample_anomaly_list_is_reproducible(repo_root):
    """异常行清单可复现（M2 DoD）：重复导出，清单与计数逐条相同。"""
    import json

    seen = []
    for _ in range(2):
        code, out, _err = _run_cli(repo_root, "run", "--json",
                                   "--purchases", SAMPLE, "--bom", BOM)
        assert code == 1
        payload = json.loads(out)
        seen.append([(w["line"], w["status"], w["code"]) for w in payload["warnings"]])
        assert payload["purchases_summary"], "摘要缺失"
    assert seen[0] == seen[1], "异常行清单两次不一致"


def test_sample_covers_all_three_states(repo_root):
    """样例是三态的演示载体：ok / invalid / unknown 都要在样例上看得见。"""
    import json

    code, out, _err = _run_cli(repo_root, "run", "--json",
                               "--purchases", SAMPLE, "--bom", BOM)
    assert code == 1
    payload = json.loads(out)
    statuses = {w["status"] for w in payload["warnings"]}
    assert {"invalid", "unknown"} <= statuses
    assert payload["library_size"] > 0, "ok 行应进入食材库"

