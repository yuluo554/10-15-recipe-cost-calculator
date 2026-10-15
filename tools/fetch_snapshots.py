"""新发地价格快照抓取器（M1 数据先行）。

产出 ``data/snapshots/`` 下的字节冻结留档：

===================  ==========================================================
``<name>.json``      原始响应件（**只增不改**；``.gitattributes`` 标 ``-text`` 防 EOL 改写字节）
``<name>.meta.json`` 来源元数据——引擎 ``io/snapshot.py::load_snapshot`` **缺它即抛错**
                     （"未挂来源不得进入计算路径"）
``ledger.json``      机读台账（数据日 / 抓取日期 / URL / 文件名 / sha256 / 记录数 / 品类覆盖）
``README.md``        人读台账（与 ``ledger.json`` **同源渲染**，禁手改——防台账与说明漂移）
===================  ==========================================================

**联网/离线分离**（plan/04：测试全离线、零 API 依赖）：

===============  ======  ======================================================
默认             联网    抓取并写盘；已有文件**默认拒绝覆盖**（需 ``--force``）
``--check``      离线    重算 sha256 与台账逐项核对 + 台账/README 位级一致
``--selftest``   离线    阳性/阴性对照——篡改临时副本必须被检出（防"恒绿假门"）
``--refetch-check`` 联网 重抓比对字节（人工跑，验证"跨抓取字节稳定"）
===============  ======  ======================================================

**接口纪律（M0 实测勘误，写进代码防复现）**：

- 历史日期参数是 ``pubDateStartTime``/``pubDateEndTime``；``startDate``/``endDate``
  会被**静默忽略**并返回最新一期——按错参数实现会让多期快照退化成同一期；
- ``limit`` 等请求参数会被**响应原样回显**，故参数集必须固定（否则 sha256 不可比）；
- ``limit`` 缺省时接口只回 20 条（静默截断），必须显式给足并断言
  ``len(list) == count``——否则快照会悄悄缺记录。

**为什么抓取器在 tools/ 而产品"不联网拉价"**：抓取是**开发期一次性动作**，
产出的快照随包冻结；运行期产品只读冻结快照（README"限制"节的口径不变）。
"""

import argparse
import datetime
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _guard import ensure_utf8_stdio  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.path.join(REPO_ROOT, "data", "snapshots")

API_URL = "http://www.xinfadi.com.cn/getPriceData.html"
USER_AGENT = "Mozilla/5.0 (compatible; recipe-cost-calculator/0.1 snapshot fetcher)"

# 请求参数集**固定**：响应会把它们原样回显，一变 sha256 就不可比
PAGE = "1"
LIMIT = "1000"

# 品类 id（M0 实测）。1188/1191/1192 实测返回 0 条，不采用。
CATEGORIES = (
    ("1186", "蔬菜"),
    ("1187", "水果"),
    ("1189", "肉禽蛋"),
    ("1190", "水产"),
)

# 与题面实测点对齐的三个可区分日期（2026-08-06/09-06/10-06）
DEFAULT_DATES = ("2026-08-06", "2026-09-06", "2026-10-06")

LEDGER_NAME = "ledger.json"
README_NAME = "README.md"
GENERATOR = "tools/fetch_snapshots.py"

REQUEST_GAP_SECONDS = 1.0
HTTP_TIMEOUT_SECONDS = 60
HTTP_RETRIES = 4
HTTP_BACKOFF_SECONDS = 3.0

META_SUFFIX = ".meta.json"


# ------------------------------------------------------------------ 抓取

def http_post(url, params, timeout=HTTP_TIMEOUT_SECONDS, retries=HTTP_RETRIES):
    """POST 表单并返回**原始响应字节**。

    返回字节而非解码文本：快照要求位级留档，解码再编码会引入不可控差异。
    接口偶发 503，故带退避重试。
    """
    body = urllib.parse.urlencode(list(params)).encode("ascii")
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, data=body, headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            })
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001 - 网络异常种类多，统一重试
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(HTTP_BACKOFF_SECONDS * (attempt + 1))
    raise RuntimeError("抓取失败（已重试 %d 次）: %s" % (retries, last_error))


def _day_params(data_date, category_id=None):
    """整日查询参数；给 ``category_id`` 时附品类过滤。"""
    params = [
        ("current", PAGE),
        ("limit", LIMIT),
        ("pubDateStartTime", data_date),
        ("pubDateEndTime", data_date),
    ]
    if category_id is not None:
        params.append(("prodPcatid", category_id))
    return tuple(params)


def _parse(raw, data_date):
    """解析响应并做**完整性断言**（防静默截断/串期）。"""
    payload = json.loads(raw.decode("utf-8"))
    records = payload.get("list") or []
    count = payload.get("count")
    if count != len(records):
        raise RuntimeError(
            "响应被截断：count=%s 但 list 只有 %d 条（limit=%s 不足？）"
            % (count, len(records), LIMIT))
    if not records:
        raise RuntimeError("数据日 %s 无记录（接口或日期有问题？）" % data_date)
    seen = sorted({str(r.get("pubDate", ""))[:10] for r in records})
    if seen != [data_date]:
        raise RuntimeError(
            "响应日期与请求不符（参数被忽略？）：请求 %s，实得 %s"
            % (data_date, seen))
    return records


def fetch_one(data_date, captured_date):
    """抓一份整日快照 + 品类覆盖核验，返回 ``(原始字节, meta 字典)``。"""
    raw = http_post(API_URL, _day_params(data_date))
    records = _parse(raw, data_date)

    # 品类覆盖核验：以 prodPcatid 逐品类实测，断言并集等于整日集合
    categories = []
    for category_id, category_name in CATEGORIES:
        time.sleep(REQUEST_GAP_SECONDS)
        sub_raw = http_post(API_URL, _day_params(data_date, category_id))
        sub_records = _parse(sub_raw, data_date) if json.loads(
            sub_raw.decode("utf-8")).get("list") else []
        names = sorted({r.get("prodCat") for r in sub_records})
        if sub_records and names != [category_name]:
            raise RuntimeError("品类 %s 返回了非预期 prodCat: %s"
                               % (category_id, names))
        categories.append({"id": category_id, "name": category_name,
                           "count": len(sub_records)})

    covered = sum(entry["count"] for entry in categories)
    if covered != len(records):
        raise RuntimeError(
            "品类并集 %d 条 ≠ 整日 %d 条（有品类未登记，快照不完整）"
            % (covered, len(records)))

    units = {}
    names = []
    for record in records:
        unit = str(record.get("unitInfo") or "")
        units[unit] = units.get(unit, 0) + 1
        names.append(record.get("prodName"))

    distinct = sorted(set(names))
    duplicates = len(names) - len(distinct)
    predominant = sorted(units.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

    meta = {
        "schema_version": "1",
        "generated_by": GENERATOR,
        "name": snapshot_name(data_date),
        "data_date": data_date,
        "captured_date": captured_date,
        "url": API_URL,
        "method": "POST",
        "request": dict(_day_params(data_date)),
        "response_file": snapshot_name(data_date) + ".json",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "record_count": len(records),
        "unit": predominant,
        "unit_counts": units,
        "categories": categories,
        "distinct_prodname_count": len(distinct),
        "duplicate_prodname_count": duplicates,
        "note": ("新发地公开批发价快照（数据日 %s），抓取于 %s；整日全品类，"
                 "sha256 见台账。逐条单位以原始件 unitInfo 为准（本字段为多数单位）。"
                 % (data_date, captured_date)),
    }
    return raw, meta


# ------------------------------------------------------------------ 命名与落盘

def snapshot_name(data_date):
    """快照基名（不含扩展名）。"""
    return "xinfadi-" + data_date


def _render_json(payload):
    """确定性 JSON 文本（排序键 + 固定缩进 + LF + 末尾换行）。"""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_bytes(path, payload):
    with open(path, "wb") as fh:
        fh.write(payload)


def _write_text(path, text):
    # 不用 Path.write_text(newline=)——该参数 3.10+ 才有，3.8 直接 TypeError
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# ------------------------------------------------------------------ 台账（同源渲染）

def build_ledger(root=SNAPSHOT_DIR):
    """从**磁盘实况**重建台账（纯函数于文件内容，可离线复算）。"""
    entries = []
    for filename in sorted(os.listdir(root)):
        if not filename.endswith(META_SUFFIX):
            continue
        with open(os.path.join(root, filename), "r", encoding="utf-8") as fh:
            meta = json.load(fh)
        entries.append({
            "name": meta.get("name"),
            "data_date": meta.get("data_date"),
            "captured_date": meta.get("captured_date"),
            "url": meta.get("url"),
            "response_file": meta.get("response_file"),
            "sha256": meta.get("sha256"),
            "record_count": meta.get("record_count"),
            "unit": meta.get("unit"),
            "categories": meta.get("categories") or [],
        })
    entries.sort(key=lambda entry: entry["data_date"] or "")
    return {
        "schema_version": "1",
        "generated_by": GENERATOR,
        "note": ("本文件为抓取器产物（禁手改）；快照原始响应件只增不改，"
                 "sha256 为位级留档判据。"),
        "source": "新发地批发价格接口（公开批发价）",
        "entry_count": len(entries),
        "entries": entries,
    }


def render_readme(ledger):
    """人读台账——**与 ledger.json 同源**，故不会与机读台账漂移。"""
    lines = [
        "# data/snapshots 快照台账",
        "",
        "> 本文件由 `%s` 生成，**禁手改**；改快照请重跑抓取器。" % GENERATOR,
        "",
        "## 一、来源",
        "",
        "新发地批发价格接口（公开批发价，POST，`http` 非 `https`）。历史日期查询参数为",
        "`pubDateStartTime` / `pubDateEndTime`（`startDate`/`endDate` 会被静默忽略并返回",
        "最新一期——这是本模块的头号陷阱）。",
        "",
        "快照为**整日全品类**留档：原始响应件字节冻结（`.gitattributes` 标 `-text`），",
        "**只增不改**；两期对比用不同文件。",
        "",
        "## 二、台账",
        "",
        "| 数据日 | 抓取日期 | 原始响应文件 | 记录数 | 单位 | sha256 |",
        "|---|---|---|---|---|---|",
    ]
    for entry in ledger["entries"]:
        lines.append("| %s | %s | `%s` | %s | %s | `%s` |" % (
            entry["data_date"], entry["captured_date"], entry["response_file"],
            entry["record_count"], entry["unit"], entry["sha256"]))

    lines.extend([
        "",
        "## 三、品类覆盖（抓取期以 `prodPcatid` 实测）",
        "",
        "| 数据日 | " + " | ".join(name for _id, name in CATEGORIES)
        + " | 合计 | 整日记录数 |",
        "|---|" + "---|" * (len(CATEGORIES) + 2),
    ])
    for entry in ledger["entries"]:
        counts = {item["id"]: item["count"] for item in entry["categories"]}
        cells = [str(counts.get(category_id, 0)) for category_id, _n in CATEGORIES]
        total = sum(counts.get(category_id, 0) for category_id, _n in CATEGORIES)
        lines.append("| %s | %s | %s | %s |" % (
            entry["data_date"], " | ".join(cells), total, entry["record_count"]))

    lines.extend([
        "",
        "品类并集必须等于整日记录数（抓取器已断言）——不等即有品类未登记，快照不完整。",
        "",
        "## 四、复核",
        "",
        "```bash",
        "py -3.12 -X utf8 tools/fetch_snapshots.py --check        # 离线位级一致",
        "py -3.12 -X utf8 tools/fetch_snapshots.py --selftest     # 离线阳性/阴性对照",
        "```",
        "",
        "**已知数据形态**（不隐藏）：同一 `prodName` 在同日可有多条（不同规格/产地），",
        "引擎按品名建索引时后出现者覆盖前者。逐日重复条数记在各自 `.meta.json` 的",
        "`duplicate_prodname_count`；原始件保留全部条目。",
        "",
    ])
    return "\n".join(lines)


# ------------------------------------------------------------------ 校验

def verify(root=SNAPSHOT_DIR):
    """离线位级核验，返回漂移清单（空列表 = 通过）。

    判据（每条都指向"台账说的"与"盘上真的"是否一致）：

    1. 每个 ``*.meta.json`` 有对应原始件，且**重算 sha256 等于 meta 登记值**；
    2. 原始件的记录数、数据日与 meta 一致（防串期/截断）；
    3. 品类覆盖合计等于记录数；
    4. ``ledger.json`` 与 ``README.md`` 等于由磁盘实况重渲染的结果（位级一致）。
    """
    drift = []
    if not os.path.isdir(root):
        return ["快照目录缺失: %s" % os.path.relpath(root, REPO_ROOT)]

    metas = [f for f in sorted(os.listdir(root)) if f.endswith(META_SUFFIX)]
    if not metas:
        return ["无任何 .meta.json（快照未抓取？）"]

    for meta_name in metas:
        meta_path = os.path.join(root, meta_name)
        with open(meta_path, "r", encoding="utf-8") as fh:
            meta = json.load(fh)

        if meta.get("generated_by") != GENERATOR:
            drift.append("%s 非本抓取器产物（generated_by=%r）"
                         % (meta_name, meta.get("generated_by")))

        raw_name = meta.get("response_file")
        raw_path = os.path.join(root, raw_name or "")
        if not raw_name or not os.path.isfile(raw_path):
            drift.append("%s 指向的原始件缺失: %s" % (meta_name, raw_name))
            continue

        with open(raw_path, "rb") as fh:
            raw = fh.read()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != meta.get("sha256"):
            drift.append("%s 位级不一致：实算 %s ≠ 台账 %s"
                         % (raw_name, digest[:12], str(meta.get("sha256"))[:12]))

        try:
            records = _parse(raw, meta.get("data_date"))
        except (ValueError, RuntimeError) as exc:
            drift.append("%s 解析失败: %s" % (raw_name, exc))
            continue

        if len(records) != meta.get("record_count"):
            drift.append("%s 记录数不一致：实 %d ≠ 台账 %s"
                         % (raw_name, len(records), meta.get("record_count")))

        covered = sum(item.get("count", 0) for item in meta.get("categories") or [])
        if covered != len(records):
            drift.append("%s 品类覆盖 %d ≠ 记录数 %d（有品类未登记）"
                         % (raw_name, covered, len(records)))

    # 台账与说明必须与磁盘实况位级一致（同源渲染 → 漂移即人改过）
    ledger = build_ledger(root)
    for filename, renderer in ((LEDGER_NAME, _render_json),
                               (README_NAME, render_readme)):
        path = os.path.join(root, filename)
        if not os.path.isfile(path):
            drift.append("%s 缺失" % filename)
            continue
        with open(path, "rb") as fh:
            actual = fh.read()
        expected = renderer(ledger).encode("utf-8")
        if actual != expected:
            drift.append("%s 与磁盘实况重渲染结果不一致（被手改过？）" % filename)

    return drift


# ------------------------------------------------------------------ 自检

def selftest():
    """阳性/阴性对照——**无自检的校验器可能一直是空扫**。

    在临时目录里造一份完整的合成快照（程序化合成，非真实抓取），
    先断言干净副本通过，再逐项篡改并断言**必须被检出**。
    """
    import shutil
    import tempfile

    root = tempfile.mkdtemp(prefix="snapshot-selftest-")
    try:
        data_date = DEFAULT_DATES[0]
        records = [
            {"id": 1, "prodName": "甲", "prodCat": "蔬菜", "prodPcatid": 1186,
             "avgPrice": "1.00", "unitInfo": "斤", "pubDate": data_date + " 00:00:00"},
            {"id": 2, "prodName": "乙", "prodCat": "水果", "prodPcatid": 1187,
             "avgPrice": "2.00", "unitInfo": "斤", "pubDate": data_date + " 00:00:00"},
        ]
        raw = json.dumps({"current": 1, "limit": 1000, "count": len(records),
                          "list": records}, ensure_ascii=False).encode("utf-8")
        name = snapshot_name(data_date)
        meta = {
            "schema_version": "1", "generated_by": GENERATOR, "name": name,
            "data_date": data_date, "captured_date": DEFAULT_DATES[0],
            "url": API_URL, "method": "POST", "request": dict(_day_params(data_date)),
            "response_file": name + ".json",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "record_count": len(records), "unit": "斤",
            "unit_counts": {"斤": len(records)},
            "categories": [{"id": "1186", "name": "蔬菜", "count": 1},
                           {"id": "1187", "name": "水果", "count": 1},
                           {"id": "1189", "name": "肉禽蛋", "count": 0},
                           {"id": "1190", "name": "水产", "count": 0}],
            "distinct_prodname_count": 2, "duplicate_prodname_count": 0,
            "note": "自检合成件",
        }
        _write_bytes(os.path.join(root, name + ".json"), raw)
        _write_text(os.path.join(root, name + META_SUFFIX), _render_json(meta))
        _write_text(os.path.join(root, LEDGER_NAME), _render_json(build_ledger(root)))
        _write_text(os.path.join(root, README_NAME), render_readme(build_ledger(root)))

        # 阴性：干净副本必须通过
        clean = verify(root)
        if clean:
            print("SNAPSHOT_SELFTEST_FAIL: 干净副本被误判: %s" % clean)
            return 1

        # 阳性一：篡改原始件一个字节 → 必须报位级不一致
        raw_path = os.path.join(root, name + ".json")
        original = open(raw_path, "rb").read()
        _write_bytes(raw_path, original.replace(b"1.00", b"1.01"))
        if not any("位级不一致" in item for item in verify(root)):
            print("SNAPSHOT_SELFTEST_FAIL: 篡改原始件未被检出（校验器空扫）")
            return 1
        _write_bytes(raw_path, original)

        # 阳性二：篡改台账 sha256 → 必须报位级不一致
        meta_path = os.path.join(root, name + META_SUFFIX)
        meta_text = open(meta_path, "r", encoding="utf-8").read()
        _write_text(meta_path, meta_text.replace(meta["sha256"], "0" * 64))
        if not any("位级不一致" in item for item in verify(root)):
            print("SNAPSHOT_SELFTEST_FAIL: 篡改台账 sha256 未被检出")
            return 1
        _write_text(meta_path, meta_text)

        # 阳性三：手改 README → 必须报与磁盘实况不一致
        readme_path = os.path.join(root, README_NAME)
        readme_text = open(readme_path, "r", encoding="utf-8").read()
        _write_text(readme_path, readme_text + "\n手改一行\n")
        if not any("README.md" in item for item in verify(root)):
            print("SNAPSHOT_SELFTEST_FAIL: 手改 README 未被检出")
            return 1
        _write_text(readme_path, readme_text)

        # 阴性复核：全部还原后必须重新通过
        if verify(root):
            print("SNAPSHOT_SELFTEST_FAIL: 还原后仍报漂移")
            return 1
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("SNAPSHOT_SELFTEST_OK")
    return 0


# ------------------------------------------------------------------ 入口

def cmd_fetch(dates, captured_date, force):
    if not os.path.isdir(SNAPSHOT_DIR):
        os.makedirs(SNAPSHOT_DIR)

    planned = [(date, os.path.join(SNAPSHOT_DIR, snapshot_name(date) + ".json"))
               for date in dates]
    if not force:
        existing = [path for _d, path in planned if os.path.exists(path)]
        if existing:
            print("拒绝覆盖已有快照（原始件只增不改；确需重抓用 --force）:",
                  file=sys.stderr)
            for path in existing:
                print("  %s" % os.path.relpath(path, REPO_ROOT), file=sys.stderr)
            return 1

    for date, raw_path in planned:
        print("抓取 %s ..." % date)
        raw, meta = fetch_one(date, captured_date)
        _write_bytes(raw_path, raw)
        _write_text(os.path.join(SNAPSHOT_DIR, snapshot_name(date) + META_SUFFIX),
                    _render_json(meta))
        print("  已写 %s（%d 条，sha256 %s）"
              % (os.path.relpath(raw_path, REPO_ROOT), meta["record_count"],
                 meta["sha256"][:12]))

    ledger = build_ledger()
    _write_text(os.path.join(SNAPSHOT_DIR, LEDGER_NAME), _render_json(ledger))
    _write_text(os.path.join(SNAPSHOT_DIR, README_NAME), render_readme(ledger))
    print("已写台账：%s / %s（%d 份快照）"
          % (LEDGER_NAME, README_NAME, ledger["entry_count"]))

    drift = verify()
    if drift:
        print("SNAPSHOT_FETCH_INCONSISTENT: %s" % "; ".join(drift), file=sys.stderr)
        return 1
    print("SNAPSHOT_FETCH_OK")
    return 0


def cmd_check():
    drift = verify()
    if drift:
        print("SNAPSHOT_CHECK_DRIFT: %s" % "; ".join(drift), file=sys.stderr)
        return 1
    ledger = build_ledger()
    print("SNAPSHOT_CHECK_OK: %d 份快照位级一致，台账与磁盘实况同源"
          % ledger["entry_count"])
    return 0


def cmd_refetch_check():
    """联网重抓比对字节（验证"跨抓取字节稳定"；不在测试面内）。"""
    if not os.path.isdir(SNAPSHOT_DIR):
        print("快照目录缺失", file=sys.stderr)
        return 1
    drift = []
    for filename in sorted(os.listdir(SNAPSHOT_DIR)):
        if not filename.endswith(META_SUFFIX):
            continue
        with open(os.path.join(SNAPSHOT_DIR, filename), "r", encoding="utf-8") as fh:
            meta = json.load(fh)
        raw_path = os.path.join(SNAPSHOT_DIR, meta["response_file"])
        if not os.path.isfile(raw_path):
            drift.append("%s 原始件缺失" % meta["response_file"])
            continue
        print("重抓 %s ..." % meta["data_date"])
        fresh = http_post(API_URL, _day_params(meta["data_date"]))
        with open(raw_path, "rb") as fh:
            on_disk = fh.read()
        if fresh != on_disk:
            drift.append("%s 重抓字节与留档不同" % meta["response_file"])
        time.sleep(REQUEST_GAP_SECONDS)

    if drift:
        print("SNAPSHOT_REFETCH_DRIFT: %s" % "; ".join(drift), file=sys.stderr)
        return 1
    print("SNAPSHOT_REFETCH_OK: 全部快照重抓字节一致")
    return 0


def main(argv=None):
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="新发地价格快照抓取器（M1 数据先行；快照只增不改）")
    parser.add_argument("--dates", nargs="*", default=list(DEFAULT_DATES),
                        help="数据日（YYYY-MM-DD，可多个；默认题面三个实测点）")
    parser.add_argument("--captured-date", default=None,
                        help="抓取日期（默认今天；显式给出可复现留档）")
    parser.add_argument("--force", action="store_true",
                        help="允许覆盖已有原始件（默认拒绝）")
    parser.add_argument("--check", action="store_true",
                        help="离线位级核验（重算 sha256 + 台账同源一致）")
    parser.add_argument("--selftest", action="store_true",
                        help="离线阳性/阴性对照")
    parser.add_argument("--refetch-check", action="store_true",
                        help="联网重抓比对字节（验证跨抓取字节稳定）")
    args = parser.parse_args(argv)

    if args.check:
        return cmd_check()
    if args.selftest:
        return selftest()
    if args.refetch_check:
        return cmd_refetch_check()

    captured = args.captured_date or datetime.date.today().isoformat()
    return cmd_fetch(list(args.dates), captured, args.force)


if __name__ == "__main__":
    sys.exit(main())
