"""入口编码守卫。

Windows 控制台/管道的默认编码可能是 cp936 或 cp1252，向它打印中文会抛
``UnicodeEncodeError``。本模块提供统一入口守卫，**所有会打印的可执行入口
（CLI 与 tools/ 下每个脚本）都必须在 main 的最开头调用它**。

设计要点：按 ``stream.encoding`` 探针决定是否 reconfigure——中文控制台
（cp936）本身能编码中文，动它反而可能出问题；只有编码能力不足的流才重设。
"""

import sys

_UTF8_NAMES = ("utf-8", "utf8", "cp65001", "utf_8")


def _needs_reconfigure(stream):
    """该流是否需要重设为 UTF-8。"""
    if stream is None:
        return False
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        # 无编码信息（如被重定向到无编码的包装器）时保守重设
        return hasattr(stream, "reconfigure")
    return encoding.replace("_", "-").lower() not in _UTF8_NAMES


def ensure_utf8_stdio():
    """把 stdout/stderr 重设为 UTF-8，返回被重设的流名列表。

    幂等；对不支持 reconfigure 的流（如 pytest 的捕获对象）静默跳过。
    """
    changed = []
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if not _needs_reconfigure(stream):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            continue
        changed.append(name)
    return changed
