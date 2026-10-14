"""脱敏审计门（随全量测试常驻）。

**为什么随测试常驻**：发布期才发现"仓库里有真实个人信息"的代价是 filter-repo 全历史
重写；随每次测试跑一次，成本几乎为零，且能在提交前就拦住。

三道机制：
1. 扫描器 `--selftest` 阳性/阴性对照（防扫描器本身失效）；
2. 四模式扫描 HARD 必须为 0；
3. **历史通道探活**（防"多 rev 的 git grep 静默 0 命中"造成全历史干净的假绿）。
"""

import os
import re
import subprocess
import sys

import pytest


def _run_audit(repo_root, *args):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, os.path.join(repo_root, "tools", "audit_desensitize.py")]
    cmd.extend(args)
    proc = subprocess.run(cmd, capture_output=True, cwd=repo_root, env=env)
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


def test_audit_selftest_passes(repo_root):
    """扫描器阳性/阴性对照——无自检的扫描器可能一直是空扫。"""
    code, out, err = _run_audit(repo_root, "--selftest")
    assert code == 0, out + err
    assert "AUDIT_SELFTEST_OK" in out


def test_audit_tracked_is_clean(repo_root):
    """已跟踪文件 HARD 必须为 0。"""
    code, out, err = _run_audit(repo_root, "--mode", "tracked")
    assert code == 0, out + err
    assert "DESENSITIZE_AUDIT_OK" in out


def test_audit_messages_is_clean(repo_root):
    """提交信息 HARD 必须为 0（元数据是内容扫描覆盖不到的盲区）。"""
    code, out, err = _run_audit(repo_root, "--mode", "messages")
    assert code == 0, out + err


def _has_git(repo_root):
    """该树是否有 ``.git``（``git archive`` 导出树天然没有）。"""
    return os.path.isdir(os.path.join(repo_root, ".git"))


def test_audit_history_channel_is_not_vacuous(repo_root):
    """**历史通道探活**：确认历史扫描真能读到 blob 内容。

    多 rev 的 ``git grep`` 会静默 0 命中，造成"全历史干净"的假绿——
    所以必须用必然存在的串做阳性对照。

    无 ``.git`` 的树（导出树/发布包）跳过：历史通道本身不可达，属**声明式跳过**
    而非"验过了"。CI 与开发机都有 .git，本门在实际发布流程中必然执行。
    """
    if not _has_git(repo_root):
        pytest.skip("该树无 .git（导出树）——历史通道不可达，历史扫描由 CI/开发机覆盖")

    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import audit_desensitize

    assert audit_desensitize._history_channel_probe(), "历史扫描通道探活失败"

    probe_rules = [("probe", re.compile("菜谱"), audit_desensitize.ADVISORY)]
    hits = audit_desensitize.scan_history(probe_rules, "@users.noreply.github.com")
    assert hits, "历史扫描对必然存在的串返回 0 命中（空扫假绿）"


def test_audit_commit_metadata_has_no_real_email(repo_root):
    """提交元数据邮箱单独检查——内容级扫描不覆盖 git 元数据。

    无 ``.git`` 的树跳过（同上）。
    """
    if not _has_git(repo_root):
        pytest.skip("该树无 .git（导出树）——提交元数据不可达，由 CI/开发机覆盖")

    env = dict(os.environ)
    proc = subprocess.run(["git", "log", "--format=%ae %ce", "--all"],
                          capture_output=True, cwd=repo_root, env=env,
                          encoding="utf-8", errors="replace")
    addresses = set()
    for line in (proc.stdout or "").splitlines():
        for addr in line.split():
            if addr:
                addresses.add(addr)
    assert addresses, "未取到任何提交邮箱（命令通道有问题？）"
    offenders = [a for a in addresses
                 if not a.endswith("@users.noreply.github.com")
                 and not a.endswith(("@example.com", "@example.org"))]
    assert not offenders, "提交元数据含非 noreply 邮箱（发布前必须改写）: %s" % offenders


def test_audit_works_without_git(repo_root, tmp_path):
    """**无 .git 兜底**：导出树里审计器必须仍能扫 tracked 通道（不整批报错）。"""
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import audit_desensitize

    # 模拟无 git：临时指向一个无 .git 的目录
    original = audit_desensitize.REPO_ROOT
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "sample.py").write_text("x = 1\n", encoding="utf-8")
    try:
        audit_desensitize.REPO_ROOT = str(export_dir)
        assert not audit_desensitize._has_git()
        tokens = audit_desensitize.compute_tokens()
        rules, noreply = audit_desensitize.build_rules(tokens)
        files = list(audit_desensitize._tracked_files())
        assert files, "无 git 时文件系统兜底遍历返回空（兜底失效）"
        # 历史/提交信息通道在无 git 时返回空（由调用方显式声明跳过）
        assert audit_desensitize.scan_history(rules, noreply) == []
        assert audit_desensitize.scan_messages(rules, noreply) == []
    finally:
        audit_desensitize.REPO_ROOT = original


def test_audit_hard_scan_is_not_vacuous(repo_root):
    """**机制探活**：注入一个合成邮箱 → 扫描必须报红。

    夹具程序化合成（片段拼接），源码里无任何真实邮箱词面。
    """
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import audit_desensitize

    tokens = audit_desensitize.compute_tokens()
    rules, noreply = audit_desensitize.build_rules(tokens)
    fake = "probe" + "user" + "@" + "probe" + "host" + "." + "net"
    hits = audit_desensitize.scan_text("contact: %s" % fake, rules, noreply, "<probe>")
    assert any(hit[2] == "email" and hit[3] == audit_desensitize.HARD for hit in hits), \
        "合成邮箱未被判 HARD（扫描器失效）"


def test_audit_exempts_noreply_and_git_transport(repo_root):
    """豁免口径：noreply 目标形态与 git 传输地址**不得**判 HARD。"""
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import audit_desensitize

    tokens = audit_desensitize.compute_tokens()
    rules, noreply = audit_desensitize.build_rules(tokens)
    text = ("email: 282769740+yuluo554" + noreply + "\n"
            "remote: git@github.com:user/repo.git\n")
    hits = [hit for hit in audit_desensitize.scan_text(text, rules, noreply, "<probe>")
            if hit[2] == "email"]
    assert not hits, "noreply 或 git 传输地址被误判 HARD: %s" % hits


def test_audit_output_is_masked(repo_root):
    """审计输出必须掩码化——输出本身不得成为二次泄漏源。

    夹具**程序化拼接**（源码里不留真实邮箱形态，否则审计器扫到自己）。
    """
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import audit_desensitize

    local = "real" + "user"
    domain = "some" + "company" + "." + "cn"
    masked = audit_desensitize._mask(local + "@" + domain)
    assert "realuser" not in masked and "***" in masked, "掩码未生效: %s" % masked
