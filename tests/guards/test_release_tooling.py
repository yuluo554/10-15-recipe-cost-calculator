"""发布物组装门（G-RELASE，M6 新增）。

守两件 M6 才出现的事，两件都是"本地看着对、换个人/换台机器就坏"的类型：

1. **zip 确定性**（plan/05 §六）：两次独立打包必须逐字节一致。失效模式是
   ``os.walk`` 的产出顺序不稳定——实测不显式排序则两次打包字节不同，
   而**两次都"成功"**，不看 sha256 根本发现不了。故断言落在 sha256 上；
2. **构建后三断言**（plan/05 §三，三处守门互相独立的第三处）：禁区成分 /
   内嵌数据逐份一致 / 白名单外多余。前两处（spec 静态门、构建前对账）都在
   G-PACK，本门补的是**产物本体**这一侧——"数据改了没重建"只有比对产物字节才看得出。

夹具用**程序化合成的迷你 dist 树**（不依赖真构建 114MB 产物），故可在 CI 常跑。
"""

import hashlib
import os
import shutil
import sys

import pytest


@pytest.fixture(scope="module")
def release_tool(repo_root):
    """导入 ``tools/make_release.py``。"""
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import make_release

    return make_release


@pytest.fixture
def fake_repo(tmp_path, write_text_lf):
    """合成一个"仓库侧"树（包内数据 ``src/rcc/data`` 与合成 dist 的内容一致）。

    **M7 口径**：数据在包内（``src/rcc/data``），``check_dist()`` 的仓库侧基准
    由 ``rcc.packaging.package_data_dir()`` 决定——故夹具必须造在那个位置，
    造在顶层 ``data/`` 就测不到真实现（会得到"仓库内缺少对应文件"的假红）。
    """
    root = tmp_path / "fake_repo"
    data_root = root / "src" / "rcc" / "data"
    (data_root / "rules").mkdir(parents=True)
    (data_root / "snapshots").mkdir(parents=True)
    write_text_lf(data_root / "rules" / "params.json", '{"a": 1}\n')
    write_text_lf(data_root / "snapshots" / "x.json", '{"b": 2}\n')
    return str(root)


@pytest.fixture
def fake_dist(tmp_path, fake_repo, write_text_lf):
    """合成一个迷你 dist 树（结构照真产物：``_internal/data/...`` + 两个 exe）。

    数据内容**从 fake_repo 的包内数据目录复制**——保证"一致的合成树"基线成立
    （断言二可比）。
    """
    root = tmp_path / "dist" / "rcc"
    internal = root / "_internal"
    (root).mkdir(parents=True)
    (internal).mkdir(parents=True)
    (root / "rcc.exe").write_bytes(b"MZ fake console exe")
    (root / "rcc-gui.exe").write_bytes(b"MZ fake gui exe")
    (internal / "python312.dll").write_bytes(b"MZ fake python dll")
    shutil.copytree(os.path.join(fake_repo, "src", "rcc", "data"),
                    str(internal / "data"))
    return str(root)


def test_release_zip_is_byte_identical_across_runs(release_tool, fake_dist, tmp_path):
    """**两次独立打包逐字节一致**——本工具的确定性承诺。"""
    first = str(tmp_path / "a.zip")
    second = str(tmp_path / "b.zip")
    release_tool._write_zip(fake_dist, first)
    release_tool._write_zip(fake_dist, second)

    digest_a = hashlib.sha256(open(first, "rb").read()).hexdigest()
    digest_b = hashlib.sha256(open(second, "rb").read()).hexdigest()
    assert digest_a == digest_b, "两次打包字节不同（条目排序缺失？）"


def test_release_zip_entries_are_sorted_and_flat_time(release_tool, fake_dist, tmp_path):
    """条目按路径排序 + 全条目固定时间戳 + STORED（三条共同保证确定性）。"""
    import zipfile

    out = str(tmp_path / "a.zip")
    names = release_tool._write_zip(fake_dist, out)
    assert names == sorted(names), "归档条目未按路径排序"

    with zipfile.ZipFile(out) as archive:
        for info in archive.infolist():
            assert info.date_time == release_tool.FIXED_DATE_TIME, \
                "%s 时间戳非固定值" % info.filename
            assert info.compress_type == zipfile.ZIP_STORED, \
                "%s 非 STORED（压缩实现差异会破坏字节一致）" % info.filename


def test_release_zip_keeps_data_nested_under_internal(release_tool, fake_dist, tmp_path):
    """随包数据必须留在 ``_internal/data/...`` 原相对路径（K41 的产物侧复核）。

    拍平（``data/x.json``）时冻结态按 ``data/snapshots/`` 取数会落空——
    构建不报错，只有换机器才发现。故在这里按**归档内路径**再断言一次。
    """
    import zipfile

    out = str(tmp_path / "a.zip")
    release_tool._write_zip(fake_dist, out)
    with zipfile.ZipFile(out) as archive:
        names = set(archive.namelist())
    assert "rcc/_internal/data/snapshots/x.json" in names, \
        "快照被拍平（未留在 data/snapshots/ 下）"
    assert "rcc/_internal/data/rules/params.json" in names
    assert "rcc/rcc.exe" in names and "rcc/rcc-gui.exe" in names, "两个 exe 未在归档顶层"


def test_dist_check_passes_on_consistent_tree(release_tool, repo_root, fake_dist, fake_repo):
    """一致的合成树 → 三断言全过（阴性基线的另一半）。"""
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc.packaging import DATA_WHITELIST, FORBIDDEN_IN_DIST

    problems = release_tool.check_dist(fake_dist, fake_repo,
                                       DATA_WHITELIST, FORBIDDEN_IN_DIST)
    assert not problems, "一致树被判有问题: %s" % problems


def test_dist_check_catches_forbidden_dir(release_tool, repo_root, fake_dist):
    """**变异一**：dist 顶层塞禁区目录 → 必须被断言一抓住。"""
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc.packaging import DATA_WHITELIST, FORBIDDEN_IN_DIST

    os.makedirs(os.path.join(fake_dist, "tests"))
    problems = release_tool.check_dist(fake_dist, repo_root,
                                       DATA_WHITELIST, FORBIDDEN_IN_DIST)
    assert any("断言一" in p for p in problems), "禁区目录未被检出: %s" % problems


def test_dist_check_catches_data_drift(release_tool, repo_root, fake_dist):
    """**变异二**：包内数据被改一个字节 → 必须被断言二抓住。

    这是"数据改了没重建"的产物侧判据——源码态、spec 门、构建前对账**全都看不出来**。
    """
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc.packaging import DATA_WHITELIST, FORBIDDEN_IN_DIST

    target = os.path.join(fake_dist, "_internal", "data", "rules", "params.json")
    with open(target, "ab") as handle:
        handle.write(b" ")

    problems = release_tool.check_dist(fake_dist, repo_root,
                                       DATA_WHITELIST, FORBIDDEN_IN_DIST)
    assert any("断言二" in p for p in problems), "数据漂移未被检出: %s" % problems


def test_dist_check_catches_unregistered_data(release_tool, repo_root, fake_dist):
    """**变异三**：包内多出一个白名单外数据文件 → 必须被断言三抓住。"""
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc.packaging import DATA_WHITELIST, FORBIDDEN_IN_DIST

    rogue = os.path.join(fake_dist, "_internal", "data", "rogue")
    os.makedirs(rogue)
    with open(os.path.join(rogue, "x.json"), "w", encoding="utf-8") as handle:
        handle.write("{}\n")

    problems = release_tool.check_dist(fake_dist, repo_root,
                                       DATA_WHITELIST, FORBIDDEN_IN_DIST)
    assert any("断言三" in p for p in problems), "白名单外数据未被检出: %s" % problems
