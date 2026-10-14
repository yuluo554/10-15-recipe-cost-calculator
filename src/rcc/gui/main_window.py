"""主窗口（M0 骨架形态：页签装配 + 自检通路）。

**零判定逻辑**：本模块只做展示与转发——所有数值与结论都来自
``..engine.pipeline``；不做任何算术、不内联任何业务数值。

重件（PySide6）只在函数体内 import——这是分层守门要求的形态。
"""

from .. import __version__

TABS = ("核算", "预警", "参数", "关于")


def _qt_widgets():
    """在函数体内取 Qt 符号。"""
    from PySide6 import QtWidgets  # noqa: PLC0415

    return QtWidgets


def build_window():
    """装配主窗口，返回 ``(app, window, tab_count)``。"""
    QtWidgets = _qt_widgets()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = QtWidgets.QMainWindow()
    window.setWindowTitle("菜谱/食堂采购成本核算器")

    tabs = QtWidgets.QTabWidget()
    for name in TABS:
        page = QtWidgets.QWidget()
        page.setObjectName("tab_%s" % name)
        tabs.addTab(page, name)

    about_page = tabs.widget(TABS.index("关于"))
    layout = QtWidgets.QVBoxLayout(about_page)
    layout.addWidget(QtWidgets.QLabel(
        "版本 %s｜纯本地运行，无账号、无上传、无遥测" % __version__))
    layout.addWidget(QtWidgets.QLabel(
        "本工具为辅助核算工具；参数默认值为经验值，非官方数据。"))

    window.setCentralWidget(tabs)
    return app, window, tabs.count()


def build_app():
    """构造并显示窗口（CLI ``gui`` 子命令的入口）。"""
    app, window, _tab_count = build_window()
    window.show()
    return app.exec()


def run():
    """CLI 入口：返回进程退出码。"""
    return build_app()
