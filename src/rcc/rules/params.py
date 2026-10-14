"""参数包门控 —— 按计算路径分作用域。

设计要点（plan/02 §3）：

- 参数包是生成器产出的**冻结产物**，禁手改；
- 每个条目挂三态之一：``verified``（放行）/ ``pending``（**阻断该 scope 的判定路径**）
  / ``input_required``（**放行门控**，但运行时显式索取，缺失即 exit 2——
  **绝不静默取默认值**）；
- 门控**按计算路径分作用域**（``cost`` / ``pricing`` / ``alert``），各只校验自己
  引用的条目。不用"整包全 verified"当唯一门——否则与核算无关的 pending 会阻断
  整个核算路径。

判别口诀：**"未核对"与"本不由参数包承载"是两回事**。
"""

import os

from ..model import (
    PARAM_INPUT_REQUIRED,
    PARAM_PENDING,
    PARAM_VERIFIED,
    SCOPES,
    SourceMissing,
    load_json_decimal,
    validate_source,
)

# 作用域 → 参数包内的分区名
SCOPE_SECTIONS = {
    "cost": "yield_rates",
    "pricing": "pricing",
    "alert": "alert",
}


class ParamsError(Exception):
    """参数包本身不可用（缺文件/结构坏/scope 未登记）。"""


class ParamsPending(Exception):
    """该作用域引用了 ``pending`` 条目 → 阻断判定路径（CLI 退出码 1）。"""

    def __init__(self, scope, items):
        self.scope = scope
        self.items = list(items)
        super().__init__(
            "作用域 %s 存在待核对参数，判定路径已阻断: %s"
            % (scope, ", ".join(self.items))
        )


class ParamsInputRequired(Exception):
    """该作用域引用了 ``input_required`` 条目 → 放行门控，但运行时必须索取。

    调用方须显式向用户索取这些值；缺失即退出码 2，**不得回落到默认值**。
    """

    def __init__(self, scope, items):
        self.scope = scope
        self.items = list(items)
        super().__init__(
            "作用域 %s 需要外部输入（本不由参数包承载）: %s"
            % (scope, ", ".join(self.items))
        )


def default_params_path():
    """参数包默认路径（随包数据，经 ``find_data_dir`` 定位）。"""
    from ..packaging import find_data_dir

    return os.path.join(find_data_dir(), "rules", "params.json")


def load_params(path=None):
    """读参数包（金额/比率解析为 Decimal）。"""
    path = path or default_params_path()
    if not os.path.isfile(path):
        raise ParamsError("参数包不存在: %s" % path)
    data = load_json_decimal(path)
    if not isinstance(data, dict):
        raise ParamsError("参数包根节点必须是对象")
    for scope, section in SCOPE_SECTIONS.items():
        if section not in data:
            raise ParamsError("参数包缺少分区 %r（作用域 %s）" % (section, scope))
    return data


def _iter_entries(section):
    """遍历分区内的条目，产出 ``(名字, 条目字典)``。"""
    for name, entry in section.items():
        if isinstance(entry, dict) and "status" in entry:
            yield name, entry


def scope_report(data, scope):
    """列出某作用域的三态清单（供"未启用清单"打印，两状态显式可见）。"""
    if scope not in SCOPE_SECTIONS:
        raise ParamsError("未登记的计算作用域: %r" % (scope,))
    verified, pending, input_required = [], [], []
    for name, entry in _iter_entries(data[SCOPE_SECTIONS[scope]]):
        status = entry.get("status")
        if status == PARAM_VERIFIED:
            verified.append(name)
        elif status == PARAM_PENDING:
            pending.append(name)
        elif status == PARAM_INPUT_REQUIRED:
            input_required.append(name)
        else:
            raise ParamsError("条目 %r 的 status 未登记: %r" % (name, status))
    return {"scope": scope, "verified": verified, "pending": pending,
            "input_required": input_required}


def effective_params(scope, path=None):
    """取某作用域下**可参与判定**的参数（只含 verified 条目）。

    - 引用了 ``pending`` 条目 → 抛 ``ParamsPending``（阻断判定路径）；
    - 引用了 ``input_required`` 条目 → 抛 ``ParamsInputRequired``（放行门控，
      但调用方必须运行时索取，**绝不静默取默认值**）；
    - 每个条目的 ``source`` 都经 ``validate_source`` 校验，未挂来源即抛
      ``SourceMissing``（**未挂来源的参数不得进入计算路径**）。
    """
    data = load_params(path)
    report = scope_report(data, scope)
    if report["pending"]:
        raise ParamsPending(scope, report["pending"])
    if report["input_required"]:
        raise ParamsInputRequired(scope, report["input_required"])

    section = data[SCOPE_SECTIONS[scope]]
    out = {}
    for name, entry in _iter_entries(section):
        try:
            validate_source(entry.get("source"))
        except SourceMissing:
            raise
        out[name] = entry
    return out
