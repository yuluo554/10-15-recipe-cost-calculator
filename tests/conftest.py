"""共享夹具。

**测试期依赖纪律**：测试套件真 import 的每个库都必须在 README 快速开始那条
安装命令的 extras 里（``.[dev]``）——否则干净 venv 里会硬失败。
"""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")
for path in (SRC, REPO_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(scope="session")
def repo_root():
    return REPO_ROOT


@pytest.fixture(scope="session")
def params_path():
    """参数包路径（冻结产物）。"""
    path = os.path.join(REPO_ROOT, "data", "rules", "params.json")
    if not os.path.isfile(path):
        pytest.fail("参数包缺失，请先跑 tools/gen_params.py")
    return path


@pytest.fixture(scope="session")
def samples_dir():
    path = os.path.join(REPO_ROOT, "data", "samples")
    if not os.path.isdir(path):
        pytest.fail("样例目录缺失，请先跑 tools/gen_samples.py")
    return path


@pytest.fixture
def write_text_lf():
    """写文本文件并固定 LF 行尾。

    **不用 ``Path.write_text(newline=)``**——该参数是 Python 3.10+ 才有，
    3.8（本项目底线）上直接 TypeError。统一走 ``open(..., newline="\\n")``。
    """

    def _write(path, text):
        with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return str(path)

    return _write
