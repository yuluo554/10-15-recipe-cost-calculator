"""真值库守门（M4）。

守四件"看着齐全、其实已失效"的事：

1. **位级一致**：`gen_truth.py --check` 必须重生成出与入库件逐字节相同的真值库与
   manifest（手改真值凑引擎即被检出）；
2. **观测是活的**：真值库里**不得**有 `observed` 一类冻结观测——若把观测也冻进去，
   评测就退化成"比对两个冻结字典"，**引擎坏掉也照样全绿**；
3. **覆盖度双登记**：分母（形态总数）与分子（采样数）都在，且**分母由代码里的
   `ISSUE_*` 常量集反射得出**——新增一个异常代码而没配用例，分母自动变大、
   覆盖率自动下降，"悄悄做小分母"这条路被堵死；
4. **manifest 自洽**：`truth_sha256` 必须等于**实算**值（只写 sha256 不重算 =
   manifest 是抄来的，不是验过的），门槛字段齐备且不回落默认值。
"""

import hashlib
import json
import os
import subprocess
import sys

import pytest

TRUTH_DIR = ("data", "truth")
SUITES = ("import", "costcard", "alert")


def _truth_dir(repo_root):
    return os.path.join(repo_root, *TRUTH_DIR)


def _load(repo_root, name):
    with open(os.path.join(_truth_dir(repo_root), name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _run_gen_truth(repo_root, *args):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, os.path.join(repo_root, "tools", "gen_truth.py")]
    cmd.extend(args)
    proc = subprocess.run(cmd, capture_output=True, cwd=repo_root, env=env)
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


# ------------------------------------------------------------ 位级一致 + 生成器

def test_frozen_truth_bit_identical(repo_root):
    """真值库是冻结产物——重生成必须逐字节一致（手改即红）。"""
    code, out, err = _run_gen_truth(repo_root, "--check")
    assert code == 0, out + err
    assert "FROZEN_TRUTH_OK" in out


def test_frozen_truth_check_detects_drift(repo_root, tmp_path):
    """**变异验证**：改动一份真值库副本 → `--check` 必须报红。

    在仓库树外造一份完整副本（复制真实件后追加一字节），跑生成器的比对路径。
    副本必须含 `data/`（B3 用例要读快照）与 `tools/`+`src/`（生成器以自身位置推
    仓库根并从包内取参数）——否则报的是"缺输入"而不是"内容漂移"，测不到东西。
    """
    import shutil

    probe_root = _probe_repo(repo_root, tmp_path)
    target = probe_root / "data" / "truth" / "import.json"
    with open(str(target), "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n")

    proc = _run_tool(str(probe_root / "tools" / "gen_truth.py"), "--check",
                     cwd=str(probe_root))
    assert proc.returncode == 1, "改动真值库后 --check 未报红（假门）: %s" % (
        proc.stderr.decode("utf-8", "replace"))
    assert "FROZEN_TRUTH_DRIFT" in proc.stderr.decode("utf-8", "replace")


def _probe_repo(repo_root, tmp_path):
    """在仓库树外造一份可独立运行的副本（tools + src + benchmark + data）。"""
    import shutil

    probe_root = tmp_path / "repo"
    probe_root.mkdir(parents=True, exist_ok=True)
    for name in ("tools", "src", "benchmark", "data"):
        shutil.copytree(os.path.join(repo_root, name), str(probe_root / name))
    return probe_root


def _run_tool(script, *args, **kwargs):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, str(script)] + list(args),
                          capture_output=True, cwd=kwargs.get("cwd"), env=env)


def test_generator_is_deterministic_across_runs(repo_root):
    """同参数两次运行必须同结果（禁 stdlib random / set 序 / 时钟）。"""
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import importlib

    import gen_truth

    importlib.reload(gen_truth)
    first = gen_truth.build_outputs()
    importlib.reload(gen_truth)
    second = gen_truth.build_outputs()
    assert first == second, "gen_truth 两次运行结果不同（不确定）"


# ------------------------------------------------- 观测必须是活的（M4 关键）

def test_truth_libraries_hold_no_frozen_observations(repo_root):
    """真值库只准存**输入 + 期望键**——不得含冻结观测。

    若把观测冻进库，评测退化成"比对两个冻结字典"：引擎怎么改都不会红。
    本门是"活体观测"这一设计的守门。
    """
    offenders = []
    for name in SUITES:
        payload = _load(repo_root, "%s.json" % name)
        for case in payload["cases"]:
            extra = set(case) - {"id", "form", "input", "expect_keys"}
            if extra:
                offenders.append("%s/%s 含多余字段 %s" % (name, case.get("id"),
                                                        sorted(extra)))
            if "expect_keys" not in case or not case["expect_keys"]:
                offenders.append("%s/%s 缺 expect_keys" % (name, case.get("id")))
    assert not offenders, "真值库出现冻结观测或多余额外字段:\n  " + "\n  ".join(offenders)


def test_suites_are_evaluated_live_not_from_frozen_observations(repo_root, tmp_path):
    """**机制探活**：观测器必须真跑引擎——喂入不匹配的用例必报观测异常。"""
    sys.path.insert(0, os.path.join(repo_root, "benchmark"))
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from benchmark import cases as cases_mod

    record = {"id": "probe", "expect_keys": ["form:accepted"],
              "input": {"purchases_csv": "not,a,valid,header\n"}}
    # 观测器把内联 CSV 落到 workdir 再真跑解析器 → 至少产出一个结论键（非空扫）
    result = cases_mod.evaluate_case("import", record, str(tmp_path))
    assert result["observed_count"] > 0, "观测器未产出任何结论键（空扫假绿）"
    assert result["match"] is False, "期望没被证实的用例不应判为一致"


# --------------------------------------------------------- 覆盖度双登记（分母）

def test_coverage_declares_both_denominator_and_numerator(repo_root):
    """覆盖声明必须同时写出**分母（形态总数）与分子（采样数）**。

    只写分子就是假覆盖。
    """
    coverage = _load(repo_root, "manifest.json")["coverage"]
    for name in SUITES:
        entry = coverage.get(name)
        assert entry, "coverage 缺套件 %s" % name
        assert isinstance(entry.get("forms_total"), int) and entry["forms_total"] > 0, \
            "%s 的分母缺失或为 0（只写分子即假覆盖）" % name
        assert isinstance(entry.get("forms_sampled"), int), "%s 缺分子" % name
        assert entry["forms_sampled"] <= entry["forms_total"], "%s 分子超过分母" % name
        assert entry.get("sampled_forms"), "%s 缺采样清单" % name
        assert len(entry["sampled_forms"]) == entry["forms_sampled"], \
            "%s 采样清单长度与分子不符" % name
        assert entry["forms_sampled"] == entry["forms_total"], \
            "%s 有登记形态未被采样（覆盖率会虚高）" % name


def test_coverage_denominator_tracks_code_constants(repo_root):
    """**分母不能悄悄做小**：`csv_import` 的每个行级 `ISSUE_*` 代码都必须进 B1 分母。

    判据是把代码常量集与 manifest 的采样清单对照——新增一个异常代码而没配用例，
    本门立即报红（这正是"分母被悄悄做小"的检测方式）。
    """
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc.io import csv_import

    coverage = _load(repo_root, "manifest.json")["coverage"]["import"]
    sampled = set(coverage["sampled_forms"])
    row_level = {getattr(csv_import, name) for name in dir(csv_import)
                 if name.startswith("ISSUE_")} - {csv_import.ISSUE_NO_USABLE_ROWS}
    missing = sorted(row_level - sampled)
    assert not missing, "csv_import 的行级异常代码未进 B1 覆盖清单: %s" % missing


def test_costcard_denominator_tracks_pipeline_constants(repo_root):
    """同理：`pipeline` 的每个 `ISSUE_*` 代码都必须进 B2 分母。"""
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc.engine import pipeline

    coverage = _load(repo_root, "manifest.json")["coverage"]["costcard"]
    sampled = set(coverage["sampled_forms"])
    codes = {getattr(pipeline, name) for name in dir(pipeline)
             if name.startswith("ISSUE_")}
    missing = sorted(codes - sampled)
    assert not missing, "pipeline 的异常代码未进 B2 覆盖清单: %s" % missing


def test_form_registry_is_not_vacuous(repo_root, tmp_path):
    """**机制探活**：登记了却无用例采样的形态 → 生成器必须报错（不给虚高覆盖率）。"""
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import gen_truth

    cases = [{"id": "x", "form": "ok_row", "input": {}, "expect_keys": ["a"]}]
    with pytest.raises(ValueError):
        gen_truth._forms_from(cases, ["ok_row", "an_unsampled_form"])

    # 反向：用例声明的形态未登记 → 也必须报错（防"偷偷多报一个形态")
    with pytest.raises(ValueError):
        gen_truth._forms_from(cases, ["another_form"])


def test_unsampled_form_is_rejected_end_to_end(repo_root, tmp_path):
    """端到端：生成器遇到未采样形态时 exit 1 并点名（不是静默产出虚高覆盖）。"""
    probe_root = _probe_repo(repo_root, tmp_path)
    script = probe_root / "tools" / "gen_truth_probe.py"
    # 打桩脚本：在**真实仓库副本**里把 B3 的登记清单换成含一个未采样形态的版本，
    # 再跑 build_outputs()——验证生成器会主动拒绝，而不是老实产出虚高覆盖率。
    stub = (
        "import os, sys\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname("
        "os.path.abspath(__file__))), 'src'))\n"
        "import gen_truth\n"
        "gen_truth.alert_forms = lambda cases: gen_truth._forms_from(\n"
        "    cases, gen_truth.alert_registered() + ['never_sampled_form'])\n"
        "sys.exit(gen_truth.main(['--check']))\n")
    with open(str(script), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(stub)

    proc = _run_tool(script, cwd=str(probe_root))
    assert proc.returncode == 1, "未采样形态未被拒绝（覆盖率会虚高）"
    assert "never_sampled_form" in proc.stderr.decode("utf-8", "replace")


# ------------------------------------------------------------- manifest 自洽

def test_manifest_truth_sha256_matches_recomputation(repo_root):
    """`truth_sha256` 必须等于**实算**值（防"manifest 是抄的、从没验过"）。"""
    manifest = _load(repo_root, "manifest.json")
    recorded = manifest.get("truth_sha256") or {}
    for name in SUITES:
        path = os.path.join(_truth_dir(repo_root), "%s.json" % name)
        with open(path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        assert recorded.get(name) == digest, (
            "%s 的 manifest sha256 与实算不符（manifest 未经验证？）" % name)


def test_manifest_thresholds_are_strings_and_complete(repo_root):
    """门槛用字符串表示 Decimal（防 float 尾差），且五项齐备（不回落默认值）。"""
    thresholds = _load(repo_root, "manifest.json")["thresholds"]
    required = ("min_pass_rate", "max_false_positive_rate", "max_duration_seconds",
                "measures_false_positive")
    for suite in ("import", "costcard", "alert", "boundary", "reconcile"):
        entry = thresholds.get(suite)
        assert entry, "门槛缺套件 %s" % suite
        for key in required:
            assert key in entry, "套件 %s 门槛缺 %r" % (suite, key)
        for key in ("min_pass_rate", "max_false_positive_rate", "max_duration_seconds"):
            assert isinstance(entry[key], str), "%s 的 %s 应为字符串 Decimal" % (suite, key)
        assert isinstance(entry["measures_false_positive"], bool), \
            "%s 的 measures_false_positive 应为布尔（显式声明是否测误报率）" % suite


def test_rule_driven_suites_declare_false_positive_unmeasured(repo_root):
    """规则驱动层（B4/B5）没有观测键通道 → 必须显式声明**未测**误报率。

    拿一个恒 0 去比门槛是恒真假门；登记"未测"比沉默好。
    """
    thresholds = _load(repo_root, "manifest.json")["thresholds"]
    for suite in ("boundary", "reconcile"):
        assert thresholds[suite]["measures_false_positive"] is False, (
            "%s 结构上不可测误报率，必须显式声明未测" % suite)
    for suite in SUITES:
        assert thresholds[suite]["measures_false_positive"] is True, \
            "%s 是样本驱动套件，误报率应实测" % suite


# --------------------------------------------- 真值库缺失 → 未启用 → exit 1

def test_missing_truth_library_makes_bench_exit_1(repo_root, tmp_path):
    """端到端（真 CLI）：删掉真值库 → 基准必须报**未启用**且 exit 1。

    在仓库副本里跑，才改得动子进程看到的 `data/truth`——**"未启用不冒充通过"**
    必须由真命令验证，进程内 monkeypatch 证明不了 CLI 的退出码。
    """
    probe_root = _probe_repo(repo_root, tmp_path)
    for name in ("import.json", "costcard.json", "alert.json"):
        os.remove(str(probe_root / "data" / "truth" / name))

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(probe_root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run([sys.executable, "-m", "rcc.cli", "bench"],
                          capture_output=True, cwd=str(probe_root), env=env)
    out = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 1, (
        "真值库缺失应 exit 1（未启用不冒充通过），实际 %d:\n%s" % (proc.returncode, out))
    assert "未启用" in out
    assert "总判: 未达标" in out
