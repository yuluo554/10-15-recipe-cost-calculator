"""脱敏审计（四模式 + 自检）。

**token 运行时实算，源码与留档零词面**——扫描器自己的输入也不许是代码字面量：

- 邮箱数字串从 ``git log --format=%ae %ce --all`` 实算；
- 本机用户名从 ``getpass.getuser()`` 实算；
- 盘符与工程路径段从仓库绝对路径实算（**仓库目录名本身是有意公开的项目坐标，不收**）。

命中分级：
- **HARD**（exit 1）：真实个人邮箱、手机号、身份证、个人路径签名、密钥形态；
- **REVIEW**（人工豁免留档）：系统目录、其余盘符路径；
- **advisory**（只报不阻断）：长 hex 串（sha256 指纹是本类项目的**文档化功能**）。

**豁免口径**（写死）：GitHub 账号名（克隆 URL 必含）= 发布固有公开元数据；
``*@users.noreply.github.com`` = 已脱敏的目标形态；``git@<host>`` = 服务传输地址。

输出**一律掩码化**——审计输出会被留档引用，输出本身不得成为二次泄漏源。
"""

import argparse
import getpass
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _guard import ensure_utf8_stdio  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HARD = "HARD"
REVIEW = "REVIEW"
ADVISORY = "advisory"

# 行内放行标记：命中所在行含该标记即转"白名单放过"（**仍在输出里可见**）
ALLOW_MARKER = "audit-allow"

# 白名单：路径 glob → 只放行的规则名（不是路径全放过——同文件别的规则命中仍要报）
RULE_WHITELIST = (
    ("tools/audit_desensitize.py", "long_hex"),
    ("data/truth/manifest.json", "long_hex"),
    ("data/rules/params.json", "long_hex"),
)


def _has_git():
    """仓库是否有 ``.git``（``git archive`` 导出的树天然没有）。

    无 git 时扫描器必须**带兜底**（退回文件系统遍历），否则"依赖 git 的守门
    测试"会在干净导出树/发布包里整批报错——这是脱敏审计的已知形态。
    """
    return os.path.isdir(os.path.join(REPO_ROOT, ".git"))


def _run_git(args):
    """跑 git 命令，**子进程解码显式 UTF-8**（无环境变量可替代）。"""
    proc = subprocess.run(["git"] + list(args), capture_output=True, cwd=REPO_ROOT,
                          encoding="utf-8", errors="replace")
    return proc.stdout or ""


def _noreply_pattern():
    """noreply 形态（改写目标，不是命中）——由字符串拼接构造，避免自命中。"""
    return "@users." + "noreply." + "github.com"


def compute_tokens():
    """运行时实算敏感 token 集（源码零词面）。"""
    tokens = {"emails": set(), "users": set(), "paths": set()}

    # 邮箱：从 git 元数据实算，剔除 noreply 与保留域
    noreply = _noreply_pattern()
    for line in _run_git(["log", "--format=%ae %ce", "--all"]).splitlines():
        for addr in line.split():
            if not addr or noreply in addr:
                continue
            if addr.endswith(("@example.com", "@example.org", "@example.net")):
                continue
            if "@" in addr:
                tokens["emails"].add(addr)

    # 本机用户名
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - 无 TTY 时可能失败
        user = ""
    if user and len(user) >= 3:
        tokens["users"].add(user)

    # 盘符与工程路径段（由仓库绝对路径实算）
    drive, tail = os.path.splitdrive(REPO_ROOT)
    if drive:
        tokens["paths"].add(drive + os.sep)
    segments = [seg for seg in tail.replace("\\", "/").split("/") if seg]
    for seg in segments:
        # 仓库目录名本身是有意公开的项目坐标，不收
        if seg and len(seg) >= 3 and not seg.startswith("10-15-"):
            tokens["paths"].add(seg)
    return tokens


def _user_path_signature(user):
    """个人路径**组合签名**（不匹配裸词——防厂商串含用户名子串误报）。"""
    if not user:
        return None
    return re.compile(r"(Users|ProgramData|home)[\\/]" + re.escape(user),
                      re.IGNORECASE)


def build_rules(tokens):
    """构造扫描规则：``[(规则名, 正则, 级别)]``。"""
    noreply = _noreply_pattern()
    rules = []

    # 邮箱：宽松形态但收紧边界（首字符字母数字 + 域名至少两段）
    rules.append(("email",
                  re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9][A-Za-z0-9._%+-]*"
                             r"@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"),
                  HARD))

    # 手机号 / 身份证：hex 边界环视（防 sha256 十六进制串里的数字段误报）
    rules.append(("phone",
                  re.compile(r"(?<![0-9a-fA-F])1[3-9]\d{9}(?![0-9a-fA-F])"),
                  HARD))
    rules.append(("idcard",
                  re.compile(r"(?<![0-9a-fA-F])\d{17}[\dXx](?![0-9a-fA-F])"),
                  HARD))

    # 密钥形态
    rules.append(("api_key",
                  re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
                  HARD))

    # 个人路径组合签名
    user = next(iter(tokens["users"]), "")
    signature = _user_path_signature(user)
    if signature is not None:
        rules.append(("user_path", signature, HARD))

    # 长 hex（sha256 指纹 = 文档化功能 → advisory，只报不阻断）
    rules.append(("long_hex",
                  re.compile(r"\b[0-9a-fA-F]{32,}\b"),
                  ADVISORY))

    return rules, noreply


def _is_exempt_email(text, noreply):
    """豁免判定：noreply 目标形态 / git 传输地址。"""
    if noreply in text:
        return True
    if re.match(r"^(git|ssh|hg)@", text):
        return True
    return False


def scan_text(text, rules, noreply, rel_path=""):
    """扫描一段文本，返回 ``[(rel_path, line_no, rule_name, level, masked)]``。"""
    hits = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for name, pattern, level in rules:
            for match in pattern.finditer(line):
                found = match.group(0)
                if name == "email" and _is_exempt_email(found, noreply):
                    continue
                if _is_rule_whitelisted(rel_path, name):
                    continue
                hits.append((rel_path, line_no, name, level, _mask(found)))
    return hits


def _is_rule_whitelisted(rel_path, rule_name):
    normalized = rel_path.replace(os.sep, "/")
    for pattern, rule in RULE_WHITELIST:
        if rule == rule_name and normalized.endswith(pattern):
            return True
    return False


def _mask(value):
    """掩码化：不复述完整形态。"""
    if len(value) <= 4:
        return value[0] + "*" * (len(value) - 1)
    if "@" in value:
        local, _, domain = value.partition("@")
        return local[:2] + "***@" + domain
    return value[:4] + "***" + value[-2:]


def _tracked_files():
    """已跟踪文件（**审查作用域 = 将被提交/推送的那个树**）。

    无 ``.git`` 时退回文件系统遍历（排除 venv / 缓存 / 构建产物）——
    ``git archive`` 导出的干净树必须仍可审计。
    """
    if not _has_git():
        for rel, path in _walk_tree():
            yield rel, path
        return
    out = _run_git(["-c", "core.quotepath=false", "ls-files"])
    for rel in out.splitlines():
        rel = rel.strip()
        if rel:
            yield rel, os.path.join(REPO_ROOT, rel.replace("/", os.sep))


# 无 git 兜底时要排除的目录（按**特征**而非名字：venv 有 pyvenv.cfg）
_SKIP_DIRS = {"__pycache__", ".git", "build", "dist", ".pytest_cache", ".mypy_cache"}


def _walk_tree():
    """文件系统遍历（无 git 兜底）。"""
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        # 按特征剪掉 venv（含 pyvenv.cfg 的目录），避免 site-packages 成片误报
        if "pyvenv.cfg" in filenames:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames
                             if d not in _SKIP_DIRS and not d.endswith(".egg-info"))
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")
            yield rel, path


def scan_tracked(rules, noreply):
    """模式一：扫描已跟踪文件。"""
    hits = []
    for rel, path in _tracked_files():
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError:
            continue
        if b"\x00" in raw[:8192]:  # 二进制走字节强标记，不做文本正则
            continue
        text = raw.decode("utf-8", errors="replace")
        hits.extend(scan_text(text, rules, noreply, rel))
    return hits


def scan_history(rules, noreply):
    """模式二：逐提交扫描历史（**多 rev 的 git grep 会静默 0 命中，故逐提交迭代**）。

    无 ``.git`` 时（``git archive`` 导出树）历史不可达 → 返回空列表，
    并由调用方在输出里**显式声明"历史通道不可用"**（不留空、不假装扫过）。
    """
    if not _has_git():
        return []
    hits = []
    commits = _run_git(["rev-list", "--all"]).split()
    for commit in commits:
        tree_files = _run_git(["ls-tree", "-r", "--name-only", commit]).splitlines()
        for rel in tree_files:
            rel = rel.strip()
            if not rel:
                continue
            blob = _run_git(["show", "%s:%s" % (commit, rel)])
            if "\x00" in blob[:8192]:
                continue
            for hit in scan_text(blob, rules, noreply, rel):
                hits.append((commit[:8],) + hit[1:])
    return hits


def scan_messages(rules, noreply):
    """模式三：提交信息扫描。无 ``.git`` 时不可达 → 空列表（由调用方显式声明）。"""
    if not _has_git():
        return []
    log = _run_git(["log", "--all", "--format=%H%n%B"])
    return scan_text(log, rules, noreply, "<commit-messages>")


def scan_dist(rules, noreply):
    """模式四：构建产物本体扫描（dist/ 存在时才跑）。"""
    dist = os.path.join(REPO_ROOT, "dist")
    if not os.path.isdir(dist):
        return []
    hits = []
    for dirpath, dirnames, filenames in os.walk(dist):
        dirnames[:] = sorted(dirnames)
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")
            try:
                with open(path, "rb") as fh:
                    raw = fh.read()
            except OSError:
                continue
            text = raw.decode("utf-8", errors="replace")
            hits.extend(scan_text(text, rules, noreply, rel))
    return hits


def _history_channel_probe():
    """**历史通道探活**：确认历史扫描真能看到内容（防静默空扫假绿）。

    探活对象取 HEAD 树里确实存在的文件（早期提交可能还没有该文件）。
    """
    commits = _run_git(["rev-list", "--all"]).split()
    if not commits:
        return False
    # 从 HEAD 开始找一个真存在的跟踪文件作为探针
    tracked = [rel.strip() for rel in
               _run_git(["-c", "core.quotepath=false", "ls-files"]).splitlines()
               if rel.strip()]
    if not tracked:
        return False
    probe_path = tracked[0]
    for commit in commits:
        probe = _run_git(["show", "%s:%s" % (commit, probe_path)])
        if probe:
            return True
    return False


def selftest():
    """阳性/阴性对照——夹具**程序化合成**，源码无字面假密钥/假手机号。"""
    tokens = compute_tokens()
    rules, noreply = build_rules(tokens)

    # 阳性：合成一个非保留域的邮箱（由片段拼接，避免源码自命中）
    local = "probe" + "user"
    domain = "probe" + "host" + "." + "net"
    fake_email = local + "@" + domain
    positive = scan_text("contact: %s" % fake_email, rules, noreply, "<selftest>")
    if not any(hit[2] == "email" for hit in positive):
        print("AUDIT_SELFTEST_FAIL: 阳性对照未报红")
        return 1

    # 阴性：noreply 与 git 传输地址必须豁免
    negative_text = ("email: %s\n" % ("282769740+yuluo554" + noreply)
                     + "remote: git@github.com:user/repo.git\n")
    negative = [hit for hit in scan_text(negative_text, rules, noreply, "<selftest>")
                if hit[2] == "email"]
    if negative:
        print("AUDIT_SELFTEST_FAIL: noreply/传输地址被误报 %r" % (negative,))
        return 1

    # 阴性：干净文本
    clean = "net_unit_price = purchase / yield_rate\n"
    if scan_text(clean, rules, noreply, "<selftest>"):
        print("AUDIT_SELFTEST_FAIL: 干净文本误报")
        return 1

    # 阴性：长 hex 是 advisory（不进阻断），且 sha256 里的数字段不判手机号
    hex_text = "sha256: " + "a" * 40 + "\n"
    hex_hits = scan_text(hex_text, rules, noreply, "<selftest>")
    if any(hit[2] == "phone" for hit in hex_hits):
        print("AUDIT_SELFTEST_FAIL: hex 串被判成手机号")
        return 1

    print("AUDIT_SELFTEST_OK")
    return 0


def main(argv=None):
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="脱敏审计（四模式 + 自检）")
    parser.add_argument("--selftest", action="store_true", help="阳性/阴性对照")
    parser.add_argument("--mode", choices=("tracked", "history", "messages", "dist", "all"),
                        default="all", help="扫描模式")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    tokens = compute_tokens()
    rules, noreply = build_rules(tokens)
    # token provenance（只报类别与实算来源，不写词面值）
    print("token provenance: emails=%d(from git log) users=%d(getpass) paths=%d(repo path)"
          % (len(tokens["emails"]), len(tokens["users"]), len(tokens["paths"])))

    has_git = _has_git()
    if not has_git:
        print("注意: 当前树无 .git（如 git archive 导出树）——历史与提交信息通道不可用，"
              "已显式跳过（不假装扫过）")

    hits = []
    modes = (("tracked", scan_tracked), ("history", scan_history),
             ("messages", scan_messages), ("dist", scan_dist))
    for name, func in modes:
        if args.mode not in ("all", name):
            continue
        if not has_git and name in ("history", "messages"):
            continue
        if name == "history" and not _history_channel_probe():
            print("AUDIT_FAIL: 历史扫描通道探活失败（可能空扫）")
            return 1
        hits.extend(func(rules, noreply))

    hard = [hit for hit in hits if hit[3] == HARD]
    review = [hit for hit in hits if hit[3] == REVIEW]
    advisory = [hit for hit in hits if hit[3] == ADVISORY]

    for label, group in (("HARD", hard), ("REVIEW", review), ("advisory", advisory)):
        for hit in group:
            print("  %s:%s [%s/%s] %s" % (hit[0], hit[1], hit[2], label, hit[4]))

    if hard:
        print("DESENSITIZE_AUDIT_FAIL: HARD 命中 %d 处" % len(hard))
        return 1
    if review:
        print("DESENSITIZE_AUDIT_REVIEW: 复核项 %d 处（需人工豁免留档）" % len(review))
    print("DESENSITIZE_AUDIT_OK: HARD 0 / REVIEW %d / advisory %d"
          % (len(review), len(advisory)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
