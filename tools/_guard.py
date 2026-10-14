"""tools/ 脚本的公共入口守卫。

**所有会打印的可执行入口都必须在 main 最开头调用 ``ensure_utf8_stdio()``**，
包括里程碑后期新增的脚本——不是只守主 CLI。这条纪律由守门测试
（``tests/guards/test_entry_guards.py``）以 AST/正则方式强制。
"""

import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from rcc._encoding import ensure_utf8_stdio  # noqa: E402,F401
