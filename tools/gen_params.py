"""参数包生成器（冻结产物）。

产出 ``src/rcc/data/rules/params.json``（包内随包数据）——**禁手改**；改需求走
"整目录重生成"，配 ``--check`` 位级一致守门。

确定性纪律：禁 stdlib ``random``、禁 ``set`` 迭代序、禁系统时钟；
JSON 固定 ``sort_keys=True`` + 固定缩进 + ``newline="\\n"``。

**来源标记红线**：净料率/阈值/毛利率的内置值均为**经验值或示例值，
非官方数据**——每条 ``source.kind`` 如实标注，`note` 写明非官方出处。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _guard import ensure_utf8_stdio  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据落点**只从 rcc.packaging 取**（M7：数据搬进包内 `src/rcc/data/`，
# 否则 `pip install` 出来的 wheel 里没有数据）。不在此复制一份 "src/rcc/data"。
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
from rcc.packaging import PACKAGE_DATA_REL  # noqa: E402

DATA_DIR = os.path.join(REPO_ROOT, PACKAGE_DATA_REL.replace("/", os.sep))
OUT_PATH = os.path.join(DATA_DIR, "rules", "params.json")

# 经验值默认净料率（非官方出处，用户可覆盖）。食材名取自公开批发价品类。
YIELD_RATES = [
    ("大白菜", "0.85", "叶菜类去外叶与根部后的出成率经验值"),
    ("娃娃菜", "0.88", "叶菜类去外叶后的出成率经验值"),
    ("小白菜", "0.80", "叶菜类去根去黄叶后的出成率经验值"),
    ("土豆", "0.90", "块茎类去皮后的出成率经验值"),
    ("胡萝卜", "0.85", "根茎类去皮去头尾后的出成率经验值"),
    ("洋葱", "0.88", "鳞茎类去外皮后的出成率经验值"),
    ("猪肉", "0.95", "去包装与筋膜后的出成率经验值"),
    ("牛肉", "0.92", "去筋膜与修整后的出成率经验值"),
    ("鸡蛋", "0.90", "带壳蛋去壳后的可食部分经验值"),
    ("草鱼", "0.55", "活鱼去鳞去内脏去头后的出成率经验值"),
]

EXPERIENCE_NOTE = "内置经验默认值，非官方数据；用户可覆盖"


def build_params():
    """构造参数包结构。"""
    yield_rates = {}
    for name, value, note in YIELD_RATES:
        yield_rates[name] = {
            "value": value,
            "status": "verified",
            "source": {
                "kind": "builtin_experience",
                "ref": "plan/02-算法与口径说明.md#参数体系",
                "date": None,
                "note": "%s（%s）" % (note, EXPERIENCE_NOTE),
            },
        }

    return {
        "schema_version": "1",
        "generated_by": "tools/gen_params.py",
        "note": "本文件为生成器冻结产物，禁止手改；改需求请重跑生成器。",
        "yield_rates": yield_rates,
        "pricing": {
            "target_margin": {
                "value": "0.60",
                "status": "verified",
                "source": {
                    "kind": "user",
                    "ref": "plan/02-算法与口径说明.md#参数体系",
                    "date": None,
                    "note": "示例值（非官方），用户须按自身经营情况配置",
                },
            },
        },
        "alert": {
            "threshold": {
                "value": "0.10",
                "status": "verified",
                "source": {
                    "kind": "user",
                    "ref": "plan/02-算法与口径说明.md#参数体系",
                    "date": None,
                    "note": "示例阈值（非官方），用户可配置",
                },
            },
        },
    }


def render(data):
    """渲染为确定性 JSON 文本（固定缩进、排序键、LF 行尾、末尾换行）。"""
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv=None):
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="参数包生成器（冻结产物）")
    parser.add_argument("--check", action="store_true",
                        help="重算并与入库件逐字节比对，不一致 exit 1")
    parser.add_argument("--out", default=OUT_PATH, help="输出路径")
    args = parser.parse_args(argv)

    text = render(build_params())
    payload = text.encode("utf-8")

    if args.check:
        if not os.path.isfile(args.out):
            print("FROZEN_PARAMS_MISSING: %s" % args.out, file=sys.stderr)
            return 1
        with open(args.out, "rb") as fh:
            existing = fh.read()
        if existing != payload:
            print("FROZEN_PARAMS_DRIFT: 入库件与重生成结果不一致", file=sys.stderr)
            return 1
        print("FROZEN_PARAMS_OK")
        return 0

    directory = os.path.dirname(args.out)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(args.out, "wb") as fh:
        fh.write(payload)
    print("已生成: %s" % os.path.relpath(args.out, REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
