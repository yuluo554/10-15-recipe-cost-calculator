"""命令行入口。

退出码语义（锁进 CLI 测试，重构不漂移）：

===== ==========================================================
0     完成 / 全部合规 / 基准达标
1     降级完成（有异常行或未启用套件）/ 检出问题 / 基准未达标
2     输入不可用（文件缺失、格式坏、参数错误）/ 用法错误
3     缺可选依赖（如 PySide6 未安装）
===== ==========================================================

**批量通路的退出码纪律**：失败件（坏文件/不可解析）是"未判定"，记 ``parse_error``，
**不改变退出码**——"没判定"与"判出问题"是两种不同的退出码语义。
"""

import argparse
import json
import os
import sys

from . import __version__
from ._encoding import ensure_utf8_stdio

EXIT_OK = 0
EXIT_DEGRADED = 1
EXIT_USAGE = 2
EXIT_NO_DEP = 3


def build_parser():
    parser = argparse.ArgumentParser(
        prog="rcc",
        description="菜谱/食堂采购成本核算器（确定性规则引擎，纯本地运行）",
    )
    parser.add_argument("--version", action="version",
                        version="recipe-cost-calculator %s" % __version__)
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="端到端核算：导入 → 成本卡 → 定价 →（可选）预警")
    p_run.add_argument("--purchases", help="进货单文件（CSV）")
    p_run.add_argument("--bom", help="菜品配方 BOM 文件（JSON）")
    p_run.add_argument("--params", help="参数包路径（默认随包数据）")
    p_run.add_argument("--snapshots", nargs="*", default=[],
                       help="两期价格快照（用于波动预警，按旧→新顺序）")
    p_run.add_argument("--with-alert", action="store_true",
                       help="启用价格波动预警（未启用时报告显式写出「本次未启用」）")
    p_run.add_argument("--report", help="报告输出前缀（同时产出 .md 与 .xlsx）")
    p_run.add_argument("--json", action="store_true", help="以 JSON 输出结果")

    p_check = sub.add_parser("check", help="校验输入数据（不产出报告）")
    p_check.add_argument("--purchases", help="进货单文件（CSV）")
    p_check.add_argument("--bom", help="菜品配方 BOM 文件（JSON）")
    p_check.add_argument("--params", help="参数包路径（默认随包数据）")

    p_bench = sub.add_parser("bench", help="跑内置基准套件")
    p_bench.add_argument("--only", action="append", default=[],
                         help="只跑指定套件（可重复）；未知名 → 退出码 2")
    p_bench.add_argument("--json", action="store_true", help="以 JSON 输出结果")

    p_self = sub.add_parser("selftest", help="冻结态/源码态自检")
    p_self.add_argument("--out", help="把自检结果写 JSON 文件（窗口版无 stdout 时的回传通路）")

    sub.add_parser("gui", help="启动桌面界面（需安装 gui extra）")
    return parser


def cmd_run(args):
    from .engine import pipeline
    from .rules.params import ParamsError, ParamsInputRequired, ParamsPending

    try:
        result = pipeline.compute_full(args)
    except FileNotFoundError as exc:
        print("输入不可用: %s" % exc, file=sys.stderr)
        return EXIT_USAGE
    except ParamsPending as exc:
        print("门控拦截: %s" % exc, file=sys.stderr)
        print("（该作用域存在待核对参数，判定路径已阻断）", file=sys.stderr)
        return EXIT_DEGRADED
    except ParamsInputRequired as exc:
        print("需要外部输入: %s" % exc, file=sys.stderr)
        print("（这些参数本不由参数包承载，请显式提供；不提供则无法继续）", file=sys.stderr)
        return EXIT_USAGE
    except (ParamsError, ValueError) as exc:
        print("输入不可用: %s" % exc, file=sys.stderr)
        return EXIT_USAGE

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(result["summary"])
        # 摘要写着"见清单"，就必须真有清单可看（否则是指向空处的指路语）
        for line in pipeline.render_issues(result.get("warnings") or []):
            print(line)

    if args.report:
        from .report import export

        export.write_reports(result, args.report)

    return EXIT_DEGRADED if result.get("warnings") else EXIT_OK


def cmd_check(args):
    from .engine import pipeline
    from .rules.params import ParamsError, ParamsInputRequired, ParamsPending

    try:
        report = pipeline.check_inputs(args)
    except FileNotFoundError as exc:
        print("输入不可用: %s" % exc, file=sys.stderr)
        return EXIT_USAGE
    except ParamsPending as exc:
        print("门控拦截: %s" % exc, file=sys.stderr)
        return EXIT_DEGRADED
    except ParamsInputRequired as exc:
        print("需要外部输入: %s" % exc, file=sys.stderr)
        return EXIT_USAGE
    except (ParamsError, ValueError) as exc:
        print("输入不可用: %s" % exc, file=sys.stderr)
        return EXIT_USAGE

    print(report["summary"])
    for line in pipeline.render_issues(report.get("issues") or []):
        print(line)
    return EXIT_DEGRADED if report.get("issues") else EXIT_OK


def cmd_bench(args):
    from benchmark import runner

    try:
        result = runner.run_suites(only=args.only)
    except runner.UnknownSuite as exc:
        print("用法错误: %s" % exc, file=sys.stderr)
        return EXIT_USAGE
    except runner.ConfigError as exc:
        print("基准配置错误: %s" % exc, file=sys.stderr)
        return EXIT_USAGE

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(runner.render_text(result))
    return EXIT_OK if result["passed"] else EXIT_DEGRADED


def cmd_selftest(args):
    from . import selftest

    report = selftest.run_selftest()
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.out:
        # 窗口版 exe 无 stdout，结论写文件回传；退出码携带成败
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
        print("自检结果已写入: %s" % args.out)
    else:
        print(text)
    return EXIT_OK if report["ok"] else EXIT_DEGRADED


def cmd_gui(args):
    """启动桌面界面。

    **惰性导入的边界不是 import 语句，是"第一个真正触及重件的调用"**——
    分层守门要求重件只在函数体内 import，所以 ``gui`` 包的顶层并不 import
    PySide6，``import rcc.gui`` 本身永不抛 ImportError，真正的缺依赖异常发生在
    后面的 ``build_app()``。因此 try 必须包住**从 import 到调用完成**的整段。
    """
    try:
        from .gui import main_window

        return main_window.run()
    except ImportError as exc:
        print("未安装界面依赖（PySide6）: %s" % exc, file=sys.stderr)
        if getattr(sys, "frozen", False):
            print("本发行包未内嵌该功能。", file=sys.stderr)
        else:
            print('请先安装: python -m pip install -e ".[gui]"', file=sys.stderr)
        return EXIT_NO_DEP


COMMANDS = {
    "run": cmd_run,
    "check": cmd_check,
    "bench": cmd_bench,
    "selftest": cmd_selftest,
    "gui": cmd_gui,
}


def main(argv=None):
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return EXIT_USAGE
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
