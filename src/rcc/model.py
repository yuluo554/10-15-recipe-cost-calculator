"""数据模型：Decimal 金额类型、参数来源标记、导入三态。

口径纪律（见 plan/02）：金额与比率一律 ``Decimal``，JSON 加载用
``parse_float=Decimal``；float 尾差不可接受（要检出 1 分/1 个基点差异）。
"""

import json
from decimal import Decimal, ROUND_HALF_UP

# 呈现精度：金额/单价两位小数，比率四位小数（= 百分比两位）
MONEY_EXP = Decimal("0.01")
RATE_EXP = Decimal("0.0001")

# 参数来源类型（白名单）。未登记值一律拒绝进入计算路径。
SOURCE_KINDS = (
    "snapshot",           # 公开价格快照（含抓取日期）
    "user",               # 用户提供/配置
    "builtin_experience", # 内置经验默认值（非官方出处）
)

# 导入解析三态
STATUS_OK = "ok"
STATUS_INVALID = "invalid"
STATUS_UNKNOWN = "unknown"

# 参数条目三态（门控语义，见 plan/02 §3）
PARAM_VERIFIED = "verified"
PARAM_PENDING = "pending"
PARAM_INPUT_REQUIRED = "input_required"

# 计算作用域（门控按计算路径分作用域，不用"整包全 verified"当唯一门）
SCOPES = ("cost", "pricing", "alert")


class SourceMissing(ValueError):
    """参数未挂来源标记，或来源类型未登记。

    继承 ``ValueError`` 而非裸 ``Exception``：它是一条**输入不可用**的失败路径
    （plan/04 §三：``source`` 缺失 → ``source_missing`` 拒绝，退出码 2），
    必须被 CLI 的 ``except (ParamsError, ValueError)`` 捕获。裸 ``Exception``
    会从 CLI 逃逸成未捕获 traceback——那等于把"该报的错"变成"崩了"。

    ``code`` 供机读判据（测试断言它，不去匹配中文散文）。
    """

    code = "source_missing"


def to_decimal(value):
    """把输入安全转成 Decimal。

    float 一律先经 ``str`` 再转（直接 ``Decimal(float)`` 会带二进制尾差），
    字符串直接解析，Decimal 原样返回。
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError("bool 不是合法数值")
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        return Decimal(value.strip())
    raise TypeError("无法转成 Decimal 的类型: %r" % type(value).__name__)


def load_json_decimal(path):
    """读 JSON，浮点字段一律解析为 Decimal。"""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh, parse_float=Decimal, parse_int=Decimal)


def quantize_money(value):
    """金额/单价呈现口径：两位小数，ROUND_HALF_UP。"""
    return to_decimal(value).quantize(MONEY_EXP, rounding=ROUND_HALF_UP)


def quantize_rate(value):
    """比率呈现口径：四位小数（百分比两位），ROUND_HALF_UP。"""
    return to_decimal(value).quantize(RATE_EXP, rounding=ROUND_HALF_UP)


def make_source(kind, ref, date=None, note=None):
    """构造参数来源标记；kind 不在白名单即抛错（拒绝未挂来源的参数进计算路径）。"""
    if kind not in SOURCE_KINDS:
        raise SourceMissing("未登记的参数来源类型: %r" % (kind,))
    if not ref:
        raise SourceMissing("参数来源缺少 ref 标识")
    return {"kind": kind, "ref": ref, "date": date, "note": note}


def validate_source(source):
    """校验来源标记；缺失或类型未登记抛 ``SourceMissing``。"""
    if not isinstance(source, dict):
        raise SourceMissing("参数未挂来源标记")
    kind = source.get("kind")
    if kind not in SOURCE_KINDS:
        raise SourceMissing("未登记的参数来源类型: %r" % (kind,))
    if not source.get("ref"):
        raise SourceMissing("参数来源缺少 ref 标识")
    return source
