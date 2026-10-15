"""窗口 exe 的冻结态入口（PyInstaller onedir 的 window 通道）。

窗口版 **stdout 不接终端**，所以除了启动界面，还必须提供一条**脚本化验收通路**：
``rcc-gui.exe --selftest <输出文件>``——把装配结果（页签数 / 数据目录 / 生效
参数数 / 版本）写进 JSON 文件，退出码携带成败。没有它，window exe 就只能靠
"人眼点一下"，而那不可复验。

页签数只在**这里**装配（不在 ``rcc.selftest`` 里）：``selftest`` 属核心层，
让它 import GUI 会把 PySide6 拖进 CLI 的导入图，与"重件只在函数体内 import"
的分层纪律相悖。故窗口装配的观测落在启动器，核心自检保持零重件。
"""

import io
import json
import sys

# 窗口 exe 的 stdout/stderr 在 --windowed 下可能是 None 或不可写；
# 自检结论一律走文件回传，不依赖控制台。
_SELFTEST_FLAG = "--selftest"


def _write_json(path, payload):
    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        handle.write("\n")


def run_selftest(out_path):
    """装配窗口 + 跑核心自检，把结论写 JSON 文件；返回退出码。"""
    from rcc import selftest
    from rcc.gui import main_window

    report = selftest.run_selftest()
    try:
        _app, _window, tab_count = main_window.build_window()
        report["tab_count"] = tab_count
        report["checks"].append({
            "name": "tabs_assembled",
            "ok": tab_count == len(main_window.TABS),
            "detail": "页签 %d 个（登记 %d 个）" % (tab_count, len(main_window.TABS)),
        })
    except Exception as exc:  # noqa: BLE001 - 自检要把失败如实回传
        report["tab_count"] = 0
        report["checks"].append({
            "name": "tabs_assembled", "ok": False,
            "detail": "%s: %s" % (type(exc).__name__, exc),
        })
    report["ok"] = all(check["ok"] for check in report["checks"])
    _write_json(out_path, report)
    return 0 if report["ok"] else 1


def main(argv=None):
    from rcc._encoding import ensure_utf8_stdio

    ensure_utf8_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)

    if _SELFTEST_FLAG in argv:
        index = argv.index(_SELFTEST_FLAG)
        rest = argv[index + 1:]
        if not rest:
            # 窗口版 stderr 可能为 None（--windowed 无控制台），写入前先探测
            if sys.stderr is not None:
                sys.stderr.write("用法: rcc-gui --selftest <输出文件>\n")
            return 2
        return run_selftest(rest[0])

    from rcc.gui import main_window

    return main_window.run()


if __name__ == "__main__":
    sys.exit(main())
