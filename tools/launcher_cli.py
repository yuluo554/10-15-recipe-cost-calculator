"""控制台 exe 的冻结态入口（PyInstaller onedir 的 console 通道）。

启动器只做两件事：**装入口编码守卫**，然后把控制权交给 ``rcc.cli``。判定逻辑
一律留在包内——启动器不承担任何业务判断，否则同一判断会长出第二份实现
（plan/06 硬纪律）。

独立成文件而不直接拿 ``src/rcc/cli.py`` 当入口：PyInstaller 会把入口脚本当
顶层模块执行，``cli.py`` 里的 ``from . import __version__`` 这类**包内相对导入**
在"顶层脚本"位置会直接 ImportError。
"""

import sys


def main():
    from rcc._encoding import ensure_utf8_stdio
    from rcc.cli import main as cli_main

    ensure_utf8_stdio()
    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
