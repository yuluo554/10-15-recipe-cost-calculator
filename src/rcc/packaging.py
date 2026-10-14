"""数据定位与打包白名单（**放在包内**，不放仓库顶层）。

顶层命名空间是共享的：仓库顶层若出现 ``packaging.py``，会**遮蔽 PyPI 的
``packaging``**——而 PyInstaller 自身依赖它做版本判断，构建会崩且报错指向
莫名其妙处。放包内则无此风险。

本模块同时承载"装到哪"（``build_datas``）与"从哪找"（``find_data_dir``）
这同一件事的两面。
"""

import os
import sys

# 随包数据白名单（相对仓库根）。**单一事实源**：spec 只准经 build_datas() 取数据路径，
# 不得手写。新增数据目录必须同时登记在此，否则构建后断言报"白名单外多余"。
DATA_WHITELIST = (
    "data/rules/params.json",
    "data/snapshots",
    "data/samples",
    "data/truth",
)

# 禁区成分：这些目录**绝不能**进发行包（版权原文/开发过程材料）。
FORBIDDEN_IN_DIST = (
    "plan",
    "tests",
    "_private",
    ".git",
)


def repo_root():
    """仓库根（源码态 = 包的上一级；冻结态无意义，用 find_data_dir）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def is_frozen():
    """是否运行在 PyInstaller 冻结态。"""
    return bool(getattr(sys, "frozen", False))


def _frozen_data_candidates():
    """冻结态的数据目录候选，按优先级：

    1. ``sys._MEIPASS/data``（PyInstaller 6 内嵌）
    2. exe 目录 ``_internal/data``（PyInstaller 6 onedir）
    3. exe 目录 ``data``（PyInstaller 5 平铺布局）
    """
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "data"))
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidates.append(os.path.join(exe_dir, "_internal", "data"))
    candidates.append(os.path.join(exe_dir, "data"))
    return candidates


def find_data_dir(explicit=None):
    """定位数据目录。

    优先级（**改优先级属"动了会打挂测试"的口径变更**，配分支测试锁死）：

    1. 显式参数
    2. 环境变量 ``RCC_DATA_DIR``
    3. 冻结态：``_MEIPASS/data`` → ``_internal/data`` → ``exe目录/data``
    4. 源码态：仓库根 ``data/``
    5. CWD 上溯找 ``data/``
    """
    if explicit:
        return os.path.abspath(explicit)

    env = os.environ.get("RCC_DATA_DIR")
    if env:
        return os.path.abspath(env)

    if is_frozen():
        for candidate in _frozen_data_candidates():
            if os.path.isdir(candidate):
                return os.path.abspath(candidate)
        # 冻结态找不到内嵌数据 → 返回首选候选路径（由自检判定为 FAIL），
        # 绝不回落到开发机仓库（那会让"内嵌数据"验了个寂寞）
        return os.path.abspath(_frozen_data_candidates()[0])

    root_data = os.path.join(repo_root(), "data")
    if os.path.isdir(root_data):
        return os.path.abspath(root_data)

    cur = os.path.abspath(os.getcwd())
    while True:
        candidate = os.path.join(cur, "data")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    raise FileNotFoundError("未能定位数据目录（data/）")


def build_datas():
    """产出 PyInstaller ``datas`` 列表：``[(源路径, 包内相对目录), ...]``。

    只收白名单内**存在**的路径；禁区成分直接抛错（构建期即拦截，
    不等构建后扫描）。
    """
    root = repo_root()
    datas = []
    for rel in DATA_WHITELIST:
        head = rel.split("/", 1)[0]
        if head in FORBIDDEN_IN_DIST:
            raise ValueError("数据白名单包含禁区成分: %s" % rel)
        src = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.exists(src):
            continue
        dest = os.path.dirname(rel.replace("/", os.sep))
        datas.append((src, dest))
    return datas


def frozen_data_is_inside_dist(exe_dir, data_dir):
    """冻结态自检：数据目录必须落在 exe 目录之内。

    非冻结态返回 ``None``（**不让源码运行被误判为 FAIL**）。
    """
    if not is_frozen():
        return None
    exe_dir = os.path.abspath(exe_dir)
    data_dir = os.path.abspath(data_dir)
    try:
        common = os.path.commonpath([exe_dir, data_dir])
    except ValueError:
        return False
    return common == exe_dir
