"""快照解析（新发地批发价原始 JSON 响应）。

快照文件是**字节冻结**的原始响应留档（``.gitattributes`` 标 ``-text``），
每条记录含 ``prodName`` / ``avgPrice`` / ``unitInfo`` / ``pubDate``。

快照必须能追溯到抓取日期——``snapshot_meta`` 由抓取脚本写入同一目录的
``*.meta.json``（抓取日期 / URL / sha256）。
"""

import hashlib
import json
import os

from ..model import make_source, to_decimal


def file_sha256(path):
    """文件 sha256（用于快照台账核对）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_snapshot(path):
    """读快照原始 JSON，返回 ``{"date":..., "captured_date":..., "prices": {...}, "source": {...}}``。

    来源元数据从同目录 ``<name>.meta.json`` 读；缺失即抛错——**未挂来源的快照
    不得进入计算路径**。

    **两个日期不是一回事**（M1 实测暴露，防"两期退化成同一期"）：

    - ``date`` = **数据日**（``meta.data_date``，行情所属交易日）——它是"两期快照"
      的**期间标识**，预警新旧两期据此区分；
    - ``captured_date`` = **抓取日**（``meta.captured_date``）——留档可复现性用，
      同一抓取日可以抓多个数据日。

    旧形态元数据只有 ``captured_date``（M0 期无真实多期快照）时，``date`` 回落
    抓取日以保持兼容。
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    meta_path = os.path.splitext(path)[0] + ".meta.json"
    if not os.path.isfile(meta_path):
        raise ValueError("快照缺少来源元数据（%s），未挂来源不得进入计算路径"
                         % os.path.basename(meta_path))

    with open(meta_path, "r", encoding="utf-8") as fh:
        meta = json.load(fh)

    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    records = payload.get("list") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("快照结构不可识别（缺 list 数组）")

    prices = {}
    for record in records:
        name = record.get("prodName")
        avg = record.get("avgPrice")
        if not name or avg in (None, ""):
            continue
        prices[name] = to_decimal(avg)

    # 数据日优先；旧形态（无 data_date）回落抓取日
    data_date = meta.get("data_date") or meta.get("captured_date")
    captured_date = meta.get("captured_date") or data_date

    return {
        "date": data_date,
        "captured_date": captured_date,
        "prices": prices,
        "unit": meta.get("unit"),
        "source": make_source("snapshot", os.path.basename(path),
                              date=data_date,
                              note=meta.get("note")),
        "sha256": file_sha256(path),
    }
