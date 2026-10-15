"""G-PACK 门：打包规格与数据白名单互相自洽（plan/04 §四、plan/05 §三）。

**为什么这是一道门**：打包规格最容易出的两类事故都不会让构建报错——

1. **spec 里手写数据路径**：白名单改了、spec 没跟着改（或反之），构建照常
   成功，直到换台机器才发现随包数据缺了；
2. **目录条目的目标位置写错**：PyInstaller 把目录源的**内容**复制进目标目录，
   若目录条目也取 ``dirname``，三份快照会被拍平进 ``data/``——
   冻结态按 ``data/snapshots/`` 取数就永远找不到，**构建本身不报任何错**。

故本门断言的不只是"spec 里没有某个字符串"，而是**最终落在包内的路径等于仓库
内的相对路径**（``build_datas()`` 的产物经 PyInstaller 语义解析后）。这条性质
一成立，"源码态能跑 ⇒ 冻结态也能跑"才成立。

**三处守门必须互相独立**（plan/05 §三）：本门（spec 静态 + 布局行为）、
构建期白名单对账（spec 里调 ``unregistered_data_dirs()``）、构建后 dist 扫描
（M6 发布期）。改一处口径必同步另两处。
"""

import ast
import os
import sys

import pytest


@pytest.fixture(scope="session")
def packaging(repo_root):
    """``rcc.packaging`` —— 白名单与定位口径的**唯一定义点**。"""
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc import packaging as mod

    return mod


@pytest.fixture(scope="session")
def spec_path(repo_root):
    path = os.path.join(repo_root, "tools", "rcc.spec")
    assert os.path.isfile(path), "打包规格缺失: tools/rcc.spec（G-PACK 无对象可守）"
    return path


@pytest.fixture(scope="session")
def spec_source(spec_path):
    with open(spec_path, "r", encoding="utf-8") as handle:
        return handle.read()


def _string_constants(source):
    """spec 里全部字符串字面量及其行号。"""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value, node.lineno


def _path_segments(text):
    for separator in ("/", "\\"):
        text = text.replace(separator, "/")
    return [part for part in text.split("/") if part]


def _path_like_constants(source):
    """spec 里**形如路径**的字符串字面量及其行号（用于"手写数据路径"判据）。

    只取**不含空白**的字面量：spec 的报错文案是中文说明（如"数据目录下存在未
    登记项…"），它形如数据路径但不是路径。不设这道筛，门会对着自己的提示语报红，
    而**刷屏的门最终会被"加豁免"加到失效**。

    筛的是"空白"而非"非 ASCII"：路径里出现中文（``data/新数据/x.json``）仍须
    被抓住——按 ASCII 筛会把它一并滤掉，那等于给"手写数据路径"留了条带中文的
    绕过通道（本门的第一版就是这样漏掉了一个禁区字面）。
    """
    for text, lineno in _string_constants(source):
        if any(char.isspace() for char in text):
            continue
        yield text, lineno


# ------------------------------------------------- spec 内不得手写数据路径

def test_spec_has_no_handwritten_data_path(repo_root, spec_source, packaging):
    """**spec 不得手写任何数据路径**——数据路径的唯一来源是 ``build_datas()``。

    判据：形如路径的字面量里不得出现以 ``data`` 为**首段**的形态（``data/x``、
    ``data\\x``、裸 ``data``）。构建器负责把所有白名单条目翻成 PyInstaller 的
    ``(源, 目标目录)`` 对，spec 只准引用它的返回值。
    """
    offenders = []
    for text, lineno in _path_like_constants(spec_source):
        segments = _path_segments(text)
        if segments and segments[0] == "data":
            offenders.append("tools/rcc.spec:%d 手写数据路径 %r" % (lineno, text))
    assert not offenders, (
        "spec 手写数据路径（必须只经 build_datas() 取数）:\n  " + "\n  ".join(offenders))


def test_spec_has_no_forbidden_literals(spec_source, packaging):
    """**spec 不得出现禁区字面**（版权原文/开发过程材料绝不进发行包）。

    禁区集合取 ``rcc.packaging.FORBIDDEN_IN_DIST``，**不在此复制一份**——
    两处各存一份就是第二份真相。

    与上一条判据**不用同一个筛选器**：上位判据筛"无空白"，对禁区判据太松——
    禁区路径可以带中文（``plan/00-README总览.md``），按无空白筛它其实能过，
    但按"只取 ASCII"筛就漏了（本门第一版正是这样漏掉的）。故此处对**全部**
    字符串字面量取路径段，一个都不放过；误报风险由"禁区段是路径级精确匹配"
    兜住（散文里出现 ``plan/`` 这类片段本就该改文案）。
    """
    forbidden = set(packaging.FORBIDDEN_IN_DIST)
    offenders = []
    for text, lineno in _string_constants(spec_source):
        segments = set(_path_segments(text))
        hit = segments & forbidden
        if hit:
            offenders.append("tools/rcc.spec:%d 含禁区字面 %s（%r）"
                             % (lineno, sorted(hit), text))
    assert not offenders, "\n  ".join(offenders)


def test_forbidden_literal_guard_is_not_vacuous(spec_source, packaging):
    """**机制探活**：伪造手写禁区路径的 spec → 两个判据都必须报红。

    两个夹具各打一条路：``data/...`` 打"手写数据路径"，``plan/...`` 打"禁区
    字面"。后者刻意**带中文**——那是本门第一版漏掉的形态（筛选器按 ASCII 筛，
    中文路径被静默滤掉，变异验证当场抓出）。
    """
    fake = 'datas = [("data/rules/params.json", "data")]\n'
    fake += 'extra = "plan/00-README总览.md"\n'
    forbidden = set(packaging.FORBIDDEN_IN_DIST)

    data_hits = [text for text, _ in _path_like_constants(fake)
                 if _path_segments(text) and _path_segments(text)[0] == "data"]
    assert data_hits, "手写数据路径判据失效（未报红）"

    forbidden_hits = [text for text, _ in _string_constants(fake)
                      if set(_path_segments(text)) & forbidden]
    assert forbidden_hits, "禁区字面判据失效（带中文的 plan 路径未报红）"


def test_path_like_filter_does_not_hide_real_paths(spec_source):
    """**阴性对照的反面**：筛选器不得把真路径也滤掉（否则门成了空扫）。

    真路径（ASCII 或带中文，**无空白**）必须放行；而 spec 里那类说明文案
    （``"data/ 下存在未登记…"``）**带空白**，必须被滤掉——否则门会对着自己的
    提示语报红。
    """
    fake = ('a = "data/rules/params.json"\n'
            'b = "data/新数据/x.json"\n'
            'c = "data/ 下存在未登记进白名单的目录（会静默不进包）: %s"\n')
    kept = [text for text, _ in _path_like_constants(fake)]
    assert "data/rules/params.json" in kept, "筛选器把真路径滤掉了（门变空扫）"
    assert "data/新数据/x.json" in kept, "筛选器把带中文的真路径滤掉了（留了绕过通道）"
    assert not any("未登记" in text for text in kept), "筛选器未滤掉说明文案（门会对自己报红）"


# ------------------------------------------- datas 只由 build_datas() 产生

def test_spec_datas_come_from_build_datas(spec_source):
    """``datas`` 必须**由调用 ``build_datas()`` 产生**，不得字面列举。

    判据落在 AST 上：``DATAS`` 的赋值右侧必须是对 ``build_datas`` 的调用。
    ``assert "build_datas" in source`` 这类字面断言证明不了"它真被用来产 datas"
    （plan/04 §四末：变异验证是硬要求）。
    """
    tree = ast.parse(spec_source)
    assignment = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "DATAS":
                    assignment = node
    assert assignment is not None, "spec 未定义 DATAS"
    value = assignment.value
    assert isinstance(value, ast.Call), "DATAS 不是调用结果（字面列举 datas？）"
    func = value.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    assert name == "build_datas", "DATAS 由 %r 产生，不是 build_datas()" % name


def test_spec_build_fails_on_unregistered_data_dir(spec_source):
    """spec 必须在构建前对账白名单（新增数据目录却忘登记 → 构建即失败）。"""
    assert "unregistered_data_dirs" in spec_source, (
        "spec 未在构建前对账白名单——'新数据目录悄悄没进包'这条只能靠构建后扫描发现")


# --------------------------------------- 包内路径 == 仓库内相对路径（可达性）

def _bundle_paths(datas):
    """按 PyInstaller 语义把 ``datas`` 展开成 ``{包内路径: 源路径}``。

    PyInstaller 对 ``(源, 目标目录)`` 的处置（见 ``utils.format_binaries_and_datas``）：

    - 源是**文件** → 落在 ``目标目录/文件名``；
    - 源是**目录** → 其**内容**（含子目录）落在 ``目标目录/`` 之下。

    本函数就是该语义的最小复刻：布局误差在这里暴露，而不是等 exe 打出来。
    """
    mapping = {}
    for src, dest_dir in datas:
        if os.path.isdir(src):
            for dirpath, _dirnames, filenames in os.walk(src):
                rel = os.path.relpath(dirpath, src)
                for filename in filenames:
                    inner = filename if rel == os.curdir else os.path.join(rel, filename)
                    mapping[os.path.normpath(os.path.join(dest_dir, inner))] = \
                        os.path.join(dirpath, filename)
        else:
            mapping[os.path.normpath(os.path.join(dest_dir, os.path.basename(src)))] = src
    return mapping


def test_whitelist_covers_every_data_directory(repo_root, packaging):
    """``data/`` 下的每个目录都必须在白名单里（否则它会静默不进包）。"""
    assert packaging.unregistered_data_dirs(repo_root) == [], (
        "data/ 下存在未登记进白名单的目录: %s" % packaging.unregistered_data_dirs(repo_root))


def test_bundled_layout_matches_repo_layout(repo_root, packaging):
    """**核心断言**：白名单产物在包内的路径 == 它在仓库内的相对路径。

    这条性质是"随包数据可达"的全部内容：``find_data_dir()`` 冻结态返回
    ``<exe>/_internal/data``，各消费点再拼仓库内相对后缀——只有两侧布局一致，
    源码态能跑的路径在冻结态才同样能跑。

    变异验证（M5 实测）：把目录条目的目标目录退回 ``dirname`` →
    ``data/snapshots/x.json`` 变成 ``data/x.json`` → 本门立即红。
    """
    datas = packaging.build_datas(repo_root)
    assert datas, "白名单产出为空（门形同虚设）"

    bundled = _bundle_paths(datas)
    assert bundled, "包内路径解析为空"

    offenders = []
    for bundle_rel, source in sorted(bundled.items()):
        repo_rel = os.path.relpath(source, repo_root)
        if os.path.normpath(bundle_rel) != os.path.normpath(repo_rel):
            offenders.append("%s 落在了包内 %s（仓库内为 %s）"
                             % (repo_rel, bundle_rel, repo_rel))
    assert not offenders, (
        "随包数据在包内的位置与仓库内不一致——冻结态按仓库相对路径取数会落空:\n  "
        + "\n  ".join(offenders))


def test_directory_entries_keep_their_own_directory(repo_root, packaging):
    """目录条目的目标目录 = 条目自身（**不是它的父目录**）。

    与上一条是同一判据的两种粒度：上一条看展开后的文件位置，这一条看
    ``build_datas()`` 返回元组本身。两者同时红/同时绿才算守住了。
    """
    datas = packaging.build_datas(repo_root)
    by_rel = {}
    for src, dest in datas:
        repo_rel = os.path.relpath(src, repo_root).replace(os.sep, "/")
        by_rel[repo_rel] = dest.replace(os.sep, "/")

    directory_entries = [rel for rel in by_rel if os.path.isdir(
        os.path.join(repo_root, rel.replace("/", os.sep)))]
    assert directory_entries, "白名单里没有目录条目（判据未被真正考验）"
    for rel in directory_entries:
        assert by_rel[rel] == rel, (
            "目录条目 %s 的目标目录为 %r（应为条目自身）——"
            "PyInstaller 会把目录内容复制进该目录，取父目录会导致内容被拍平"
            % (rel, by_rel[rel]))


def test_file_entries_land_in_their_parent_directory(repo_root, packaging):
    """文件条目的目标目录 = 其父目录（``data/rules/params.json`` → ``data/rules``）。"""
    datas = packaging.build_datas(repo_root)
    by_rel = {}
    for src, dest in datas:
        repo_rel = os.path.relpath(src, repo_root).replace(os.sep, "/")
        by_rel[repo_rel] = dest.replace(os.sep, "/")

    file_entries = [rel for rel in by_rel if os.path.isfile(
        os.path.join(repo_root, rel.replace("/", os.sep)))]
    assert file_entries, "白名单里没有文件条目（判据未被真正考验）"
    for rel in file_entries:
        parent = os.path.dirname(rel)
        assert by_rel[rel] == parent, (
            "文件条目 %s 的目标目录为 %r（应为父目录 %r）" % (rel, by_rel[rel], parent))


def test_whitelist_is_the_single_source_for_spec_datas(repo_root, packaging):
    """spec 实际声明的数据集合 == 白名单（防"spec 自己又列了一杯"）。"""
    from_file = {os.path.relpath(src, repo_root).replace(os.sep, "/")
                 for src, _dest in packaging.build_datas(repo_root)}
    whitelist = {rel for rel in packaging.DATA_WHITELIST
                 if os.path.exists(os.path.join(repo_root, rel.replace("/", os.sep)))}
    assert from_file == whitelist, (
        "build_datas() 的产出与白名单不一致: 多 %s / 少 %s"
        % (sorted(from_file - whitelist), sorted(whitelist - from_file)))


# ------------------------------------------------- 冻结态自检的判定纪律

def test_frozen_inside_dist_is_none_when_not_frozen(packaging):
    """非冻结态该项返回 ``None``——不让源码运行被误判 FAIL。"""
    assert packaging.is_frozen() is False, "测试进程不应处于冻结态"
    assert packaging.frozen_data_is_inside_dist(os.getcwd(), os.getcwd()) is None


def test_frozen_inside_dist_rejects_data_outside_exe(tmp_path, packaging, monkeypatch):
    """**冻结态判定本身要有牙**：数据在 exe 目录之外必须报 False。

    否则自检里的 "数据目录落在 exe 目录内" 就是恒真的装饰——而那正是打包最常见
    的失效模式（数据没随包走、exe 回头读了开发机的仓库）。
    """
    monkeypatch.setattr(packaging, "is_frozen", lambda: True)
    exe_dir = str(tmp_path / "dist")
    inside = str(tmp_path / "dist" / "_internal" / "data")
    outside = str(tmp_path / "elsewhere" / "data")
    assert packaging.frozen_data_is_inside_dist(exe_dir, inside) is True
    assert packaging.frozen_data_is_inside_dist(exe_dir, outside) is False


def test_frozen_data_candidates_are_inside_dist_layout(tmp_path, monkeypatch, packaging):
    """冻结态候选路径必须都指向 exe 目录之内（含 PyInstaller 5 平铺兼容项）。"""
    monkeypatch.setattr(packaging.sys, "frozen", True, raising=False)
    monkeypatch.setattr(packaging.sys, "_MEIPASS",
                        str(tmp_path / "dist" / "_internal"), raising=False)
    monkeypatch.setattr(packaging.sys, "executable",
                        str(tmp_path / "dist" / "rcc.exe"), raising=False)
    exe_dir = str(tmp_path / "dist")
    for candidate in packaging._frozen_data_candidates():
        assert packaging.frozen_data_is_inside_dist(exe_dir, candidate) is True, (
            "冻结态候选 %s 落在 exe 目录之外" % candidate)
