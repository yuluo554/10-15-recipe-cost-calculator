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
    """已登记套件应可跑；M4 起五套件全部达标 → 整体退出码 0。"""
    code, out, _err = _run_cli(repo_root, "bench", "--only", "boundary")
    assert code == 0, out
    assert "达标" in out

    code, out, _err = _run_cli(repo_root, "bench", "--only", "reconcile")
    assert code == 0, out


def test_bench_all_five_suites_pass(repo_root):
    """M4 DoD：五套件基准达标（真值库已入库，样本驱动层不再 not_enabled）。"""
    code, out, _err = _run_cli(repo_root, "bench")
    assert code == 0, out
    assert "总判: 达标" in out
    for suite in ("import", "costcard", "alert", "boundary", "reconcile"):
        assert suite in out, "输出缺套件 %s" % suite
    assert "未启用" not in out, "真值库已入库，不应再有未启用套件"


def test_bench_exit_code_matches_printed_verdict(repo_root):
    """退出码必须与打印的总判一致（不得"打印未达标、退出码 0"）。"""
    code, out, _err = _run_cli(repo_root, "bench")
    verdict_ok = "总判: 达标" in out
    assert code == (0 if verdict_ok else 1), (
        "CLI 退出码与打印的总判不一致（退出码语义漂移）:\n%s" % out)


def test_bench_reports_coverage_dual_registration(repo_root):
    """覆盖度双登记（分母 + 分子）必须出现在输出里——只写分子即假覆盖。"""
    code, out, _err = _run_cli(repo_root, "bench", "--only", "import")
    assert code == 0, out
    assert "覆盖度" in out, "基准输出未声明覆盖度"
    assert "形态" in out, "覆盖度未写出分母（形态总数）"


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


# ------------------------------------------------- 核算引擎失败路径（M3）
#
# **退出码语义**：行级问题 → exit 1（降级完成，清单里能看见）；
# 形态/输入不可用 → exit 2。两者混淆会让"部分可用"被当成"完全不可用"。

def _params_copy(repo_root, tmp_path, mutate, name="params-m3.json"):
    """复制随包参数包并施加改动。"""
    import json

    with open(os.path.join(repo_root, "data", "rules", "params.json"),
              encoding="utf-8") as fh:
        payload = json.load(fh)
    mutate(payload)
    path = tmp_path / name
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return str(path)


def test_target_margin_one_is_exit_2(repo_root, tmp_path):
    """``target_margin = 1.0`` → 拒绝（**非除零**）→ exit 2。"""
    path = _params_copy(
        repo_root, tmp_path,
        lambda p: p["pricing"]["target_margin"].update({"value": "1.0"}))
    code, _out, err = _run_cli(repo_root, "run", "--params", path,
                               "--purchases", SAMPLE, "--bom", BOM)
    assert code == 2, "target_margin=1 应走输入不可用 exit 2，实际 %d\n%s" % (code, err)
    assert "小于 1" in err, "报错未说明真因:\n%s" % err


def test_old_price_zero_in_snapshot_is_exit_2(repo_root, tmp_path):
    """``old_price = 0`` → 拒绝（**非除零**，缺对比基准）→ exit 2。

    用真实快照副本把某食材的旧价改为 0，验证 F5 的前提校验在端到端通路上生效。
    选 08-06 快照的**首条记录**（大白菜，且被样例 BOM 引用）——若选一个 BOM 不
    引用的食材，F5 根本不会被触发，测试就变成了"恒真假门"。
    """
    import json

    snap_src = os.path.join(repo_root, "data", "snapshots", "xinfadi-2026-08-06.json")
    with open(snap_src, encoding="utf-8") as fh:
        payload = json.load(fh)
    target = payload["list"][0]["prodName"]
    # 断言该食材确被样例 BOM 引用（否则本测试测的不是被测的那件事）
    with open(os.path.join(repo_root, "data", "samples", "bom-demo.json"),
              encoding="utf-8") as fh:
        bom_payload = json.load(fh)
    bom_foods = {item["food"] for dish in bom_payload["dishes"]
                 for item in dish["items"]}
    assert target in bom_foods, (
        "选中的旧价置零食材 %r 未被样例 BOM 引用——F5 不会被触发（假门）" % target)

    # 只保留该食材这一条并置零（其余同名记录会覆盖，需剔除）
    payload["list"][0]["avgPrice"] = "0"
    payload["list"] = [r for index, r in enumerate(payload["list"])
                       if r.get("prodName") != target or index == 0]
    snap = tmp_path / "old-zero.json"
    with open(str(snap), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False))
    meta = tmp_path / "old-zero.meta.json"
    with open(str(meta), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"captured_date": "2026-10-15", "data_date": "2026-08-06",
                             "url": "local", "unit": "元/斤", "note": "测试副本"}))

    new_snap = os.path.join(repo_root, "data", "snapshots", "xinfadi-2026-10-06.json")
    code, _out, err = _run_cli(repo_root, "run", "--with-alert",
                               "--purchases", SAMPLE, "--bom", BOM,
                               "--snapshots", str(snap), new_snap)
    assert code == 2, "旧价为 0 应被拒绝（exit 2），实际 %d\n%s" % (code, err)
    assert "大于 0" in err or "缺对比基准" in err, \
        "旧价为 0 的拒绝原因未说明:\n%s" % err


def test_yield_rate_out_of_range_is_degraded_not_aborted(repo_root, tmp_path):
    """净料率越界 → **该行 invalid 并入清单**，退出码 1（其余菜品照常出数）。"""
    path = _params_copy(
        repo_root, tmp_path,
        lambda p: p["yield_rates"]["大白菜"].update({"value": "1.5"}))
    code, out, err = _run_cli(repo_root, "run", "--json", "--params", path,
                              "--purchases", SAMPLE, "--bom", BOM)
    assert code == 1, "行级问题应 exit 1（降级完成），实际 %d\n%s" % (code, err)
    import json

    payload = json.loads(out)
    codes = [w.get("code") for w in payload["warnings"]]
    assert "yield_rate_out_of_range" in codes, "越界未列入异常清单"
    dishes = [c["dish"] for c in payload["cards"]]
    assert "醋溜白菜" not in dishes, "越界的那道菜必须被排除"
    assert len(dishes) == 4, "其余菜品必须照常算出（不中断整批）"


def test_all_yield_rates_out_of_range_is_exit_2(repo_root, tmp_path):
    """全部菜品被排除 → 成本卡为空 → 输入不可用 exit 2（不产出"0 道菜"）。"""
    path = _params_copy(
        repo_root, tmp_path,
        lambda p: [p["yield_rates"][k].update({"value": "1.5"})
                   for k in p["yield_rates"]])
    code, _out, err = _run_cli(repo_root, "run", "--params", path,
                               "--purchases", SAMPLE, "--bom", BOM)
    assert code == 2, err
    assert "成本卡为空" in err


def test_missing_source_is_exit_2_not_traceback(repo_root, tmp_path):
    """``source`` 缺失 → ``source_missing`` 拒绝 → exit 2（**不是未捕获 traceback**）。"""
    path = _params_copy(
        repo_root, tmp_path,
        lambda p: p["yield_rates"]["大白菜"].pop("source"))
    code, _out, err = _run_cli(repo_root, "run", "--params", path,
                               "--purchases", SAMPLE, "--bom", BOM)
    assert code == 2, "缺来源应走 exit 2，实际 %d\n%s" % (code, err)
    assert "Traceback" not in err, "缺来源不应逃逸成未捕获异常:\n%s" % err


@pytest.mark.parametrize("name,payload,expect", [
    ("no-dishes.json", "{}", "缺少 dishes"),
    ("empty-dishes.json", '{"dishes": []}', "为空"),
    ("no-name.json", '{"dishes": [{"items": [{"food": "大白菜", "qty": "1"}]}]}',
     "缺少 name"),
    ("missing-food.json",
     '{"dishes": [{"name": "测试菜", "items": [{"food": "不存在食材X", "qty": "1"}]}]}',
     "不存在的食材"),
])
def test_bom_shape_failures_are_exit_2(repo_root, tmp_path, name, payload, expect):
    """BOM 形态失败四条 → 一律 exit 2（**整份文件的形态问题，不是某一行的问题**）。"""
    bom = tmp_path / name
    with open(str(bom), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(payload)
    code, _out, err = _run_cli(repo_root, "run", "--purchases", SAMPLE, "--bom", str(bom))
    assert code == 2, "BOM 形态问题应为 exit 2，实际 %d\n%s" % (code, err)
    assert expect in err, "报错未说明真因（期望含 %r）:\n%s" % (expect, err)


def test_missing_rate_entry_is_exit_2_not_defaulted(repo_root, tmp_path):
    """``input_required``：本不由参数包承载的净料率缺失 → exit 2，**不静默取默认值**。"""
    bom = tmp_path / "bom.json"
    with open(str(bom), "w", encoding="utf-8", newline="\n") as fh:
        fh.write('{"dishes": [{"name": "测试菜", "items": [{"food": "未知食材X", "qty": "1"}]}]}')
    purchases = tmp_path / "p.csv"
    with open(str(purchases), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("日期,品名,类别,数量,单位,单价,金额\n"
                 "2026-10-01,未知食材X,其他,10,斤,3.00,30.00\n")
    code, _out, err = _run_cli(repo_root, "run",
                               "--purchases", str(purchases), "--bom", str(bom))
    assert code == 2, err
    assert "净料率" in err

