"""报告导出：Markdown（人读）+ XLSX（机读）。

两条硬约束（plan/02 §6）：

- **逐字节可复现**：自写最小 OOXML writer，``ZIP_STORED`` + ``create_system=0``
  + 固定 ``date_time=(1980,1,1,0,0,0)``，零第三方依赖。第三方库的 ZIP 元数据
  （宿主系统标识、时间戳）会让字节漂移，破坏"同输入同字节"的承诺。
- **无外链**：单元格文本里不得有 URL——断网可开、可归档。

两格式都消费 ``sections.build_sections()`` 的同一份结构，所以"内容一致"是
结构性质而非人工抽查。
"""

import os
import re
import zipfile

from . import sections as sections_mod

FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)
_URL_RE = re.compile(r"https?://", re.IGNORECASE)


class ExternalLinkError(ValueError):
    """机读产物里出现外链——违反"断网可开"硬约束。"""


# ---------------------------------------------------------------- Markdown

def render_markdown(result):
    """渲染 Markdown 报告（人读）。"""
    lines = ["# 菜品成本核算报告", ""]
    for section in sections_mod.build_sections(result):
        lines.append("## %s" % section["title"])
        lines.append("")
        lines.extend(_render_md_section(section))
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _render_md_section(section):
    kind = section["kind"]
    if kind == "kv":
        return ["| %s | %s |" % (k, v) for k, v in section["rows"]]
    if kind == "table":
        return _md_table(section["headers"], section["rows"])
    if kind == "notice":
        return [section["text"]]
    if kind == "multi":
        out = []
        for block in section["blocks"]:
            out.append("### %s" % block["subtitle"])
            out.append("")
            out.extend(_md_table(block["headers"], block["rows"]))
            out.append("")
        return out
    raise ValueError("未登记的章节类型: %r" % kind)


def _md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in row) + " |")
    if not rows:
        out.append("| " + " | ".join(["—"] * len(headers)) + " |")
    return out


# ------------------------------------------------------------------- XLSX

def render_xlsx_rows(result):
    """把章节摊平成二维表（XLSX 单表形态）。"""
    rows = []
    for section in sections_mod.build_sections(result):
        rows.append([section["title"]])
        kind = section["kind"]
        if kind == "kv":
            for key, value in section["rows"]:
                rows.append([key, value])
        elif kind == "table":
            rows.append(list(section["headers"]))
            for row in section["rows"]:
                rows.append(["" if c is None else str(c) for c in row])
        elif kind == "notice":
            rows.append([section["text"]])
        elif kind == "multi":
            for block in section["blocks"]:
                rows.append([block["subtitle"]])
                rows.append(list(block["headers"]))
                for row in block["rows"]:
                    rows.append(["" if c is None else str(c) for c in row])
        rows.append([])
    return rows


def write_xlsx(path, rows):
    """写最小 OOXML xlsx（确定性）。"""
    for row in rows:
        for cell in row:
            if isinstance(cell, str) and _URL_RE.search(cell):
                raise ExternalLinkError("机读产物不得含外链: %r" % cell[:80])

    sheet_xml = _sheet_xml(rows)
    entries = {
        "[Content_Types].xml": _CONTENT_TYPES,
        "_rels/.rels": _RELS,
        "xl/workbook.xml": _WORKBOOK,
        "xl/_rels/workbook.xml.rels": _WORKBOOK_RELS,
        "xl/worksheets/sheet1.xml": sheet_xml,
    }
    # 条目按路径显式排序 + 固定时间戳 + STORED → 逐字节确定
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zf:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=FIXED_DATE_TIME)
            info.create_system = 0
            info.external_attr = 0o600 << 16
            zf.writestr(info, entries[name].encode("utf-8"))


def _col_name(index):
    """0 → A, 25 → Z, 26 → AA。"""
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _sheet_xml(rows):
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, value in enumerate(row):
            ref = "%s%d" % (_col_name(c), r)
            cells.append('<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s'
                         "</t></is></c>" % (ref, _escape(str(value))))
        parts.append('<row r="%d">%s</row>' % (r, "".join(cells)))
    parts.append("</sheetData></worksheet>")
    return "".join(parts)


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    "</Types>"
)

_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)

_WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="核算报告" sheetId="1" r:id="rId1"/></sheets></workbook>'
)

_WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    "</Relationships>"
)


def write_reports(result, prefix):
    """写 Markdown + XLSX 双轨报告，返回产出路径列表。

    统一换行：文本产物一律 ``newline="\\n"``（防 Windows 把 \\n 翻成 \\r\\n，
    触发 EOL 门 / 破坏跨平台可复现）。
    """
    md_path = prefix + ".md"
    xlsx_path = prefix + ".xlsx"
    directory = os.path.dirname(os.path.abspath(md_path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)

    with open(md_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_markdown(result))
    write_xlsx(xlsx_path, render_xlsx_rows(result))
    return [md_path, xlsx_path]
