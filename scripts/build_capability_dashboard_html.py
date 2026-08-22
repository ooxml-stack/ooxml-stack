#!/usr/bin/env python3
"""Render the OOXML capability dashboard as a static HTML page."""

from __future__ import annotations

import argparse
import html
import json
import subprocess
from pathlib import Path

from build_capability_dashboard import build_dashboard
from build_ooxml_element_capability_ledger import DEFAULT_OUT as LEDGER_OUT
from build_ooxml_element_capability_ledger import build_ledger, write_json
from capability_dashboard_notes import display_text, note_for, value_note


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "artifacts/OOXML-ELEMENT-CAPABILITY-DASHBOARD.html"


def split_sections(markdown: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    title = "Summary"
    body: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            title = line[2:]
            continue
        if line.startswith("## "):
            if body:
                sections.append((title, body))
            title, body = line[3:], []
            continue
        body.append(line)
    sections.append((title, body))
    return sections


def render_section(title: str, lines: list[str]) -> str:
    content = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("| "):
            block, index = take_table(lines, index)
            content.append(render_table(block, title))
            continue
        if line.startswith("- "):
            block, index = take_list(lines, index)
            content.append(render_list(block, title))
            continue
        if line.strip():
            content.append(f"<p>{html.escape(line)}</p>")
        index += 1
    return f"<section><h2{tip_attrs(note_for(title))}>{html.escape(display_text(title))}</h2>{''.join(content)}</section>"


def take_table(lines: list[str], start: int) -> tuple[list[str], int]:
    end = start
    while end < len(lines) and lines[end].startswith("| "):
        end += 1
    return lines[start:end], end


def take_list(lines: list[str], start: int) -> tuple[list[str], int]:
    end = start
    while end < len(lines) and lines[end].startswith("- "):
        end += 1
    return lines[start:end], end


def render_table(lines: list[str], context: str) -> str:
    rows = [parse_row(line) for line in lines if not set(line.replace("|", "").strip()) <= {"-", " "}]
    if not rows:
        return ""
    headers = rows[0]
    head = "".join(render_header(cell) for cell in headers)
    body = []
    for row in rows[1:]:
        body.append("<tr>" + "".join(render_cell(row, headers, index, context) for index in range(len(row))) + "</tr>")
    return f"<div class=\"table-wrap\"><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def parse_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_header(label: str) -> str:
    return f"<th{tip_attrs(note_for(label))}>{note_label(display_text(label))}</th>"


def render_cell(row: list[str], headers: list[str], index: int, context: str) -> str:
    value = row[index]
    header = headers[index] if index < len(headers) else ""
    label = row[0] if row else value
    note = note_for(value, context) if index == 0 else value_note(label, header, value, context)
    visible = display_text(value) if index == 0 else value
    body = note_label(visible) if index == 0 else html.escape(visible)
    return f"<td{tip_attrs(note)}>{body}</td>"


def render_list(lines: list[str], context: str) -> str:
    items = []
    for line in lines:
        label = line[2:]
        items.append(f"<li{tip_attrs(note_for(label, context))}>{note_label(display_text(label))}</li>")
    return f"<ul>{''.join(items)}</ul>"


def tip_attrs(note: str) -> str:
    escaped = html.escape(note, quote=True)
    return f" class=\"has-note\" title=\"{escaped}\""


def note_label(text: str) -> str:
    return f"<span class=\"note-label\">{html.escape(text)}</span>"


def extract_tables(markdown: str) -> dict[str, list[list[str]]]:
    tables: dict[str, list[list[str]]] = {}
    for title, lines in split_sections(markdown):
        blocks = [take_table(lines, i)[0] for i, line in enumerate(lines) if line.startswith("| ")]
        if blocks:
            tables[title] = [row for row in map(parse_row, blocks[0][2:]) if row]
    return tables


def lookup(rows: list[list[str]], key: str, column: int) -> str:
    for row in rows:
        if row and row[0] == key and len(row) > column:
            return row[column]
    return "n/a"


def summary_cards(markdown: str) -> str:
    tables = extract_tables(markdown)
    levels = tables.get("Capability Levels", [])
    claim = tables.get("Claim Summary", [])
    semantic = lookup(levels, "semantic_editable", 1)
    surface = lookup(levels, "surface_editable", 1)
    rate = ratio_text(semantic, surface)
    cards = [
        ("XML element instances", lookup(levels, "xml_element_instances", 1), "Raw XML / 原始 XML", "unit: tag instances / 单位：标签实例"),
        ("Object candidates", lookup(levels, "object_candidates", 1), "Object inventory / 对象总账", "unit: object rows / 单位：对象行"),
        ("Readable / inspectable", lookup(levels, "readable_inspectable", 1), "Object subset / 对象子集", "denom: object candidates / 分母：对象候选"),
        ("Surface-editable", surface, "Campaign object rows / campaign 对象行", "safe bounded write / 安全边界写"),
        ("Semantic-editable", semantic, "Campaign object rows / campaign 对象行", "exact semantic oracle / 精确语义 oracle"),
        ("Unsupported / not proven", lookup(levels, "unsupported_or_not_proven", 1), "Campaign object rows / campaign 对象行", "remaining blockers / 剩余阻断"),
        ("Office output files", lookup(levels, "office_output_files", 1), "Output files / 输出文件", "not object count / 不是对象数"),
        ("Full claim", lookup(claim, "full_claim_proven", 1), "Boolean gate / 布尔门禁", "target: blockers = 0 / 目标：阻断为 0"),
    ]
    html_cards = "".join(render_kpi(*card) for card in cards)
    return f"{level_notice()}<div class=\"kpis\">{html_cards}</div>{progress_bar(rate)}"


def ratio_text(numerator: str, denominator: str) -> str:
    try:
        top = int(numerator.replace(",", ""))
        bottom = int(denominator.replace(",", ""))
    except ValueError:
        return "n/a"
    return f"{top / bottom * 100:.2f}%" if bottom else "n/a"


def level_notice() -> str:
    text = (
        "Every headline card carries its own unit and denominator; compare only cards "
        "with the same unit. / 每张顶部卡片都标出单位和分母；只有同单位数字才能相加或比较。"
    )
    return f"<p class=\"level-notice\">{html.escape(text)}</p>"


def render_kpi(label: str, value: str, level: str, scope: str) -> str:
    note = note_for(label) + "\n" + level + "\n" + scope
    return (
        f"<div class=\"kpi has-note\" title=\"{html.escape(note, quote=True)}\">"
        f"<span>{note_label(display_text(label))}</span><strong>{html.escape(value)}</strong>"
        f"<small>{html.escape(level)}</small><small>{html.escape(scope)}</small></div>"
    )


def progress_bar(rate: str) -> str:
    value = rate if rate.endswith("%") else "0%"
    label = f"Semantic promotion / 语义推进 {value}"
    note = "中文：这个进度条显示 former preserve-only 对象中已经语义可编辑的比例。\nEN: This progress bar shows the share of former preserve-only objects now proven semantic-editable."
    return f"<div class=\"progress has-note\" title=\"{html.escape(note, quote=True)}\"><div style=\"width:{html.escape(value)}\"></div><span>{html.escape(label)}</span></div>"


def styles() -> str:
    return """
body{margin:0;background:#f6f8fb;color:#172033;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:36px 24px 56px}
header{margin-bottom:24px}
h1{font-size:32px;line-height:1.15;margin:0 0 8px}
.meta{color:#5f6b7a;margin:0}
.level-notice{background:#fff7e6;border:1px solid #f2cf88;border-radius:8px;color:#5b4308;margin:16px 0 8px;padding:10px 12px}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:10px;margin:18px 0}
.kpi{background:#fff;border:1px solid #dce3ec;border-radius:8px;padding:13px 14px;box-shadow:0 1px 2px rgba(20,31,46,.04)}
.kpi span{display:block;color:#617085;font-size:12px}
.kpi strong{display:block;font-size:19px;margin-top:4px}
.kpi small{display:block;color:#6f7d8f;font-size:11px;line-height:1.25;margin-top:5px;white-space:normal}
.progress{position:relative;height:30px;background:#e6ebf2;border-radius:8px;overflow:hidden;margin:12px 0 18px}
.progress div{height:100%;background:#2663d9}
.progress span{position:absolute;inset:0;display:flex;align-items:center;padding-left:10px;color:#fff;font-weight:650;text-shadow:0 1px 1px rgba(0,0,0,.25)}
section{background:#fff;border:1px solid #dce3ec;border-radius:8px;margin:16px 0;padding:18px;box-shadow:0 1px 2px rgba(20,31,46,.04)}
h2{font-size:18px;margin:0 0 14px}
.has-note{cursor:help}
.note-label{border-bottom:1px dotted #9dadc2;text-underline-offset:3px}
.table-wrap{overflow:auto}
table{width:100%;border-collapse:collapse}
th,td{border-bottom:1px solid #e8edf3;padding:9px 10px;text-align:left;white-space:nowrap}
th{background:#f1f4f8;color:#344256;font-weight:650}
td:nth-child(n+2){font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:0}
ul{margin:0;padding-left:20px}
li{margin:6px 0}
@media(max-width:920px){.kpis{grid-template-columns:repeat(2,1fr)}}
@media(max-width:720px){main{padding:24px 14px}h1{font-size:25px}section{padding:14px}th,td{padding:8px}.kpis{grid-template-columns:1fr}}
"""


def render_html(markdown: str) -> str:
    sections = split_sections(markdown)
    title = sections[0][0]
    rendered = "".join(render_section(name, lines) for name, lines in sections[1:])
    cards = summary_cards(markdown)
    meta = "Live working-tree evidence dashboard. Not a release freeze. / 当前工作树 evidence 看板，不是 release freeze。"
    return f"<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html.escape(display_text(title))}</title><style>{styles()}</style></head><body><main><header><h1{tip_attrs(note_for(title))}>{html.escape(display_text(title))}</h1><p class=\"meta\">{html.escape(meta)}</p></header>{cards}{rendered}</main></body></html>\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", help="Machine ledger JSON path")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="HTML output path")
    parser.add_argument("--open", action="store_true", help="Open the generated HTML file")
    args = parser.parse_args()
    ledger = load_or_build_ledger(args.ledger)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(build_dashboard(ledger)), encoding="utf-8")
    print(out)
    if args.open:
        subprocess.run(["open", str(out)], check=False)


def load_or_build_ledger(path: str | None) -> dict:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    data = build_ledger()
    write_json(LEDGER_OUT, data)
    return data


if __name__ == "__main__":
    main()
