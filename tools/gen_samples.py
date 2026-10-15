"""样例数据生成器（确定性冻结产物）。

产出可**直接喂给 CLI** 的样例输入：进货单 CSV + 菜品 BOM JSON。
README 里引用的每个输入文件都必须由本生成器产出——**本地工作目录残留会掩盖
"引用了根本不存在的文件"**（这类缺口 CI 也暴露不了，CI 只跑 pytest 不读 README）。

确定性纪律：自研 splitmix64、固定 seed、无系统时钟、`newline="\\n"` 写盘。
演示数据一律**合成**：店名只用 data/README.md 登记的假店名白名单。
"""

import argparse
import csv
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _guard import ensure_utf8_stdio  # noqa: E402
from detrng import SplitMix64  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES_DIR = os.path.join(REPO_ROOT, "data", "samples")

SEED = 20261015

# 假店名白名单（data/README.md §三）——演示数据只准用这些
SHOP_NAMES = ("示例食堂甲", "示例小馆乙", "示例快餐丙")

# 食材（名称须与参数包 yield_rates 键一致，否则引擎会要求外部输入）
FOODS = [
    ("大白菜", "蔬菜", "斤"),
    ("娃娃菜", "蔬菜", "斤"),
    ("小白菜", "蔬菜", "斤"),
    ("土豆", "蔬菜", "斤"),
    ("胡萝卜", "蔬菜", "斤"),
    ("洋葱", "蔬菜", "斤"),
    ("猪肉", "肉禽蛋", "斤"),
    ("牛肉", "肉禽蛋", "斤"),
    ("鸡蛋", "肉禽蛋", "斤"),
    ("草鱼", "水产", "斤"),
]

DISHES = [
    ("醋溜白菜", [("大白菜", "1.2"), ("胡萝卜", "0.2")]),
    ("土豆烧牛肉", [("土豆", "0.8"), ("牛肉", "0.5"), ("洋葱", "0.3")]),
    ("番茄炒蛋", [("鸡蛋", "0.6"), ("洋葱", "0.1")]),
    ("清蒸草鱼", [("草鱼", "1.5"), ("小白菜", "0.4")]),
    ("娃娃菜粉丝煲", [("娃娃菜", "1.0"), ("猪肉", "0.2")]),
]

# 日期标签（示例值，非业务参数；仅作样例文件的日期列）
SAMPLE_DATES = ("2026-10-01", "2026-10-05", "2026-10-10")


def build_purchases():
    """生成进货单 CSV 文本（确定性）。

    样例刻意注入**每一类异常**，让"异常行一律列清单、不静默跳过"可被演示与测试：
    三态各自都要有代表，否则"三态语义"只是文档里的一句话。

    - ``invalid``：非数值 / 必填列为空 / 数值为负；
    - ``unknown``（表头级）：未登记列名（行仍可用）；
    - ``unknown``（行级）：字段数多于表头 → 整行结构不可解析（**行不入库**）；
    - 重复品名：非异常，但让"同品名取最后一条价"的取舍**可观测**。
    """
    rng = SplitMix64(SEED)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["日期", "品名", "类别", "数量", "单位", "单价", "金额"])

    for index, (name, category, unit) in enumerate(FOODS):
        qty = rng.randint(5, 40)
        # 单价区间按品类分档（分档值来自 RNG，不是业务参数）
        price_cents = rng.randint(200, 4000)
        price = "%d.%02d" % (price_cents // 100, price_cents % 100)
        amount = "%.2f" % (qty * price_cents / 100.0)
        writer.writerow([SAMPLE_DATES[index % len(SAMPLE_DATES)], name, category,
                         qty, unit, price, amount])

    # 同品名二次进货（**非异常**）：演示"同品名取最后一条价"的取舍口径。
    # 该品名在 BOM 中被引用，故这份后到的价即该食材的参考价。
    writer.writerow(["2026-10-12", "土豆", "蔬菜", "12", "斤", "1.65", "19.80"])

    # ---- 刻意注入的异常行（三态覆盖 + 结构错）----
    # invalid：非数值
    writer.writerow(["2026-10-10", "土豆", "蔬菜", "abc", "斤", "1.50", "0"])
    # invalid：必填列（品名）为空
    writer.writerow(["2026-10-10", "", "蔬菜", "3", "斤", "2.00", "6.00"])
    # invalid：数值为负
    writer.writerow(["2026-10-10", "南瓜", "蔬菜", "-2", "斤", "1.80", "-3.60"])
    # unknown（行级，行不入库）：字段数多于表头 → 列对齐不可信。
    # 注意表头下方会被追加一列，故这里给 9 个字段（表头 8 列）。
    writer.writerow(["2026-10-10", "莲藕", "蔬菜", "4", "斤", "3.50", "14.00",
                     "备注甲", "多余字段"])
    # unknown（单位未登记，**行仍可用**）：非 BOM 食材，不影响核算结果
    writer.writerow(["2026-10-10", "冬瓜", "蔬菜", "5", "克拉", "1.20", "6.00"])

    # 刻意注入 1 个未登记列名，验证 mapping_uncertain 第三态（表头级）
    buffer.seek(0)
    text = buffer.getvalue()
    return text.replace("日期,品名,类别,数量,单位,单价,金额",
                        "日期,品名,类别,数量,单位,单价,金额,备注")


def build_bom():
    """生成菜品 BOM JSON 文本（确定性）。"""
    payload = {
        "schema_version": "1",
        "shop": SHOP_NAMES[0],
        "note": "合成演示数据（假店名白名单内），非真实经营信息",
        "dishes": [],
    }
    for name, items in DISHES:
        payload["dishes"].append({
            "name": name,
            "items": [{"food": food, "qty": qty} for food, qty in items],
        })
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def outputs():
    """``{相对路径: 文本内容}``。"""
    return {
        "data/samples/purchases-demo.csv": build_purchases(),
        "data/samples/bom-demo.json": build_bom(),
    }


def _write_text(path, text):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main(argv=None):
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="样例数据生成器（冻结产物）")
    parser.add_argument("--check", action="store_true",
                        help="重算并与入库件逐字节比对，不一致 exit 1")
    args = parser.parse_args(argv)

    drift = []
    for rel, text in sorted(outputs().items()):
        path = os.path.join(REPO_ROOT, rel.replace("/", os.sep))
        payload = text.encode("utf-8")
        if args.check:
            if not os.path.isfile(path):
                drift.append("%s 缺失" % rel)
                continue
            with open(path, "rb") as fh:
                if fh.read() != payload:
                    drift.append("%s 内容漂移" % rel)
        else:
            _write_text(path, text)
            print("已生成: %s" % rel)

    if args.check:
        if drift:
            print("FROZEN_SAMPLES_DRIFT: %s" % "; ".join(drift), file=sys.stderr)
            return 1
        print("FROZEN_SAMPLES_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
