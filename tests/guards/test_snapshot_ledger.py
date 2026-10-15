"""快照台账门（M1 数据先行）。

守三件"本地看着有、其实已失效"的事：

1. **快照位级一致**：原始件 sha256 与台账登记值一致，且台账/README 与磁盘实况
   同源——**只写 sha256 不重算 = 台账是抄来的，不是验过的**；
2. **多期可区分**：≥3 个不同数据日，且两两不同——"两期退化成同一期"是本模块的
   头号陷阱（`startDate` 被静默忽略的形态），退化后涨跌幅全 0 却像"无异常"；
3. **抓取器带自检**：`--selftest` 必须真能检出篡改（防"恒绿假门"）。
"""

import json
import os
import subprocess
import sys

import pytest

SNAPSHOT_DIR = ("data", "snapshots")
FETCHER = ("tools", "fetch_snapshots.py")


def _run_tool(repo_root, *args):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, os.path.join(repo_root, FETCHER[0], FETCHER[1])]
    cmd.extend(args)
    proc = subprocess.run(cmd, capture_output=True, cwd=repo_root, env=env)
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


def _snapshot_dir(repo_root):
    return os.path.join(repo_root, *SNAPSHOT_DIR)


def _metas(repo_root):
    directory = _snapshot_dir(repo_root)
    if not os.path.isdir(directory):
        return []
    out = []
    for filename in sorted(os.listdir(directory)):
        if filename.endswith(".meta.json"):
            with open(os.path.join(directory, filename), "r", encoding="utf-8") as fh:
                out.append((filename, json.load(fh)))
    return out


def test_fetcher_selftest_passes(repo_root):
    """离线阳性/阴性对照——无自检的校验器可能一直是空扫。"""
    code, out, err = _run_tool(repo_root, "--selftest")
    assert code == 0, out + err
    assert "SNAPSHOT_SELFTEST_OK" in out


def test_snapshot_check_is_byte_identical(repo_root):
    """`--check` 离线位级一致（重算 sha256 + 台账同源）。"""
    code, out, err = _run_tool(repo_root, "--check")
    assert code == 0, out + err
    assert "SNAPSHOT_CHECK_OK" in out


def test_snapshots_cover_three_distinct_dates(repo_root):
    """M1 DoD：≥3 个**可区分**数据日。"""
    metas = _metas(repo_root)
    assert len(metas) >= 3, "快照不足 3 份（M1 DoD）"
    dates = [meta.get("data_date") for _f, meta in metas]
    assert all(dates), "快照缺 data_date（无法区分期间）: %s" % dates
    assert len(set(dates)) == len(dates), "存在重复数据日（期间不可区分）: %s" % dates


def test_every_snapshot_has_capture_date_and_sha256(repo_root):
    """台账三要素：抓取日期 + URL + sha256，缺一不可。"""
    metas = _metas(repo_root)
    assert metas, "无任何快照元数据"
    for filename, meta in metas:
        assert meta.get("captured_date"), "%s 缺抓取日期" % filename
        assert meta.get("url"), "%s 缺来源 URL" % filename
        sha = meta.get("sha256") or ""
        assert len(sha) == 64, "%s 的 sha256 形态不对: %r" % (filename, sha)
        assert meta.get("response_file"), "%s 缺原始响应文件名" % filename


def test_ledger_matches_disk_recomputation(repo_root):
    """台账 sha256 必须等于**实算**值（防"台账是抄的、从没验过"）。"""
    import hashlib

    directory = _snapshot_dir(repo_root)
    ledger_path = os.path.join(directory, "ledger.json")
    assert os.path.isfile(ledger_path), "台账 ledger.json 缺失"
    with open(ledger_path, "r", encoding="utf-8") as fh:
        ledger = json.load(fh)

    assert ledger.get("entry_count") == len(ledger.get("entries") or [])
    for entry in ledger["entries"]:
        raw_path = os.path.join(directory, entry["response_file"])
        assert os.path.isfile(raw_path), "台账指向的原始件缺失: %s" % entry["response_file"]
        with open(raw_path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        assert digest == entry["sha256"], (
            "%s 台账 sha256 与实算不符（台账未经验证？）" % entry["response_file"])


def test_snapshot_raw_files_have_no_cr(repo_root):
    """原始件字节冻结：`-text` 已标，不得含 CR（否则 sha256 跨机失配）。"""
    directory = _snapshot_dir(repo_root)
    offenders = []
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".json") or filename.endswith(".meta.json"):
            continue
        with open(os.path.join(directory, filename), "rb") as fh:
            if b"\r" in fh.read():
                offenders.append(filename)
    assert not offenders, "快照原始件含 CR（EOL 会改写字节）: %s" % offenders


def test_gitattributes_freezes_snapshots(repo_root):
    """`.gitattributes` 必须把快照目录标 `-text`（防检出时 EOL 归一改写字节）。"""
    with open(os.path.join(repo_root, ".gitattributes"), "r",
              encoding="utf-8", newline="") as fh:
        content = fh.read()
    assert "data/snapshots/** -text" in content, "快照目录未标 -text"


def test_check_detects_tampered_snapshot(repo_root, tmp_path):
    """**机制探活**：篡改一份快照副本 → `--check` 必须报红。

    在仓库树外造一份带篡改的完整快照目录（复制真实件后改一字节），
    直接调 `verify()`——证明校验器真在读盘重算，而不是恒绿。
    """
    import hashlib
    import shutil

    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import fetch_snapshots

    source = _snapshot_dir(repo_root)
    probe = tmp_path / "snapshots"
    shutil.copytree(source, str(probe))

    # 先断言干净副本通过（否则后面的报红不能归因于篡改）
    assert fetch_snapshots.verify(str(probe)) == []

    target = None
    for filename in sorted(os.listdir(str(probe))):
        # 只挑原始响应件（ledger.json 排序在前且不含行情字段，篡改它测不到东西）
        if filename.startswith("xinfadi-") and filename.endswith(".json"):
            target = os.path.join(str(probe), filename)
            break
    assert target, "找不到可篡改的原始件"

    with open(target, "rb") as fh:
        raw = fh.read()
    tampered = raw.replace(b'"avgPrice":"0.', b'"avgPrice":"9.', 1)
    assert tampered != raw, "篡改动作未生效（模式没命中，测试自身失效）"
    with open(target, "wb") as fh:
        fh.write(tampered)

    drift = fetch_snapshots.verify(str(probe))
    assert any("位级不一致" in item for item in drift), (
        "篡改原始件未被检出（校验器空扫）: %s" % drift)

    # 篡改后 sha256 确实变了（证明替换动作生效）
    with open(target, "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() != hashlib.sha256(raw).hexdigest()


def test_alert_rejects_degenerate_same_period(repo_root, tmp_path):
    """**两期退化守卫**：同一份快照当两期 → 必须拒绝（exit 2），不产出"全平"假结果。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = (os.path.join(repo_root, "src") + os.pathsep
                         + env.get("PYTHONPATH", ""))
    same = os.path.join(*SNAPSHOT_DIR, "xinfadi-2026-08-06.json")
    proc = subprocess.run(
        [sys.executable, "-m", "rcc.cli", "run", "--with-alert",
         "--purchases", "data/samples/purchases-demo.csv",
         "--bom", "data/samples/bom-demo.json",
         "--snapshots", same, same],
        capture_output=True, cwd=repo_root, env=env)
    assert proc.returncode == 2, proc.stderr.decode("utf-8", "replace")
    assert "同一期" in proc.stderr.decode("utf-8", "replace")


def test_alert_reports_distinct_data_dates(repo_root):
    """两期快照的数据日必须在结果里**可区分**（旧 2026-08-06 / 新 2026-10-06）。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = (os.path.join(repo_root, "src") + os.pathsep
                         + env.get("PYTHONPATH", ""))
    old = os.path.join(*SNAPSHOT_DIR, "xinfadi-2026-08-06.json")
    new = os.path.join(*SNAPSHOT_DIR, "xinfadi-2026-10-06.json")
    proc = subprocess.run(
        [sys.executable, "-m", "rcc.cli", "run", "--json", "--with-alert",
         "--purchases", "data/samples/purchases-demo.csv",
         "--bom", "data/samples/bom-demo.json",
         "--snapshots", old, new],
        capture_output=True, cwd=repo_root, env=env)
    payload = json.loads(proc.stdout.decode("utf-8", "replace"))
    alert = payload["alert"]
    assert alert["old_snapshot"]["date"] == "2026-08-06", alert["old_snapshot"]
    assert alert["new_snapshot"]["date"] == "2026-10-06", alert["new_snapshot"]
    assert alert["old_snapshot"]["date"] != alert["new_snapshot"]["date"]
    # 抓取日保留（留档可复现性）
    assert alert["old_snapshot"]["captured_date"], "缺抓取日"


def test_snapshot_load_requires_meta(repo_root, tmp_path):
    """**未挂来源不得进入计算路径**：缺 meta.json 即抛错。"""
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc.io import snapshot as snapshot_mod

    orphan = tmp_path / "orphan.json"
    with open(str(orphan), "w", encoding="utf-8", newline="\n") as fh:
        fh.write('{"list": []}')
    with pytest.raises(ValueError) as exc:
        snapshot_mod.load_snapshot(str(orphan))
    assert "来源元数据" in str(exc.value)
