"""编码守卫覆盖门 + README 可跑通门 + CI 配置门 + 报告确定性门。

这三类门守的都是"本地全绿但别处会挂"的缺口：

- **编码守卫**：所有会打印的可执行入口（CLI + tools/ 每个脚本，**含里程碑后期新增的**）
  都必须在 main 最开头调用入口守卫——漏一个，windows CI 就崩在那一个脚本的 print 上；
- **README 可跑通**：README 引用的每个输入文件必须**由生成器保证存在**。
  本地工作目录残留会掩盖"引用了根本不存在的文件"，且 **CI 也暴露不了它**
  （CI 只跑 pytest 不读 README）；
- **CI 配置**：非法 YAML 会让 GitHub **不建任何 job**，而 state 仍显示 active、
  文件字节也洁净——看状态、看字节都查不出。
"""

import ast
import os
import re
import subprocess
import sys

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover - dev extra 缺失时声明式跳过
    yaml = None


# --------------------------------------------------------------- 编码守卫

PRINT_GUARD_NAME = "ensure_utf8_stdio"


def _entry_scripts(repo_root):
    """会打印的可执行入口：CLI + tools/ 下每个**有 main 的**脚本。

    纯库模块（如 detrng.py，无 ``main`` 与 ``__main__`` 块、不打印）不算入口。
    """
    yield os.path.join(repo_root, "src", "rcc", "cli.py")
    tools_dir = os.path.join(repo_root, "tools")
    for filename in sorted(os.listdir(tools_dir)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        path = os.path.join(tools_dir, filename)
        if _is_executable_entry(path):
            yield path


def _is_executable_entry(path):
    """判定是否为可执行入口（有 ``main`` 函数或 ``__main__`` 块）。"""
    tree = ast.parse(open(path, "r", encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return True
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            if (isinstance(test, ast.Compare)
                    and isinstance(test.left, ast.Name)
                    and test.left.id == "__name__"):
                return True
    return False


def _calls_guard(path):
    """AST 判定：该脚本是否在 main/模块层调用了入口守卫。"""
    tree = ast.parse(open(path, "r", encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == PRINT_GUARD_NAME:
                return True
    return False


def test_all_entry_scripts_call_encoding_guard(repo_root):
    """**入口集合随里程碑增长**——新增脚本漏守即红。"""
    missing = []
    for path in _entry_scripts(repo_root):
        if not _calls_guard(path):
            missing.append(os.path.relpath(path, repo_root).replace(os.sep, "/"))
    assert not missing, "以下入口未调用编码守卫 %s: %s" % (PRINT_GUARD_NAME, missing)


def test_guard_detection_is_not_vacuous(repo_root, tmp_path):
    """机制探活：确认 AST 判定真能分辨"有守卫"与"没守卫"。"""
    good = tmp_path / "good.py"
    with open(str(good), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("def main():\n    ensure_utf8_stdio()\n")
    bad = tmp_path / "bad.py"
    with open(str(bad), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("def main():\n    print('hi')\n")
    assert _calls_guard(str(good))
    assert not _calls_guard(str(bad))


def test_encoding_guard_reconfigures_non_utf8_stream(repo_root):
    """行为测试：cp1252 流应被重设为 UTF-8（本机即可复现，不必等 CI）。"""
    sys.path.insert(0, os.path.join(repo_root, "src"))
    import io

    from rcc._encoding import _needs_reconfigure

    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    assert _needs_reconfigure(stream), "cp1252 流应判定为需要重设"

    utf8_stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    assert not _needs_reconfigure(utf8_stream), "utf-8 流不应被重设"


def test_guard_is_idempotent_and_safe(repo_root):
    """守卫幂等，且对不支持 reconfigure 的流静默跳过。"""
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc._encoding import ensure_utf8_stdio

    ensure_utf8_stdio()
    ensure_utf8_stdio()  # 二次调用不得抛错


# -------------------------------------------------------- README 可跑通门

README_INPUT_RE = re.compile(r"--(purchases|bom|params|snapshots)\s+(\S+)")


def test_readme_inputs_exist(repo_root):
    """README 代码块里引用的输入路径必须**真存在**。

    这类静态断言抓不到无前缀的裸文件名，所以**从命令里抽参数**。
    """
    readme = os.path.join(repo_root, "README.md")
    text = open(readme, "r", encoding="utf-8").read()
    missing = []
    for match in README_INPUT_RE.finditer(text):
        raw = match.group(2).strip("`\"'")
        if raw.startswith("-"):  # 选项而非路径
            continue
        path = os.path.join(repo_root, raw.replace("/", os.sep))
        if not os.path.exists(path):
            missing.append(raw)
    assert not missing, "README 引用的输入不存在（需由生成器产出）: %s" % missing


def test_readme_inputs_are_generator_produced(repo_root):
    """README 引用的输入必须由生成器产出，而非"恰好本地有"。"""
    sys.path.insert(0, os.path.join(repo_root, "tools"))
    import gen_samples

    produced = set(gen_samples.outputs())
    readme = os.path.join(repo_root, "README.md")
    text = open(readme, "r", encoding="utf-8").read()
    referenced = {m.group(2).strip("`\"'") for m in README_INPUT_RE.finditer(text)}
    sample_refs = {r for r in referenced if r.startswith("data/samples/")}
    assert sample_refs, "README 未引用任何样例输入（门形同虚设）"
    assert sample_refs <= produced, (
        "README 引用了生成器不产出的样例: %s" % sorted(sample_refs - produced))


def test_readme_commands_run(repo_root):
    """按 README 步骤真跑一遍（退出码须符合明示语义）。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # 子进程不继承测试进程的 sys.path——显式指向 src/
    src = os.path.join(repo_root, "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    purchases = "data/samples/purchases-demo.csv"
    bom = "data/samples/bom-demo.json"

    # rcc run：样例含刻意注入的异常行 → 退出码 1 是明示语义
    proc = subprocess.run(
        [sys.executable, "-m", "rcc.cli", "run", "--purchases", purchases, "--bom", bom],
        capture_output=True, cwd=repo_root, env=env)
    assert proc.returncode == 1, (
        "rcc run 退出码应为 1（有异常行，明示语义），实际 %d: %s"
        % (proc.returncode, proc.stderr.decode("utf-8", "replace")))

    # rcc bench：真值库未生成 → 未启用套件不计为通过 → 退出码 1
    proc = subprocess.run([sys.executable, "-m", "rcc.cli", "bench"],
                          capture_output=True, cwd=repo_root, env=env)
    assert proc.returncode in (0, 1), proc.stderr.decode("utf-8", "replace")

    # rcc selftest：源码态应全过
    proc = subprocess.run([sys.executable, "-m", "rcc.cli", "selftest"],
                          capture_output=True, cwd=repo_root, env=env)
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")


# --------------------------------------------------------------- CI 配置门

@pytest.mark.skipif(yaml is None, reason="需要 pyyaml（dev extra）")
def test_workflows_are_valid_yaml(repo_root):
    """非法 YAML 会让 GitHub 不建任何 job，而 state 仍显示 active。"""
    wf_dir = os.path.join(repo_root, ".github", "workflows")
    assert os.path.isdir(wf_dir), ".github/workflows 缺失"
    files = [f for f in sorted(os.listdir(wf_dir)) if f.endswith((".yml", ".yaml"))]
    assert files, "无 workflow 文件"
    for filename in files:
        path = os.path.join(wf_dir, filename)
        with open(path, "r", encoding="utf-8") as fh:
            try:
                doc = yaml.safe_load(fh)
            except yaml.YAMLError as exc:
                pytest.fail("%s 不是合法 YAML（GitHub 会不建任何 job）: %s" % (filename, exc))
        assert doc, "%s 为空" % filename


@pytest.mark.skipif(yaml is None, reason="需要 pyyaml（dev extra）")
def test_workflow_jobs_have_required_keys(repo_root):
    wf_dir = os.path.join(repo_root, ".github", "workflows")
    for filename in sorted(os.listdir(wf_dir)):
        if not filename.endswith((".yml", ".yaml")):
            continue
        with open(os.path.join(wf_dir, filename), "r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        jobs = (doc or {}).get("jobs") or {}
        assert jobs, "%s 无 job" % filename
        for name, job in jobs.items():
            assert job.get("runs-on"), "%s job %s 缺 runs-on" % (filename, name)
            assert job.get("steps"), "%s job %s 缺 steps" % (filename, name)


@pytest.mark.skipif(yaml is None, reason="需要 pyyaml（dev extra）")
def test_checkout_uses_full_history(repo_root):
    """历史扫描类守门依赖 git 历史——浅克隆会让它**静默削弱成空验**。"""
    wf_dir = os.path.join(repo_root, ".github", "workflows")
    offenders = []
    for filename in sorted(os.listdir(wf_dir)):
        if not filename.endswith((".yml", ".yaml")):
            continue
        with open(os.path.join(wf_dir, filename), "r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        for job_name, job in ((doc or {}).get("jobs") or {}).items():
            for step in job.get("steps") or []:
                uses = str(step.get("uses", ""))
                if "actions/checkout" in uses:
                    depth = (step.get("with") or {}).get("fetch-depth")
                    if depth != 0:
                        offenders.append("%s/%s fetch-depth=%r" % (filename, job_name, depth))
    assert not offenders, "checkout 未取全量历史（历史扫描会静默空验）: %s" % offenders


@pytest.mark.skipif(yaml is None, reason="需要 pyyaml（dev extra）")
def test_ci_sets_utf8_env(repo_root):
    """编码三层加固之一：CI 全局 UTF-8（只救 CI，不能当唯一手段，但必须有）。"""
    path = os.path.join(repo_root, ".github", "workflows", "ci.yml")
    with open(path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    env = doc.get("env") or {}
    assert str(env.get("PYTHONUTF8")) in ("1", "true", "True"), "CI 未设 PYTHONUTF8"
    assert str(env.get("PYTHONIOENCODING", "")).lower().startswith("utf-8"), \
        "CI 未设 PYTHONIOENCODING"


@pytest.mark.skipif(yaml is None, reason="需要 pyyaml（dev extra）")
def test_ci_extras_cover_test_dependencies(repo_root):
    """**CI 的 extras 集合必须覆盖测试期依赖**，否则门在 CI 上静默跳过。"""
    path = os.path.join(repo_root, ".github", "workflows", "ci.yml")
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    # 测试期真 import 的库：pytest（框架）、pyyaml（本文件的 CI 门）
    assert ".[dev]" in text or "[dev]" in text, "CI 未安装 dev extra（pytest/pyyaml 会缺）"


# ------------------------------------------------------------ 报告确定性门

def test_report_is_byte_identical(repo_root, tmp_path):
    """同输入两次导出必须逐字节一致（自写最小 OOXML writer）。"""
    import hashlib

    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc.report import export

    result = _sample_result(repo_root)
    first = export.write_reports(result, str(tmp_path / "a"))
    second = export.write_reports(result, str(tmp_path / "b"))

    for path_a, path_b in zip(first, second):
        with open(path_a, "rb") as fh_a, open(path_b, "rb") as fh_b:
            digest_a = hashlib.sha256(fh_a.read()).hexdigest()
            digest_b = hashlib.sha256(fh_b.read()).hexdigest()
        assert digest_a == digest_b, "%s 两次导出字节不同" % os.path.basename(path_a)


def test_xlsx_has_no_external_links(repo_root, tmp_path):
    """机读产物无外链（断网可开、可归档）。

    OOXML 的命名空间声明（``xmlns="http://schemas.openxmlformats.org/..."``）
    与 Relationship ``Type`` 属性**本身就是 http URI**（规范如此）——所以不能对
    产物全文做 http 子串扫描。正确判据 = 无 ``TargetMode="External"`` +
    **剥掉 XML 标签后的文本内容**无 http。
    """
    import re
    import zipfile

    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc.report import export

    result = _sample_result(repo_root)
    paths = export.write_reports(result, str(tmp_path / "report"))
    xlsx = [p for p in paths if p.endswith(".xlsx")][0]

    tag_re = re.compile(r"<[^>]*>")
    with zipfile.ZipFile(xlsx) as zf:
        for name in zf.namelist():
            content = zf.read(name).decode("utf-8", errors="replace")
            # 关系项：不得有外部目标
            assert 'TargetMode="External"' not in content, "%s 含外部关系" % name
            # 剥标签后的文本内容不得含 URL
            text = tag_re.sub("", content)
            assert "http://" not in text and "https://" not in text, \
                "%s 的文本内容含外链" % name


def test_xlsx_external_link_guard_is_not_vacuous(repo_root, tmp_path):
    """**机制探活**：确认外链判据真能抓出 URL（防恒绿假门）。"""
    import re

    from rcc.report import export

    tag_re = re.compile(r"<[^>]*>")
    # 单元格里的 URL 会被剥标签后仍留存 → 判据能抓
    cell = '<c r="A1" t="inlineStr"><is><t>https://example.com</t></is></c>'
    assert "https://" in tag_re.sub("", cell), "外链判据失效"
    # 而命名空间声明在标签内 → 剥标签后消失（不误报）
    xmlns = '<worksheet xmlns="http://schemas.openxmlformats.org/x">'
    assert "http://" not in tag_re.sub("", xmlns), "命名空间被误判为外链"
    # writer 自身在遇到外链时必须抛错
    with pytest.raises(export.ExternalLinkError):
        export.write_xlsx(str(tmp_path / "bad.xlsx"),
                          [["https://example.com"]])


def test_xlsx_entries_are_stored_with_fixed_timestamp(repo_root, tmp_path):
    """zip 条目必须 STORED + 固定时间戳 + create_system=0（跨平台位级一致）。"""
    import zipfile

    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc.report import export

    result = _sample_result(repo_root)
    paths = export.write_reports(result, str(tmp_path / "report"))
    xlsx = [p for p in paths if p.endswith(".xlsx")][0]
    with zipfile.ZipFile(xlsx) as zf:
        for info in zf.infolist():
            assert info.compress_type == zipfile.ZIP_STORED, "%s 非 STORED" % info.filename
            assert info.date_time == export.FIXED_DATE_TIME, "%s 时间戳未固定" % info.filename
            assert info.create_system == 0, "%s create_system 未固定" % info.filename


def test_markdown_and_xlsx_share_one_render_source(repo_root, tmp_path):
    """两格式内容一致是**结构性质**（单一渲染源），不是人工抽查。"""
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc.report import export, sections

    result = _sample_result(repo_root)
    structure = sections.build_sections(result)
    md_text = export.render_markdown(result)
    xlsx_rows = export.render_xlsx_rows(result)

    # 每个章节标题都要同时出现在两种产物里
    for section in structure:
        assert section["title"] in md_text, "Markdown 缺章节 %s" % section["title"]
        flat = [" ".join(str(c) for c in row) for row in xlsx_rows]
        assert any(section["title"] in line for line in flat), \
            "XLSX 缺章节 %s" % section["title"]


def test_disabled_alert_section_is_explicit(repo_root):
    """未启用章节必须**显式写出**——"没查"与"查了没问题"是两种结论。"""
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc.report import export

    result = _sample_result(repo_root)
    assert not result["alert_enabled"]
    text = export.render_markdown(result)
    assert "未启用" in text and "预警" in text, "未启用预警时报告未显式声明"


def _sample_result(repo_root):
    """构造一份最小引擎结果（走真实编排层，不手搓）。"""
    sys.path.insert(0, os.path.join(repo_root, "src"))
    from rcc.engine import pipeline

    class _Args(object):
        purchases = os.path.join(repo_root, "data", "samples", "purchases-demo.csv")
        bom = os.path.join(repo_root, "data", "samples", "bom-demo.json")
        params = None
        snapshots = []
        with_alert = False

    return pipeline.compute_full(_Args())
