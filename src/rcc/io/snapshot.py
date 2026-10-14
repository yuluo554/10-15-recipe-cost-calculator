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
    """读快照原始 JSON，返回 ``{"date":..., "prices": {品名: Decimal}, "source": {...}}``。

    抓取日期从同目录 ``<name>.meta.json`` 读；缺失即抛错——**未挂来源的快照
    不得进入计算路径**。
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

    return {
        "date": meta.get("captured_date"),
        "prices": prices,
        "unit": meta.get("unit"),
        "source": make_source("snapshot", os.path.basename(path),
                              date=meta.get("captured_date"),
                              note=meta.get("note")),
        "sha256": file_sha256(path),
    }
