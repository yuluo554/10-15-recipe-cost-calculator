"""G-INSTALL 门：**装真 wheel** 之后用户能不能跑（M7 新增）。

## 为什么这道门必须存在

M6 已经修过一次同族缺陷（顶层 `benchmark/` 没进安装面 → 装好的 `rcc bench`
ModuleNotFoundError），并把它写进了 CI 的 "Console-script smoke" 一步——**思路对，
但那一跑在 `pip install -e` 的 editable 安装上**。editable 安装把仓库根放上
`sys.path`，于是：

- `find_data_dir()` 走 `repo_root()` → 命中仓库根 → 仓库里的 `data/` 正常；
- 一切绿。

而 `pip install <wheel>` 之后 `repo_root()` 找到的是 `<venv>`，数据又不在包里
（M7 之前 `data/` 在仓库根、包外、无 `package-data`），于是
`selftest` 报 `ok=false`、`bench` 抛 `FileNotFoundError`——**同一份代码，用户装完
就是跑不起来，而 CI 全绿**。

## 本门的两级判据

1. :func:`test_wheel_contains_package_data`——**结构级**：打出来的 wheel 里必须
   真有 `rcc/data/**` 条目（快、无副作用，CI 每轮都跑）；
2. :func:`test_installed_wheel_is_usable`——**行为级**：全新 venv 装 wheel，
   在**中立目录**（不是仓库树）跑 `selftest` 与 `bench`，断言 `ok=true`、
   `param_count>0`、五套件达标。

只做第 1 条不够：`package-data` 写错（比如 `data/*` 而非 `data/**/*`）时条目数
可能是 0 而不是报错，也可能文件进去了但 `find_data_dir()` 的优先级没改——两种都
只有真装一次才暴露。故第 2 条是主判据，第 1 条是它的快速前哨。
"""

import glob
import json
import os
import shutil
import subprocess
import sys

import pytest

# 标记：装态门跑得慢（建 venv + 装 wheel，约 30s），但**不许 skip**
pytestmark = pytest.mark.install


def _venv_python(venv_dir):
    """venv 内解释器路径（Windows 与 POSIX 不同）。"""
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def _venv_script(venv_dir, name):
    """venv 内控制台脚本路径（`rcc` 在 Windows 上是 rcc.exe）。"""
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", name + ".exe")
    return os.path.join(venv_dir, "bin", name)


def _run(cmd, cwd=None):
    """跑子进程，**显式 UTF-8 解码**（本仓编码三层加固的第三层）。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(cmd, capture_output=True, cwd=cwd, env=env,
                          encoding="utf-8", errors="replace")


def _clean_source_copy(repo_root, target):
    """把**构建所需的最小源码树**复制到仓库树外（不含 `build/`、`dist/`、`.venv`）。

    **为什么必须复制**：`pip wheel .` 会复用仓库里已有的 `build/lib/`。那目录是
    上一次构建的残留，里面**已经有 `rcc/data/`**——于是即使把
    `[tool.setuptools.package-data]` 整段删掉，wheel 里照样有数据，**负控不会红**
    （本门第一版就被这个假绿骗过）。从干净副本构建才问得到"当前 pyproject 声明
    能打出什么"。
    """
    target = str(target)
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target)
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        source = os.path.join(repo_root, name)
        if os.path.isfile(source):
            shutil.copyfile(source, os.path.join(target, name))
    for name in ("src", "benchmark"):
        shutil.copytree(os.path.join(repo_root, name), os.path.join(target, name),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
    return target


def _build_wheel(repo_root, out_dir, tmp_path):
    """在**干净源码副本**上 `pip wheel . --no-deps`，返回 wheel 路径。

    失败即 fail，不静默跳过——装态门无对象可验时"跳过"等于把门关掉。
    """
    os.makedirs(out_dir, exist_ok=True)
    source = _clean_source_copy(repo_root, os.path.join(str(tmp_path), "clean-src"))
    proc = _run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps",
                 "-w", out_dir], cwd=source)
    assert proc.returncode == 0, (
        "pip wheel 失败（装态门无对象可验）:\n%s\n%s" % (proc.stdout, proc.stderr))
    wheels = sorted(glob.glob(os.path.join(out_dir, "*.whl")))
    assert wheels, "pip wheel 成功但产物目录里没有 .whl: %s" % out_dir
    return wheels[0]


# --------------------------------------------------------- 结构级：wheel 里有数据

def test_wheel_contains_package_data(repo_root, tmp_path):
    """**wheel 必须带数据**——M7 之前这里恒为 0 条。

    判据不写死条目总数（新增数据文件不该让门变红），只要求：
    ① 存在 `rcc/data/` 下的条目；② 四个白名单目录各有代表性文件；
    ③ 参数包在里面（`selftest` 的第一件事就是加载它）。
    """
    import zipfile

    wheel = _build_wheel(repo_root, str(tmp_path / "wheelhouse"), tmp_path)
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()

    data_entries = [name for name in names if "/data/" in name]
    assert data_entries, (
        "wheel 里没有任何 rcc/data/ 条目——package-data 没生效，"
        "装完必然 FileNotFoundError（这正是 M7 修的缺陷）")

    required = (
        "rcc/data/rules/params.json",
        "rcc/data/truth/manifest.json",
        "rcc/data/samples/bom-demo.json",
        "rcc/data/samples/purchases-demo.csv",
    )
    missing = [name for name in required if name not in names]
    assert not missing, "wheel 缺关键数据文件（白名单目录没被完整收进包）: %s" % missing

    snapshots = [name for name in data_entries
                 if name.startswith("rcc/data/snapshots/") and name.endswith(".json")]
    assert len(snapshots) >= 2, (
        "wheel 里快照文件过少（%d 个）——目录型 package-data 只收了一层？" % len(snapshots))


# ---------------------------------------------- 行为级：装完在干净环境真能跑

def test_installed_wheel_is_usable(repo_root, tmp_path):
    """**全新 venv 装 wheel → 中立目录跑 `selftest`/`bench`**。

    为什么必须在**中立目录**跑：仓库树内的 CWD 上溯会命中源码树，源码态的
    `find_data_dir()` 可能"顺手"找到别处的 `data/`，那样验的是本机残留而不是
    "装进去的那份"。故 `cwd` 显式设到 venv 之外的临时目录。
    """
    wheel = _build_wheel(repo_root, str(tmp_path / "wheelhouse"), tmp_path)

    venv_dir = str(tmp_path / "venv")
    proc = _run([sys.executable, "-m", "venv", venv_dir])
    assert proc.returncode == 0, "建 venv 失败:\n%s" % proc.stderr
    python = _venv_python(venv_dir)
    assert os.path.isfile(python), "venv 内没有解释器: %s" % python

    proc = _run([python, "-m", "pip", "install", "--no-deps", wheel])
    assert proc.returncode == 0, "装 wheel 失败:\n%s\n%s" % (proc.stdout, proc.stderr)

    rcc = _venv_script(venv_dir, "rcc")
    assert os.path.isfile(rcc), "装完没有 rcc 控制台脚本: %s" % rcc

    # 中立目录：既不是仓库树，也不是 venv 内（避免任何"顺手找到"的可能）
    neutral = tmp_path / "neutral"
    neutral.mkdir()
    cwd = str(neutral)

    # ---- selftest：退出码 0 + ok=true + param_count>0
    proc = _run([rcc, "selftest"], cwd=cwd)
    assert proc.returncode == 0, (
        "装好的 rcc selftest 退出码 %d（应为 0）:\n%s\n%s"
        % (proc.returncode, proc.stdout, proc.stderr))
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True, "selftest ok=false（checks: %s）" % [
        (c["name"], c["ok"], c["detail"]) for c in payload["checks"] if not c["ok"]]
    assert payload["param_count"] > 0, "param_count=%r（参数包没读到）" % payload["param_count"]

    # data_dir 必须落在装进去的包里——不是开发机仓库、不是 CWD
    data_dir = os.path.abspath(payload["data_dir"])
    assert os.path.isdir(data_dir), "selftest 报的 data_dir 不存在: %s" % data_dir
    assert "site-packages" in data_dir or "dist-packages" in data_dir, (
        "装态 data_dir 不在 site-packages 内（%s）——说明读的是源码树或别处" % data_dir)
    assert os.path.abspath(repo_root) not in data_dir, (
        "装态 data_dir 落回了开发机仓库（%s）——正是本门要拦的失效形态" % data_dir)

    # ---- bench：退出码 0 + 五套件全 [达标]
    proc = _run([rcc, "bench"], cwd=cwd)
    assert proc.returncode == 0, (
        "装好的 rcc bench 退出码 %d（应为 0）:\n%s\n%s"
        % (proc.returncode, proc.stdout, proc.stderr))
    assert proc.stdout.count("[达标]") == 5, (
        "五套件未全达标:\n%s" % proc.stdout)
    assert "总判: 达标" in proc.stdout, "总判不是达标:\n%s" % proc.stdout

    shutil.rmtree(venv_dir, ignore_errors=True)
