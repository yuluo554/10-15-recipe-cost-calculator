"""GUI 层测试夹具。

**offscreen 必须在 import PySide6 之前设好**：Qt 在创建 ``QApplication`` 时读取
``QT_QPA_PLATFORM``，之后再设已无意义（CI 无显示服务器时当场失败）。放在
conftest 的模块层而非测试函数里，是为了保证它先于任何 Qt import 生效。

重件的缺失**不在本文件处理**——那是各测试模块的 ``importorskip`` 声明式跳过，
与"分层门禁类测试必须恒跑"（在 ``tests/guards/``）互不影响。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
