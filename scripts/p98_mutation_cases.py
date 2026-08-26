from __future__ import annotations

from typing import Any

# P98-A high-risk uncovered-family mutation fixtures.
#
# These construct deliberately rule-violating OOXML packages for complex rule
# families that were left `uncovered_in_p97`:
#   - ChartEx (Office 2016+ extended charts): mc wrapper, style id, strDim order
#   - SmartArt / diagram relationship pairing
#   - Spreadsheet slicer cache / part contracts
#   - Embedded package / media relationship integrity (charts, headers, links)
#
# Each case pairs a *control* package (expected not to alarm the target rule)
# with a *mutant* package (expected to alarm it). The gate runner runs the
# format's combined rule registry against both and requires `mutant_hit and not
# control_hit` for the target rule id.

CT = "http://schemas.openxmlformats.org/package/2006/content-types"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = OFFICE_REL
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
X = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
CX = "http://schemas.microsoft.com/office/drawing/2014/chartex"
CS = "http://schemas.microsoft.com/office/drawing/2012/chartStyle"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
X14 = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
X15 = "http://schemas.microsoft.com/office/spreadsheetml/2010/11/main"

# Slicer GUI/type constants -------------------------------------------------
_WB_CACHE_URI = "{BBE1A952-AA13-448e-AADC-164F8A28A991}"
_PIVOT_DEF_URI = "{725AE2AE-9491-48be-B2B4-4EB974FC3084}"
_SLICER_CACHE_REL = "http://schemas.microsoft.com/office/2007/relationships/slicerCache"
_SLICER_REL = "http://schemas.microsoft.com/office/2007/relationships/slicer"
_PIVOT_REL = OFFICE_REL + "/pivotCacheDefinition"
_CACHE_TYPE = "application/vnd.ms-excel.slicerCache+xml"
_SLICER_TYPE = "application/vnd.ms-excel.slicer+xml"


def cases() -> list[dict[str, Any]]:
    pptx = [
        pptx_chartex_mc_wrapper_case(),
        pptx_chartex_style_id_case(),
        pptx_chartex_strdim_order_case(),
        pptx_smartart_drawing_part_case(),
        pptx_media_rel_integrity_case(),
        pptx_chart_embedded_xlsx_case(),
    ]
    docx = [
        docx_chartex_style_id_case(),
        docx_hyperlink_rel_valid_case(),
        docx_header_footer_rel_valid_case(),
        docx_document_rels_required_case(),
    ]
    xlsx = [
        xlsx_workbook_slicer_cache_case(),
        xlsx_slicer_part_contract_case(),
        xlsx_slicer_cache_consistency_case(),
    ]
    return pptx + docx + xlsx


def rels_xml(*rels: str) -> str:
    return f'<Relationships xmlns="{PKG_REL}">' + "".join(rels) + "</Relationships>"


def ct_xml(*parts: str) -> str:
    overrides = "".join(f'<Override PartName="/{part}" ContentType="x"/>' for part in parts)
    return f'<Types xmlns="{CT}">{overrides}</Types>'


def base_case(case_id: str, fmt: str, rule: str, family: str,
              control: dict[str, str | bytes], mutant: dict[str, str | bytes]) -> dict[str, Any]:
    return {"id": case_id, "format": fmt, "rule_id": rule, "rule_family": family,
            "control": control, "mutant": mutant}


def pptx_slide(body: str = "") -> str:
    return (
        f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}" '
        f'xmlns:c="{CX}" xmlns:mc="{MC}">{body}</p:sld>'
    )


# ---------------------------------------------------------------------------
# PPTX — ChartEx
# ---------------------------------------------------------------------------

def pptx_chartex_mc_wrapper_case() -> dict[str, Any]:
    # ChartEx needs mc:AlternateContent around the cx:chart reference.
    good = pptx_slide(
        f'<mc:AlternateContent><mc:Choice Requires="cx1">'
        f'<c:chart xmlns:c="{CX}" r:id="rId1"/>'
        f'</mc:Choice><mc:Fallback><a:p/></mc:Fallback></mc:AlternateContent>'
    )
    bad = pptx_slide(f'<c:chart xmlns:c="{CX}" r:id="rId1"/>')
    return base_case("pptx-chartex-mc-wrapper", "pptx", "chartex_mc_wrapper", "chartex",
                     {"ppt/slides/slide1.xml": good}, {"ppt/slides/slide1.xml": bad})


def pptx_chartex_style_id_case() -> dict[str, Any]:
    # Office expects style id='410'; id='201' may cause repair warnings.
    good = f'<cs:chartStyle xmlns:cs="{CS}" id="410"/>'
    bad = f'<cs:chartStyle xmlns:cs="{CS}" id="201"/>'
    return base_case("pptx-chartex-style-id", "pptx", "chartex_style_id", "chartex",
                     {"ppt/charts/style1.xml": good}, {"ppt/charts/style1.xml": bad})


def pptx_chartex_strdim_order_case() -> dict[str, Any]:
    # strDim levels must be leaf-first (innermost category first); the mutant
    # orders them root-first so lvl[0] is denser than lvl[-1].
    leaf = f'<c:lvl><c:pt idx="0" val="Leaf1"/><c:pt idx="1" val="Leaf2"/></c:lvl>'
    stem = f'<c:lvl><c:pt idx="0" val="Stem1"/><c:pt idx="1" val="Stem1"/></c:lvl>'
    good = pptx_slide(
        f'<c:chartEx xmlns:c="{CX}"><c:strDim type="cat">{leaf}{stem}</c:strDim></c:chartEx>'
    )
    bad = pptx_slide(
        f'<c:chartEx xmlns:c="{CX}"><c:strDim type="cat">{stem}{leaf}</c:strDim></c:chartEx>'
    )
    return base_case("pptx-chartex-strdim-order", "pptx", "chartex_strdim_order", "chartex",
                     {"ppt/slides/slide1.xml": good}, {"ppt/slides/slide1.xml": bad})


# ---------------------------------------------------------------------------
# PPTX — SmartArt / diagram relationship pairing
# ---------------------------------------------------------------------------

def pptx_smartart_drawing_part_case() -> dict[str, Any]:
    # Every diagramData relationship must be matched by a diagramDrawing relationship.
    data_rel = f'<Relationship Id="rId1" Type="{OFFICE_REL}/diagramData" Target="../diagrams/data1.xml"/>'
    drawing_rel = (
        f'<Relationship Id="rId2" Type="http://schemas.microsoft.com/office/2007/relationships/diagramDrawing" '
        f'Target="../diagrams/drawing1.xml"/>'
    )
    slide = pptx_slide('<a:graphicData/>')
    good = {"ppt/slides/slide1.xml": slide,
            "ppt/slides/_rels/slide1.xml.rels": rels_xml(data_rel, drawing_rel),
            "ppt/diagrams/data1.xml": "<dgm:dataModel xmlns:dgm='http://schemas.openxmlformats.org/drawingml/2006/diagram'/>",
            "ppt/diagrams/drawing1.xml": "<dgm:drawing xmlns:dgm='http://schemas.openxmlformats.org/drawingml/2006/diagram'/>"}
    bad = {"ppt/slides/slide1.xml": slide,
           "ppt/slides/_rels/slide1.xml.rels": rels_xml(data_rel),
           "ppt/diagrams/data1.xml": "<dgm:dataModel/>"}
    return base_case("pptx-smartart-drawing-part", "pptx", "smartart_drawing_part",
                     "smartart_diagram_rel", good, bad)


# ---------------------------------------------------------------------------
# PPTX — embedded / media relationships
# ---------------------------------------------------------------------------

def pptx_media_rel_integrity_case() -> dict[str, Any]:
    # a:videoFile/a:audioFile r:link must resolve to an existing media part.
    slide = pptx_slide(f'<a:videoFile r:link="rId10"/>')
    media_rel = f'<Relationship Id="rId10" Type="{OFFICE_REL}/video" Target="../media/movie.mp4"/>'
    good = {"ppt/slides/slide1.xml": slide,
            "ppt/slides/_rels/slide1.xml.rels": rels_xml(media_rel),
            "ppt/media/movie.mp4": b"\x00\x00\x00\x18ftypmp42"}
    bad = {"ppt/slides/slide1.xml": slide,
           "ppt/slides/_rels/slide1.xml.rels": rels_xml(media_rel)}
    return base_case("pptx-media-rel-integrity", "pptx", "media_rel_integrity",
                     "embedded_media_rel", good, bad)


def pptx_chart_embedded_xlsx_case() -> dict[str, Any]:
    # Charts that use embedded data must carry an embedded xlsx package relation.
    c_ns = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    chart = (
        f'<c:chartSpace xmlns:c="{c_ns}"><c:chart><c:plotArea><c:lineChart>'
        f'<c:ser><c:idx val="0"/><c:val><c:numRef><c:numCache/></c:numRef></c:val></c:ser>'
        f'</c:lineChart></c:plotArea></c:chart></c:chartSpace>'
    )
    xlsx_rel = (
        f'<Relationship Id="rId1" Type="{OFFICE_REL}/package" '
        f'Target="../embeddings/Microsoft_Excel_Worksheet.xlsx"/>'
    )
    good = {"ppt/charts/chart1.xml": chart,
            "ppt/charts/_rels/chart1.xml.rels": rels_xml(xlsx_rel),
            "ppt/embeddings/Microsoft_Excel_Worksheet.xlsx":
                bytes.fromhex("504b0304140000000800")}
    bad = {"ppt/charts/chart1.xml": chart,
           "ppt/charts/_rels/chart1.xml.rels": rels_xml(
               '<Relationship Id="rId9" Type="http://example.com/other" Target="x"/>')}
    return base_case("pptx-chart-embedded-xlsx", "pptx", "chart_embedded_xlsx",
                     "embedded_package_rel", good, bad)


# ---------------------------------------------------------------------------
# DOCX — ChartEx
# ---------------------------------------------------------------------------

def docx_chartex_style_id_case() -> dict[str, Any]:
    good = f'<cs:chartStyle xmlns:cs="{CS}" id="410"/>'
    bad = f'<cs:chartStyle xmlns:cs="{CS}" id="201"/>'
    return base_case("docx-chartex-style-id", "docx", "chartex_style_id", "chartex",
                     {"word/charts/style1.xml": good}, {"word/charts/style1.xml": bad})


# ---------------------------------------------------------------------------
# DOCX — embedded / media relationships
# ---------------------------------------------------------------------------

def docx_hyperlink_rel_valid_case() -> dict[str, Any]:
    doc = (f'<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body><w:p>'
           f'<w:hyperlink r:id="rId1"><w:r><w:t>link</w:t></w:r></w:hyperlink>'
           f'</w:p></w:body></w:document>')
    self_rel = (
        f'<Relationship Id="rId1" Type="{OFFICE_REL}/hyperlink" '
        f'Target="https://example.com" TargetMode="External"/>'
    )
    good = {"[Content_Types].xml": ct_xml("word/document.xml"),
            "word/document.xml": doc, "word/_rels/document.xml.rels": rels_xml(self_rel)}
    bad = {"[Content_Types].xml": ct_xml("word/document.xml"),
           "word/document.xml": doc, "word/_rels/document.xml.rels": rels_xml()}
    return base_case("docx-hyperlink-rel-valid", "docx", "hyperlink_rel_valid",
                     "embedded_media_rel", good, bad)


def docx_header_footer_rel_valid_case() -> dict[str, Any]:
    doc = (f'<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body><w:sectPr>'
           f'<w:headerReference w:type="default" r:id="rId1"/>'
           f'</w:sectPr></w:body></w:document>')
    header_rel = f'<Relationship Id="rId1" Type="{OFFICE_REL}/header" Target="header1.xml"/>'
    good = {"[Content_Types].xml": ct_xml("word/document.xml", "word/header1.xml"),
            "word/document.xml": doc, "word/_rels/document.xml.rels": rels_xml(header_rel),
            "word/header1.xml": f'<w:hdr xmlns:w="{W}"/>'}
    bad = {"[Content_Types].xml": ct_xml("word/document.xml"),
           "word/document.xml": doc, "word/_rels/document.xml.rels": rels_xml(header_rel)}
    return base_case("docx-header-footer-rel", "docx", "header_footer_rel_valid",
                     "embedded_media_rel", good, bad)


def docx_document_rels_required_case() -> dict[str, Any]:
    doc = f'<w:document xmlns:w="{W}"><w:body/></w:document>'
    styles_rel = f'<Relationship Id="rId1" Type="{OFFICE_REL}/styles" Target="styles.xml"/>'
    good = {"[Content_Types].xml": ct_xml("word/document.xml"),
            "word/document.xml": doc, "word/_rels/document.xml.rels": rels_xml(styles_rel)}
    bad = {"[Content_Types].xml": ct_xml("word/document.xml"),
           "word/document.xml": doc}
    return base_case("docx-document-rels-required", "docx", "document_rels_required",
                     "embedded_package_rel", good, bad)


# ---------------------------------------------------------------------------
# XLSX — slicer
# ---------------------------------------------------------------------------

def xlsx_workbook_slicer_cache_case() -> dict[str, Any]:
    cache_def = (f'<x14:slicerCacheDefinition xmlns:x14="{X14}" name="S3" sourceName="Field1">'
                 f'<x14:data><x14:tabular pivotCacheId="1"/>'
                 f'<x14:items count="1"><x14:i x="0" s="0"/></x14:items></x14:data>'
                 f'<x14:pivotTables><x14:pivotTable name="PT1"/></x14:pivotTables>'
                 f'</x14:slicerCacheDefinition>')
    workbook_rels = rels_xml(
        f'<Relationship Id="rId1" Type="{_SLICER_CACHE_REL}" Target="slicerCaches/slicerCache1.xml"/>')

    def wb(uri: str) -> str:
        return (f'<workbook xmlns="{X}" xmlns:r="{R}" xmlns:x14="{X14}"><sheets/>'
                f'<extLst><ext uri="{uri}">'
                f'<x14:slicerCaches><x14:slicerCache r:id="rId1"/></x14:slicerCaches>'
                f'</ext></extLst></workbook>')

    good = {"xl/workbook.xml": wb(_WB_CACHE_URI),
            "xl/_rels/workbook.xml.rels": workbook_rels,
            "xl/slicerCaches/slicerCache1.xml": cache_def}
    bad = {"xl/workbook.xml": wb("{BAD-URI-0000-0000-0000}"),
           "xl/_rels/workbook.xml.rels": workbook_rels,
           "xl/slicerCaches/slicerCache1.xml": cache_def}
    return base_case("xlsx-workbook-slicer-cache", "xlsx", "workbook_slicer_cache_structure",
                     "spreadsheet_slicer", good, bad)


def _slicer_ct_xml() -> str:
    return (f'<Types xmlns="{CT}">'
            f'<Override PartName="/xl/workbook.xml" ContentType="x"/>'
            f'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="x"/>'
            f'<Override PartName="/xl/slicerCaches/slicerCache1.xml" ContentType="{_CACHE_TYPE}"/>'
            f'<Override PartName="/xl/slicers/slicer1.xml" ContentType="{_SLICER_TYPE}"/>'
            f'</Types>')


def _slicer_wb(uri: str) -> str:
    return (f'<workbook xmlns="{X}" xmlns:r="{R}" xmlns:x14="{X14}"><sheets>'
            f'<sheet name="S1" sheetId="1" r:id="sheetRid"/></sheets>'
            f'<extLst><ext uri="{uri}">'
            f'<x14:slicerCaches><x14:slicerCache r:id="cacheRid"/></x14:slicerCaches>'
            f'</ext></extLst></workbook>')


def xlsx_slicer_part_contract_case() -> dict[str, Any]:
    # Pivot slicer cache, registered once from the workbook and referenced once
    # by a worksheet slicer list. Mutant drops the worksheet registration so the
    # slicer part is orphaned (no owner).
    pivot_cache_def = (
        f'<x14:slicerCacheDefinition xmlns:x14="{X14}" name="SlicerA" sourceName="Field1">'
        f'<x14:data><x14:tabular pivotCacheId="1">'
        f'<x14:items count="1"><x14:i x="0" s="0"/></x14:items>'
        f'</x14:tabular></x14:data>'
        f'<x14:pivotTables><x14:pivotTable name="PT1"/></x14:pivotTables>'
        f'</x14:slicerCacheDefinition>')
    wb_rels = rels_xml(
        f'<Relationship Id="cacheRid" Type="{_SLICER_CACHE_REL}" Target="slicerCaches/slicerCache1.xml"/>',
        f'<Relationship Id="sheetRid" Type="{OFFICE_REL}/worksheet" Target="worksheets/sheet1.xml"/>')

    def sheet(has_slicer: bool) -> str:
        lst = '<x14:slicerList><x14:slicer r:id="slicerRid"/></x14:slicerList>' if has_slicer else ''
        return f'<worksheet xmlns="{X}" xmlns:r="{R}" xmlns:x14="{X14}">{lst}</worksheet>'

    sheet_rels = rels_xml(
        f'<Relationship Id="slicerRid" Type="{_SLICER_REL}" Target="../slicers/slicer1.xml"/>')
    slicer_part = f'<x14:slicers xmlns:x14="{X14}"><x14:slicer cache="SlicerA"/></x14:slicers>'

    def files(has_slicer: bool) -> dict[str, str]:
        return {"[Content_Types].xml": _slicer_ct_xml(),
                "xl/workbook.xml": _slicer_wb(_WB_CACHE_URI),
                "xl/_rels/workbook.xml.rels": wb_rels,
                "xl/slicerCaches/slicerCache1.xml": pivot_cache_def,
                "xl/slicers/slicer1.xml": slicer_part,
                "xl/worksheets/sheet1.xml": sheet(has_slicer),
                "xl/worksheets/_rels/sheet1.xml.rels": sheet_rels if has_slicer else rels_xml()}

    return base_case("xlsx-slicer-part-contract", "xlsx", "slicer_part_contract",
                     "spreadsheet_slicer", files(True), files(False))


def xlsx_slicer_cache_consistency_case() -> dict[str, Any]:
    # Pivot slicer cache whose item index outruns the source sharedItems count.
    wb_rels = rels_xml(
        f'<Relationship Id="cacheRid" Type="{_SLICER_CACHE_REL}" Target="slicerCaches/slicerCache1.xml"/>',
        f'<Relationship Id="sheetRid" Type="{OFFICE_REL}/worksheet" Target="worksheets/sheet1.xml"/>')
    sheet = f'<worksheet xmlns="{X}" xmlns:r="{R}" xmlns:x14="{X14}"/>'

    def cache_def(source_count: int, item_indices: list[int]) -> str:
        items = "".join(f'<x14:i x="{i}" s="0"/>' for i in item_indices)
        return (f'<x14:slicerCacheDefinition xmlns:x14="{X14}" name="Slicer" sourceName="Field1">'
                f'<x14:data><x14:tabular pivotCacheId="1">'
                f'<x14:items count="{len(item_indices)}">{items}</x14:items>'
                f'</x14:tabular></x14:data>'
                f'<x14:pivotTables><x14:pivotTable name="PT1"/></x14:pivotTables>'
                f'</x14:slicerCacheDefinition>')

    def pivot_cache_def(source_count: int) -> str:
        shared_items = "".join('<i/>' for _ in range(source_count))
        return (
            f'<extCacheDefinition xmlns="{X}" xmlns:x14="{X14}" xmlns:r="{R}">'
            f'<cacheFields><cacheField name="Field1"><sharedItems>{shared_items}</sharedItems></cacheField></cacheFields>'
            f'<extLst><ext uri="{_PIVOT_DEF_URI}">'
            f'<x14:pivotCacheDefinition pivotCacheId="1"/></ext></extLst>'
            f'</extCacheDefinition>')
    pivot_table = f'<pivotCacheTable xmlns="{X}" name="PT1"/>'
    pivot_table_rels = rels_xml(
        f'<Relationship Id="rId1" Type="{_PIVOT_REL}" Target="../pivotCache/pivotCacheDefinition1.xml"/>')

    def files(item_indices: list[int]) -> dict[str, str]:
        return {"xl/workbook.xml": _slicer_wb(_WB_CACHE_URI),
                "xl/_rels/workbook.xml.rels": wb_rels,
                "xl/worksheets/sheet1.xml": sheet,
                "xl/slicerCaches/slicerCache1.xml": cache_def(1, item_indices),
                "xl/pivotCache/pivotCacheDefinition1.xml": pivot_cache_def(1),
                "xl/pivotTables/pivotTable1.xml": pivot_table,
                "xl/pivotTables/_rels/pivotTable1.xml.rels": pivot_table_rels}

    return base_case("xlsx-slicer-cache-consistency", "xlsx", "slicer_cache_definition_consistency",
                     "spreadsheet_slicer", files([0]), files([9]))