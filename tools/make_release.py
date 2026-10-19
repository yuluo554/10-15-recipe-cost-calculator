"""发布物组装与留档（plan/05 §五、§六；M6）。

两步各一子命令，**可复跑的是第一步**：

- ``zip``：把一个 dist 目录打成**确定性** zip（``ZIP_STORED`` + 条目按路径显式
  sort + 全条目固定 ``date_time`` + ``create_system=0``）。纪律与
  ``report/export.py`` 的机读产物同源（K12）——不同处在于本工具打的是**目录树**，
  故必须先 ``os.walk`` 收集再显式排序：``os.walk`` 的产出顺序跨调用不稳定，
  实测不排序则两次打包字节不同；
- ``ledger``：对产物算 sha256 / 字节数并输出 JSON，供发布留档直接引用，
  避免手抄 64 位 hex（错一位肉眼不可查）。

**"可复跑"边界的诚实口径**（写进留档，不许含糊）：

- **同 dist → 同 zip 逐字节一致**（本工具保证，实测背书）；
- **exe 构建本身不承诺跨机字节一致**——PyInstaller 的产物受编译期环境
  （bootloader 构建、依赖版本、路径）影响。把 exe 哈希也写成"可复现"是假的。

**归档内路径前缀**：zip 内一律用 ASCII 顶层目录 ``rcc/``，解压即得
``rcc/rcc.exe`` + ``rcc/_internal/``——与 README「下载即用」一节的命令逐字对应。
"""

import argparse
import hashlib
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _guard import ensure_utf8_stdio  # noqa: E402

# zip 内顶层目录名（ASCII；解压后即 README 里 `rcc/rcc.exe selftest` 的那一层）
ARCHIVE_TOP = "rcc"

# 固定时间戳（同 export.py 的口径）。值本身是"最小可表达 DOS 时间"，
# 不是业务数值，故不在零字面量门禁的禁用 token 集里。
FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)

# 归档内的可执行文件应保留该属性位（解压后仍带可执行权限）
EXEC_MODE = 0o755 << 16
FILE_MODE = 0o644 << 16


def _iter_files(root):
    """收集 ``(归档内相对路径, 绝对路径)``，**按路径显式排序**。

    排序是确定性的**必要条件**：``os.walk`` 依赖文件系统的目录项顺序，
    同一台机器两次调用都可能不同，跨机器更不必说。
    """
    entries = []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            entries.append((rel, path))
    entries.sort(key=lambda item: item[0])
    return entries


def _write_zip(dist_root, out_path, top=ARCHIVE_TOP):
    """把 ``dist_root`` 打成确定性 zip，返回归档内条目名列表。"""
    dist_root = os.path.abspath(dist_root)
    if not os.path.isdir(dist_root):
        raise FileNotFoundError("dist 目录不存在: %s" % dist_root)

    entries = _iter_files(dist_root)
    if not entries:
        raise ValueError("dist 目录为空: %s" % dist_root)

    names = []
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as archive:
        for rel, path in entries:
            arcname = "%s/%s" % (top, rel)
            info = zipfile.ZipInfo(arcname, date_time=FIXED_DATE_TIME)
            info.create_system = 0
            info.external_attr = EXEC_MODE if path.endswith(".exe") else FILE_MODE
            with open(path, "rb") as handle:
                archive.writestr(info, handle.read())
            names.append(arcname)
    return names


def _sha256_of(path):
    """流式算文件 sha256（114MB 的产物不进内存）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cmd_zip(args):
    names = _write_zip(args.dist, args.out, top=args.top)
    digest = _sha256_of(args.out)
    size = os.path.getsize(args.out)
    print("ZIP_OK: %s" % args.out)
    print("  条目 %d" % len(names))
    print("  sha256 %s" % digest)
    print("  字节 %d" % size)
    return 0


def cmd_ledger(args):
    """算 sha256 / 字节数，输出 JSON（供留档引用，**不手抄**）。"""
    rows = []
    for path in args.artifacts:
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            print("LEDGER_FAIL: 产物不存在: %s" % path, file=sys.stderr)
            return 2
        rows.append({
            "name": os.path.basename(path),
            "bytes": os.path.getsize(path),
            "sha256": _sha256_of(path),
        })
    payload = {
        "generated_by": "tools/make_release.py ledger",
        "note": "可复跑范围 = '同 dist → 同 zip'；exe 构建本身不承诺跨机字节一致",
        "artifacts": rows,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        print("LEDGER_OK: %s" % args.out)
    else:
        sys.stdout.write(text)
    return 0


def cmd_verify(args):
    """两次独立打包 → **逐字节一致**（这条是本工具唯一承诺的可复跑性）。"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        first = os.path.join(tmp, "a.zip")
        second = os.path.join(tmp, "b.zip")
        _write_zip(args.dist, first, top=args.top)
        _write_zip(args.dist, second, top=args.top)
        digest_a = _sha256_of(first)
        digest_b = _sha256_of(second)
    if digest_a != digest_b:
        print("RELEASE_ZIP_UNSTABLE: 两次打包字节不同（%s vs %s）"
              % (digest_a[:12], digest_b[:12]))
        return 1
    print("RELEASE_ZIP_DETERMINISTIC_OK: %s" % digest_a)
    return 0


# --------------------------------------------------- 构建后 --check 三断言

def _covered_by_whitelist(rel_in_data, whitelist):
    """归档内某数据文件是否落在白名单内（``rel_in_data`` 相对 ``data/``）。"""
    full = "data/" + rel_in_data
    for entry in whitelist:
        if full == entry or full.startswith(entry + "/"):
            return True
    return False


def check_dist(dist_root, repo_root, whitelist, forbidden):
    """构建后三断言，返回问题清单（空 = 通过）。

    plan/05 §三 的"构建后扫描"（三处守门互相独立，改一处口径必同步另两处）：

    1. **dist 顶层禁区成分扫描**——**只匹配顶层**：按任意层级扫会把依赖包自带的
       同名子目录（Qt 的某个 ``tests/``）当命中，而那是上游固有、不是我们的禁区；
    2. **内嵌数据逐份 sha256 对账**——包内数据必须与仓库内同相对路径的字节一致；
       不一致即"产物与源码基线脱钩"（改了数据没重建，或打包过程损坏）；
    3. **白名单外多余检测**——包内出现了白名单没登记的条目 = "悄悄多进了东西"
       （与构建前的 ``unregistered_data_dirs()`` 是同一件事的另一侧）。
    """
    dist_root = os.path.abspath(dist_root)
    repo_root = os.path.abspath(repo_root)
    problems = []

    if not os.path.isdir(dist_root):
        return ["dist 目录不存在: %s" % dist_root]

    # 断言一：dist 顶层（含 _internal 的顶层）不得出现禁区目录名
    forbidden = set(forbidden)
    tops = [("", dist_root), ("_internal", os.path.join(dist_root, "_internal"))]
    for label, base in tops:
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if name in forbidden and os.path.isdir(os.path.join(base, name)):
                problems.append("断言一：dist 顶层出现禁区目录 %s/%s"
                                % (label or ".", name))

    # 断言二 + 三：内嵌数据目录
    bundled = os.path.join(dist_root, "_internal", "data")
    if not os.path.isdir(bundled):
        problems.append("断言二/三：未找到内嵌数据目录 %s（数据没随包走？）" % bundled)
        return problems

    # 仓库侧对应物的位置**只从 rcc.packaging 取**（M7：数据搬进包内 src/rcc/data/）。
    # 不在此复制一份 "src/rcc/data"——两处各写一份就是第二份真相。
    from rcc.packaging import package_data_dir  # noqa: PLC0415

    source_root = package_data_dir(repo_root)

    seen = []
    for dirpath, dirnames, filenames in os.walk(bundled):
        dirnames.sort()
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, bundled).replace(os.sep, "/")
            seen.append(rel)

            # 断言三：白名单外多余
            if not _covered_by_whitelist(rel, whitelist):
                problems.append("断言三：包内数据不在白名单内 %s" % rel)
                continue

            # 断言二：与仓库内同相对路径的字节一致
            counterpart = os.path.join(source_root, rel.replace("/", os.sep))
            if not os.path.isfile(counterpart):
                problems.append("断言二：仓库内缺少对应文件 %s" % counterpart)
                continue
            if _sha256_of(path) != _sha256_of(counterpart):
                problems.append("断言二：包内数据与仓库不一致 %s" % counterpart)

    if not seen:
        problems.append("断言二/三：内嵌数据目录为空")
    return problems


def cmd_check(args):
    """构建后三断言（任一违反 → exit 1）。"""
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
    from rcc.packaging import DATA_WHITELIST, FORBIDDEN_IN_DIST

    repo_root = args.repo_root or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    problems = check_dist(args.dist, repo_root, DATA_WHITELIST, FORBIDDEN_IN_DIST)

    if problems:
        print("DIST_CHECK_FAIL: %d 项" % len(problems))
        for problem in problems:
            print("  %s" % problem)
        return 1
    print("DIST_CHECK_OK: 禁区成分 0 / 内嵌数据逐份一致 / 白名单外多余 0")
    return 0


def main(argv=None):
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="发布物组装与留档（确定性 zip + sha256）")
    sub = parser.add_subparsers(dest="command")

    p_zip = sub.add_parser("zip", help="把 dist 目录打成确定性 zip")
    p_zip.add_argument("--dist", required=True, help="dist/原目录（如 .../dist/rcc）")
    p_zip.add_argument("--out", required=True, help="输出 zip 路径")
    p_zip.add_argument("--top", default=ARCHIVE_TOP, help="归档内顶层目录名")
    p_zip.set_defaults(func=cmd_zip)

    p_ledger = sub.add_parser("ledger", help="算产物 sha256/字节数并输出 JSON")
    p_ledger.add_argument("--artifacts", nargs="+", required=True, help="产物路径")
    p_ledger.add_argument("--out", help="输出 JSON 路径（缺省打 stdout）")
    p_ledger.set_defaults(func=cmd_ledger)

    p_verify = sub.add_parser("verify", help="两次独立打包比对字节")
    p_verify.add_argument("--dist", required=True, help="dist/原目录")
    p_verify.add_argument("--top", default=ARCHIVE_TOP, help="归档内顶层目录名")
    p_verify.set_defaults(func=cmd_verify)

    p_check = sub.add_parser("check", help="构建后三断言（禁区/数据一致/白名单外多余）")
    p_check.add_argument("--dist", required=True, help="dist/原目录（如 .../dist/rcc）")
    p_check.add_argument("--repo-root", help="仓库根（缺省取本脚本上一级）")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_usage(sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
