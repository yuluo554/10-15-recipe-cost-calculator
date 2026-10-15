"""零字面量门禁：业务数值只能来自参数包，不得抄进代码。

**token 全部运行时实算**——从 ``data/rules/params.json`` 读出全部数值（原样字符串
形式 + 对应小数形式），源码与留档**零词面**。这与 check_literals 的"token 从规则包
实算"是同一条原则：**门禁自己的输入也不许是代码字面量**。

扫描面随交付形态扩张（引擎 → CLI → 报告 → GUI → benchmark），**含 docstring 与注释**。

豁免口径（写死，否则门禁刷屏）：精度/基数约定 ``0``/``1``/``2``/``100``/``0.01``/
``0.0001`` 属精度约定而非业务数值，不参与扫描；匹配一律带词边界，防 ``0.8`` 命中 ``0.85``。
"""

import argparse
import ast
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _guard import ensure_utf8_stdio  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAMS_PATH = os.path.join(REPO_ROOT, "data", "rules", "params.json")

# 扫描面：随交付形态扩张。新增交付形态时要问"它该不该进扫描面？"
#
# **M3 复核收紧**：原先逐目录枚举（engine/alert/rules/report/gui/cli.py/benchmark）
# 会漏掉同属计算路径的模块——`selftest.py` 就曾带着手写的公式探针数值待在面外，
# 悄悄长出了第二份口径。枚举式扫描面的失效模式是"漏一个文件而不自知"，
# 故改为**整包扫描** `src/rcc`（含 io/selftest/packaging/model 等全部子模块），
# 使"计算路径上的任何源码"都无处可逃。
SCAN_GLOBS = (
    "src/rcc",
    "benchmark",
)

# 精度/基数约定豁免（非业务数值）。**从 rcc.model 的精度定义实算**，
# 不手写第二份——量化精度与半步都是精度约定，不属业务数值。
def _exempt_values():
    from decimal import Decimal

    src = os.path.join(REPO_ROOT, "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from rcc.model import MONEY_EXP, RATE_EXP  # noqa: PLC0415

    values = {"0", "1", "2", "100", "0.0", "1.0"}
    for exp in (MONEY_EXP, RATE_EXP):
        values.add(format(exp.normalize(), "f"))
        values.add(format(exp, "f"))
        values.add(format(exp / 2, "f"))
        values.add(str(int(exp * 100)) if exp * 100 == int(exp * 100) else "")
    return frozenset(v for v in values if v)


EXEMPT_VALUES = _exempt_values()


def collect_values(obj, out=None):
    """递归收集参数包里的全部数值（保留原样字符串形式与规范化形式）。"""
    if out is None:
        out = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ("status", "kind", "date", "ref", "note", "schema_version",
                       "generated_by"):
                continue
            collect_values(value, out)
    elif isinstance(obj, list):
        for value in obj:
            collect_values(value, out)
    elif isinstance(obj, (int, float, str)):
        text = str(obj).strip()
        if not text:
            return out
        try:
            from decimal import Decimal

            dec = Decimal(text)
        except Exception:  # noqa: BLE001 - 非数值字符串不参与
            return out
        out.add(text)
        normalized = format(dec.normalize(), "f")
        out.add(normalized)
        # 百分比形态（0.6 → 60）与反向形态
        out.add(format(dec * 100, "f"))
        out.add(format(dec / 100, "f"))
    return out


def banned_tokens(params_path=PARAMS_PATH):
    """从参数包实算禁用 token 集（**运行时实算，源码零词面**）。"""
    with open(params_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    values = collect_values(data)
    tokens = set()
    for text in values:
        if text in EXEMPT_VALUES:
            continue
        # 过滤过短/无意义的形式
        stripped = text.lstrip("-").rstrip("0").rstrip(".")
        if not stripped:
            continue
        tokens.add(text)
    return sorted(tokens, key=len, reverse=True)


def _token_regex(token):
    """词边界正则：防 ``0.8`` 命中 ``0.85`` 的子串。

    尾边界除数字外还排除 ``\\.[0-9]``——防把版本号一类**更长的点分数字串**
    （如 ``0.1.0``）误判成业务数值 ``0.1``。这类误报会让门禁刷屏，而刷屏的门禁
    最终会被"加豁免"加到失效。
    """
    escaped = re.escape(token)
    return re.compile(r"(?<![0-9.])" + escaped + r"(?![0-9]|\.[0-9])")


def scan_text(text, tokens):
    """扫描一段文本，返回命中列表 ``[(token, line_no, line_text)]``。"""
    hits = []
    lines = text.splitlines()
    for token in tokens:
        pattern = _token_regex(token)
        for line_no, line in enumerate(lines, start=1):
            if pattern.search(line):
                hits.append((token, line_no, line.strip()))
    return hits


def _iter_files():
    for rel in SCAN_GLOBS:
        target = os.path.join(REPO_ROOT, rel.replace("/", os.sep))
        if os.path.isfile(target):
            yield rel, target
        elif os.path.isdir(target):
            for dirpath, dirnames, filenames in os.walk(target):
                dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
                for filename in sorted(filenames):
                    if filename.endswith(".py"):
                        full = os.path.join(dirpath, filename)
                        yield os.path.relpath(full, REPO_ROOT).replace(os.sep, "/"), full


def scan_repo(tokens=None, params_path=PARAMS_PATH):
    """扫描全部扫描面，返回 ``[(rel_path, token, line_no, line_text)]``。"""
    tokens = tokens if tokens is not None else banned_tokens(params_path)
    results = []
    for rel, path in _iter_files():
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        for token, line_no, line in scan_text(text, tokens):
            results.append((rel, token, line_no, line))
    return results


def selftest():
    """阳性/阴性对照——**无自检的门禁可能一直是空扫**。

    阳性：程序化合成含禁用 token 的假源码 → 必须报红。
    阴性：干净字符串 → 不得报红。
    夹具全部程序化合成，源码里无任何真实业务数值词面。
    """
    tokens = banned_tokens()
    if not tokens:
        print("LITERAL_GATE_SELFTEST_FAIL: token 集为空（参数包没读出数值？）")
        return 1

    # 阳性对照：用 token 本身拼一段假源码
    probe_token = tokens[0]
    fake_source = "net_price = purchase / %s\n" % probe_token
    positive = scan_text(fake_source, tokens)
    if not positive:
        print("LITERAL_GATE_SELFTEST_FAIL: 阳性对照未报红（token=%r）" % probe_token)
        return 1

    # 阴性对照：干净源码
    clean_source = "net_price = purchase / yield_rate\n"
    negative = scan_text(clean_source, tokens)
    if negative:
        print("LITERAL_GATE_SELFTEST_FAIL: 阴性对照误报 %r" % (negative,))
        return 1

    # 子串边界对照：token 的前缀不应被误报为独立 token
    if len(probe_token) > 1:
        prefix = probe_token[:-1]
        if scan_text("value = %s9\n" % prefix, tokens):
            print("LITERAL_GATE_SELFTEST_FAIL: 前缀 %r 被误报（词边界失效）" % prefix)
            return 1

    # 版本号对照：更长的点分数字串（如 0.1.0）不得被误判为业务数值 0.1。
    # 这条与扫描面纳入 __init__.py 同时生效——否则门禁会因版本号刷屏。
    for short in ("0.1", "0.6", "0.8"):
        if short not in tokens:
            continue
        version_like = "version = %s.0\n" % short
        if scan_text(version_like, tokens):
            print("LITERAL_GATE_SELFTEST_FAIL: 版本号形态 %r 被误报为业务数值 %r"
                  % (version_like.strip(), short))
            return 1

    print("LITERAL_GATE_SELFTEST_OK")
    return 0


def main(argv=None):
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="零字面量门禁")
    parser.add_argument("--selftest", action="store_true", help="跑阳性/阴性对照")
    parser.add_argument("--params", default=PARAMS_PATH, help="参数包路径")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    tokens = banned_tokens(args.params)
    hits = scan_repo(tokens, args.params)
    if hits:
        print("LITERAL_GATE_FAIL: 源码含业务数值字面量（%d 处）" % len(hits))
        for rel, token, line_no, line in hits:
            # 输出掩码化：不复述完整 token 形态
            masked = token[0] + "*" * max(0, len(token) - 1)
            print("  %s:%d [%s]" % (rel, line_no, masked))
        return 1
    print("LITERAL_GATE_OK: 扫描面 %d 个入口，禁用 token %d 个，0 命中"
          % (len(list(_iter_files())), len(tokens)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
