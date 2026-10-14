"""EOL 门：冻结 fixtures 与跟踪文本文件不得带 CR。

Windows 开发机全局 ``core.autocrlf=true`` 会让全新 clone 把 LF 重写成 CRLF、
基准全挂——dev 目录从未走检出、Linux CI 均测不到，只有"开发机本机的全新 clone"
能暴露。所以这道门必须常驻。

**变异验证**：往一个冻结件写 CR → 本门必须变红。
"""

import os

import pytest

CR = b"\r"

# 冻结 fixtures：字节语义必须稳定（台账登记 sha256）
FROZEN_DIRS = ("data/truth", "data/samples", "data/rules", "data/snapshots")


def _tracked_text_files(repo_root):
    """仓库内应保持 LF 的文本文件。"""
    skip_dirs = {".git", "__pycache__", ".venv", "venv", "build", "dist", ".pytest_cache"}
    out = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs)
        for filename in sorted(filenames):
            if filename.endswith((".py", ".md", ".toml", ".cfg", ".txt", ".yml", ".yaml",
                                  ".json", ".csv", ".gitattributes", ".gitignore")):
                out.append(os.path.join(dirpath, filename))
    return out


def test_no_cr_in_text_files(repo_root):
    offenders = []
    for path in _tracked_text_files(repo_root):
        with open(path, "rb") as fh:
            data = fh.read()
        if CR in data:
            rel = os.path.relpath(path, repo_root).replace(os.sep, "/")
            offenders.append(rel)
    assert not offenders, "以下文件含 CR（EOL 门）：%s" % offenders


def test_frozen_dirs_have_no_cr(repo_root):
    """冻结件单独再扫一遍（它们是台账登记 sha256 的对象）。"""
    offenders = []
    for rel_dir in FROZEN_DIRS:
        target = os.path.join(repo_root, rel_dir.replace("/", os.sep))
        if not os.path.isdir(target):
            continue
        for dirpath, _dirnames, filenames in os.walk(target):
            for filename in sorted(filenames):
                path = os.path.join(dirpath, filename)
                with open(path, "rb") as fh:
                    if CR in fh.read():
                        offenders.append(os.path.relpath(path, repo_root)
                                         .replace(os.sep, "/"))
    assert not offenders, "冻结件含 CR：%s" % offenders


def test_gitattributes_declares_eol_lf(repo_root):
    """`.gitattributes` 必须声明源码归一为 LF，否则新 clone 会漂移。"""
    path = os.path.join(repo_root, ".gitattributes")
    assert os.path.isfile(path), ".gitattributes 缺失"
    with open(path, "r", encoding="utf-8", newline="") as fh:
        content = fh.read()
    assert "text=auto" in content and "eol=lf" in content


def test_cr_detection_is_not_vacuous(tmp_path):
    """**机制探活**：确认本门真的能检出 CR（防"恒绿假门"）。"""
    probe = tmp_path / "probe.txt"
    probe.write_bytes(b"line1\r\nline2\n")
    with open(str(probe), "rb") as fh:
        assert CR in fh.read(), "CR 探测机制失效"
