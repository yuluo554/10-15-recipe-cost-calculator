"""报告章节结构 —— **单一渲染源**。

Markdown 渲染器与 XLSX 渲染器**都消费本模块产出的结构化章节**，于是
"两格式内容一致"不再是"导出后肉眼比对"，而是**结构上不可能不一致**。

**溯源硬约束**：章节必含"参数来源块"（每项参数：来源类型 + 文件/快照标识 +
抓取日期），并把逐项计算过程直接渲染引擎的 ``steps``——报告层**不重算**。
**"未启用"章节显式写出**，不留空：\"没查\"与\"查了没问题\"是两种结论。
"""

from decimal import Decimal

# 章节标题常量（两渲染器共用，避免各写一份）
SEC_OVERVIEW = "一、概览"
SEC_LIBRARY = "二、食材库"
SEC_COSTCARD = "三、成本卡"
SEC_PRICING = "四、毛利率定价"
SEC_ALERT = "五、价格波动预警"
SEC_SOURCES = "六、参数来源块"
SEC_SCOPES = "七、参数门控状态"
SEC_DISCLAIMER = "八、免责声明"

DISCLAIMER = (
    "本工具为辅助核算工具，非财务/经营决策工具。净料率、损耗率、目标毛利率、"
    "波动阈值等参数的内置默认值均为**经验值或示例值，非官方数据**，用户须自行核对。"
    "价格数据来自公开批发价快照，逐份记录抓取日期；本工具不联网拉价。"
)


def _fmt(value):
    """统一呈现：Decimal 去尾零显示，None → 空串。"""
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def build_sections(result):
    """把引擎结果组装成结构化章节（两渲染器的共同输入）。"""
    sections = []

    # 一、概览
    overview_rows = [
        ("进货单", result.get("purchases_summary", "")),
        ("食材库规模", "%d 项" % result.get("library_size", 0)),
        ("菜品数", "%d 道" % len(result.get("cards", []))),
        ("异常行数", "%d 条" % len(result.get("warnings", []))),
    ]
    sections.append({
        "key": "overview", "title": SEC_OVERVIEW, "kind": "kv",
        "rows": overview_rows,
    })

    # 二、食材库
    library_rows = []
    for card in result.get("cards", []):
        for line in card["lines"]:
            library_rows.append([
                line["food"], _fmt(line["purchase_unit_price"]),
                _fmt(line["yield_rate"]), _fmt(line["loss_rate"]),
                _fmt(line["net_unit_price"]),
                (line.get("price_source") or {}).get("kind", ""),
            ])
    sections.append({
        "key": "library", "title": SEC_LIBRARY, "kind": "table",
        "headers": ["食材", "毛料单价", "净料率", "损耗率", "净料单价", "价格来源"],
        "rows": library_rows,
    })

    # 三、成本卡（直接渲染引擎留痕，报告层不重算）
    costcard_rows = []
    for card in result.get("cards", []):
        for line in card["lines"]:
            costcard_rows.append([
                card["dish"], line["food"], _fmt(line["net_unit_price"]),
                _fmt(line["qty"]), _fmt(line["line_cost"]),
            ])
        costcard_rows.append([card["dish"], "— 单份成本 —", "", "",
                              _fmt(card["cost"])])
    sections.append({
        "key": "costcard", "title": SEC_COSTCARD, "kind": "table",
        "headers": ["菜品", "食材", "净料单价", "用量", "行成本"],
        "rows": costcard_rows,
    })

    # 四、毛利率定价
    pricing_rows = []
    for row in result.get("pricing", []):
        pricing_rows.append([
            row["dish"], _fmt(row["cost"]), _fmt(row["target_margin"]),
            _fmt(row["suggested_price"]), _fmt(row["actual_margin"]),
        ])
    sections.append({
        "key": "pricing", "title": SEC_PRICING, "kind": "table",
        "headers": ["菜品", "单份成本", "目标毛利率", "建议售价", "实际毛利率"],
        "rows": pricing_rows,
    })

    # 五、预警（未启用时显式写出，不留空）
    if result.get("alert_enabled"):
        alert = result["alert"]
        alert_rows = []
        for row in alert["changes"]:
            alert_rows.append([
                row["name"], _fmt(row["old_price"]), _fmt(row["new_price"]),
                _fmt(row["change_rate"]), row["status"],
            ])
        impacted_rows = []
        for row in alert["impacted"]:
            impacted_rows.append([
                row["dish"], _fmt(row["old_cost"]), _fmt(row["new_cost"]),
                _fmt(row["delta"]), _fmt(row["change_rate"]),
                "、".join(row["touched_foods"]),
            ])
        sections.append({
            "key": "alert", "title": SEC_ALERT, "kind": "multi",
            "blocks": [
                {"subtitle": "食材价格变动（按涨跌幅降序）", "kind": "table",
                 "headers": ["食材", "旧价", "新价", "涨跌幅", "状态"],
                 "rows": alert_rows},
                {"subtitle": "受影响菜品（超阈值 %s）" % _fmt(alert["threshold"]),
                 "kind": "table",
                 "headers": ["菜品", "旧成本", "新成本", "成本差", "涨跌幅", "涉及食材"],
                 "rows": impacted_rows},
            ],
        })
    else:
        sections.append({
            "key": "alert", "title": SEC_ALERT, "kind": "notice",
            "text": "本次导出未启用价格波动预警（用 --with-alert 并给出两期快照启用）。",
        })

    # 六、参数来源块（让读者不开仓库也能核证"这个数字哪来的"）
    source_rows = []
    for card in result.get("cards", []):
        for line in card["lines"]:
            src = line.get("price_source") or {}
            source_rows.append(["进货单价·" + line["food"], src.get("kind", ""),
                                src.get("ref", ""), _fmt(src.get("date"))])
            ysrc = line.get("yield_source") or {}
            source_rows.append(["净料率·" + line["food"], ysrc.get("kind", ""),
                                ysrc.get("ref", ""), _fmt(ysrc.get("date"))])
            qsrc = line.get("qty_source") or {}
            source_rows.append(["用量·" + line["food"], qsrc.get("kind", ""),
                                qsrc.get("ref", ""), _fmt(qsrc.get("date"))])
    for row in result.get("pricing", []):
        src = row.get("margin_source") or {}
        source_rows.append(["目标毛利率·" + row["dish"], src.get("kind", ""),
                            src.get("ref", ""), _fmt(src.get("date"))])
    if result.get("alert_enabled"):
        alert = result["alert"]
        for label, snap in (("预警阈值", alert.get("threshold_source") or {}),
                            ("旧快照", alert["old_snapshot"].get("source") or {}),
                            ("新快照", alert["new_snapshot"].get("source") or {})):
            source_rows.append([label, snap.get("kind", ""), snap.get("ref", ""),
                                _fmt(snap.get("date"))])
    sections.append({
        "key": "sources", "title": SEC_SOURCES, "kind": "table",
        "headers": ["参数项", "来源类型", "来源标识", "抓取/登记日期"],
        "rows": source_rows,
    })

    # 七、参数门控状态（三态显式可见）
    scope_rows = []
    for scope in result.get("param_scopes", []):
        scope_rows.append([
            scope["scope"], str(len(scope["verified"])),
            "、".join(scope["pending"]) or "—",
            "、".join(scope["input_required"]) or "—",
        ])
    sections.append({
        "key": "scopes", "title": SEC_SCOPES, "kind": "table",
        "headers": ["作用域", "已核对条目数", "待核对（阻断）", "需外部输入"],
        "rows": scope_rows,
    })

    # 八、免责声明
    sections.append({
        "key": "disclaimer", "title": SEC_DISCLAIMER, "kind": "notice",
        "text": DISCLAIMER,
    })
    return sections
