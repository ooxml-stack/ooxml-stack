from __future__ import annotations

from typing import Any

CT = "http://schemas.openxmlformats.org/package/2006/content-types"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = OFFICE_REL
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
X = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def cases() -> list[dict[str, Any]]:
    docx = [
        docx_content_types_case(), docx_image_rel_case(), docx_color_case(),
        docx_drawing_table_case(), docx_wml_table_case(), docx_numbering_case(),
        docx_body_case(),
    ]
    pptx = [
        pptx_content_types_case(), pptx_slide_rel_case(), pptx_blip_case(), pptx_color_case(),
        pptx_table_case(), pptx_element_order_case(), pptx_animation_case(),
    ]
    xlsx = [
        xlsx_sheet_rid_case(), xlsx_rel_id_case(), xlsx_blip_case(), xlsx_color_case(),
        xlsx_table_case(), xlsx_shared_string_case(), xlsx_cell_ref_case(),
    ]
    return docx + pptx + xlsx


def rels_xml(*rels: str) -> str:
    return f'<Relationships xmlns="{PKG_REL}">' + "".join(rels) + "</Relationships>"


def ct_xml(*parts: str) -> str:
    overrides = "".join(f'<Override PartName="/{part}" ContentType="x"/>' for part in parts)
    return f'<Types xmlns="{CT}">{overrides}</Types>'


def docx_doc(body: str = "") -> str:
    return f'<w:document xmlns:w="{W}" xmlns:a="{A}" xmlns:r="{R}"><w:body>{body}</w:body></w:document>'


def base_case(case_id: str, fmt: str, rule: str, family: str,
              control: dict[str, str | bytes], mutant: dict[str, str | bytes]) -> dict[str, Any]:
    return {"id": case_id, "format": fmt, "rule_id": rule, "rule_family": family,
            "control": control, "mutant": mutant}


def docx_content_types_case() -> dict[str, Any]:
    doc = docx_doc()
    return base_case("docx-content-types", "docx", "content_types_integrity", "opc_content_types",
                     {"[Content_Types].xml": ct_xml("word/document.xml"), "word/document.xml": doc},
                     {"[Content_Types].xml": f'<Types xmlns="{CT}"/>', "word/document.xml": doc})


def docx_image_rel_case() -> dict[str, Any]:
    doc = docx_doc('<a:blip r:embed="rId1"/>')
    rel = f'<Relationship Id="rId1" Type="{OFFICE_REL}/image" Target="media/image1.png"/>'
    files = {"[Content_Types].xml": ct_xml("word/document.xml"), "word/document.xml": doc,
             "word/_rels/document.xml.rels": rels_xml(rel)}
    return base_case("docx-image-rel", "docx", "image_rel_integrity", "drawingml_blip_rel",
                     files | {"word/media/image1.png": b"png"}, files)


def docx_color_case() -> dict[str, Any]:
    good = docx_doc('<a:srgbClr val="FF0000"/>')
    bad = docx_doc('<a:srgbClr val="#FF0000"/>')
    return base_case("docx-color-no-hash", "docx", "color_no_hash", "drawingml_color",
                     {"word/document.xml": good}, {"word/document.xml": bad})


def docx_drawing_table_case() -> dict[str, Any]:
    good = docx_doc(drawing_table_xml(2, 2, "root"))
    bad = docx_doc(drawing_table_xml(2, 1, "root"))
    return base_case("docx-drawing-table-grid", "docx", "table_grid_consistency", "drawingml_table",
                     {"word/document.xml": good}, {"word/document.xml": bad})


def docx_wml_table_case() -> dict[str, Any]:
    good = '<w:tbl><w:tblGrid><w:gridCol/><w:gridCol/></w:tblGrid><w:tr><w:tc/><w:tc/></w:tr></w:tbl>'
    bad = '<w:tbl><w:tblGrid><w:gridCol/><w:gridCol/></w:tblGrid><w:tr><w:tc/></w:tr></w:tbl>'
    return base_case("docx-wml-table-grid", "docx", "wml_table_grid_consistency", "word_table",
                     {"word/document.xml": docx_doc(good)}, {"word/document.xml": docx_doc(bad)})


def docx_numbering_case() -> dict[str, Any]:
    ref = '<w:p><w:pPr><w:numPr><w:numId w:val="7"/></w:numPr></w:pPr></w:p>'
    numbering = f'<w:numbering xmlns:w="{W}"><w:num w:numId="7"/></w:numbering>'
    return base_case("docx-numbering-ref", "docx", "numbering_ref_valid", "word_numbering",
                     {"word/document.xml": docx_doc(ref), "word/numbering.xml": numbering},
                     {"word/document.xml": docx_doc(ref)})


def docx_body_case() -> dict[str, Any]:
    good = docx_doc()
    bad = f'<w:document xmlns:w="{W}"><w:p/></w:document>'
    return base_case("docx-body-required", "docx", "body_required", "word_structure",
                     {"word/document.xml": good}, {"word/document.xml": bad})


def pptx_content_types_case() -> dict[str, Any]:
    slide = f'<p:sld xmlns:p="{P}"/>'
    return base_case("pptx-content-types", "pptx", "content_types_integrity", "opc_content_types",
                     {"[Content_Types].xml": ct_xml("ppt/slides/slide1.xml"), "ppt/slides/slide1.xml": slide},
                     {"[Content_Types].xml": f'<Types xmlns="{CT}"/>', "ppt/slides/slide1.xml": slide})


def pptx_slide_rel_case() -> dict[str, Any]:
    good = f'<Relationship Id="rId1" Type="{OFFICE_REL}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
    bad = '<Relationship Id="rId1" Type="http://example.com/bogus" Target="bogus"/>'
    return base_case("pptx-slide-rel", "pptx", "slide_rel_completeness", "presentation_relationship",
                     {"ppt/slides/_rels/slide1.xml.rels": rels_xml(good)},
                     {"ppt/slides/_rels/slide1.xml.rels": rels_xml(bad)})


def pptx_blip_case() -> dict[str, Any]:
    slide = f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><a:blip r:embed="rId1"/></p:sld>'
    rel = f'<Relationship Id="rId1" Type="{OFFICE_REL}/image" Target="../media/image1.png"/>'
    files = {"ppt/slides/slide1.xml": slide, "ppt/slides/_rels/slide1.xml.rels": rels_xml(rel)}
    return base_case("pptx-blip-rel", "pptx", "blip_fill_integrity", "drawingml_blip_rel",
                     files | {"ppt/media/image1.png": b"png"}, files)


def pptx_color_case() -> dict[str, Any]:
    good = f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><a:srgbClr val="00FF00"/></p:sld>'
    bad = f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><a:srgbClr val="#00FF00"/></p:sld>'
    return base_case("pptx-color-no-hash", "pptx", "color_no_hash", "drawingml_color",
                     {"ppt/slides/slide1.xml": good}, {"ppt/slides/slide1.xml": bad})


def pptx_table_case() -> dict[str, Any]:
    good = drawing_table_xml(2, 2, "p:sld")
    bad = drawing_table_xml(2, 1, "p:sld")
    return base_case("pptx-table-grid", "pptx", "table_grid_consistency", "drawingml_table",
                     {"ppt/slides/slide1.xml": good}, {"ppt/slides/slide1.xml": bad})


def pptx_element_order_case() -> dict[str, Any]:
    good = f'<p:presentation xmlns:p="{P}"><p:sldSz cx="1" cy="1"/><p:defaultTextStyle/></p:presentation>'
    bad = f'<p:presentation xmlns:p="{P}"><p:defaultTextStyle/><p:sldSz cx="1" cy="1"/></p:presentation>'
    return base_case("pptx-element-order", "pptx", "element_order", "presentation_structure",
                     {"ppt/presentation.xml": good}, {"ppt/presentation.xml": bad})


def pptx_animation_case() -> dict[str, Any]:
    body = '<p:cNvPr id="1"/><p:spTgt spid="1"/>'
    good = f'<p:sld xmlns:p="{P}">{body}</p:sld>'
    bad = good.replace('spid="1"', 'spid="9"')
    return base_case("pptx-animation-target", "pptx", "animation_target_ref", "presentation_animation",
                     {"ppt/slides/slide1.xml": good}, {"ppt/slides/slide1.xml": bad})


def xlsx_sheet_rid_case() -> dict[str, Any]:
    rel = f'<Relationship Id="rId1" Type="{OFFICE_REL}/worksheet" Target="worksheets/sheet1.xml"/>'
    files = {"xl/_rels/workbook.xml.rels": rels_xml(rel)}
    return base_case("xlsx-sheet-rid", "xlsx", "sheet_rid_resolvable", "spreadsheet_relationship",
                     files | {"xl/workbook.xml": workbook_xml("rId1")},
                     files | {"xl/workbook.xml": workbook_xml("rId99")})


def xlsx_rel_id_case() -> dict[str, Any]:
    r1 = f'<Relationship Id="rId1" Type="{OFFICE_REL}/worksheet" Target="worksheets/sheet1.xml"/>'
    r2 = f'<Relationship Id="rId1" Type="{OFFICE_REL}/styles" Target="styles.xml"/>'
    return base_case("xlsx-rel-id-unique", "xlsx", "rel_id_unique", "opc_relationship",
                     {"xl/_rels/workbook.xml.rels": rels_xml(r1)},
                     {"xl/_rels/workbook.xml.rels": rels_xml(r1, r2)})


def xlsx_blip_case() -> dict[str, Any]:
    drawing = f'<xdr:wsDr xmlns:xdr="x" xmlns:a="{A}" xmlns:r="{R}"><a:blip r:embed="rId1"/></xdr:wsDr>'
    rel = f'<Relationship Id="rId1" Type="{OFFICE_REL}/image" Target="../media/image1.png"/>'
    files = {"xl/drawings/drawing1.xml": drawing, "xl/drawings/_rels/drawing1.xml.rels": rels_xml(rel)}
    return base_case("xlsx-blip-rel", "xlsx", "blip_fill_integrity", "drawingml_blip_rel",
                     files | {"xl/media/image1.png": b"png"}, files)


def xlsx_color_case() -> dict[str, Any]:
    good = f'<styleSheet xmlns="{X}"><fills><fill><fgColor rgb="FFFF0000"/></fill></fills></styleSheet>'
    bad = f'<styleSheet xmlns="{X}"><fills><fill><fgColor rgb="FF0000"/></fill></fills></styleSheet>'
    return base_case("xlsx-style-rgb-width", "xlsx", "styles_rgb_argb_width", "spreadsheet_color",
                     {"xl/styles.xml": good}, {"xl/styles.xml": bad})


def xlsx_table_case() -> dict[str, Any]:
    good = drawing_table_xml(2, 2, "xdr:wsDr")
    bad = drawing_table_xml(2, 1, "xdr:wsDr")
    return base_case("xlsx-drawing-table-grid", "xlsx", "table_grid_consistency", "drawingml_table",
                     {"xl/drawings/drawing1.xml": good}, {"xl/drawings/drawing1.xml": bad})


def xlsx_shared_string_case() -> dict[str, Any]:
    sheet = f'<worksheet xmlns="{X}"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>'
    good = f'<sst xmlns="{X}" uniqueCount="1"><si><t>A</t></si></sst>'
    bad = f'<sst xmlns="{X}" uniqueCount="0"><si><t>A</t></si></sst>'
    return base_case("xlsx-sst-count", "xlsx", "sst_count_consistent", "spreadsheet_shared_strings",
                     {"xl/worksheets/sheet1.xml": sheet, "xl/sharedStrings.xml": good},
                     {"xl/worksheets/sheet1.xml": sheet, "xl/sharedStrings.xml": bad})


def xlsx_cell_ref_case() -> dict[str, Any]:
    return base_case("xlsx-cell-ref-row", "xlsx", "cell_ref_matches_row", "spreadsheet_structure",
                     {"xl/worksheets/sheet1.xml": worksheet_xml("A1")},
                     {"xl/worksheets/sheet1.xml": worksheet_xml("A2")})


def workbook_xml(rid: str) -> str:
    return f'<workbook xmlns="{X}" xmlns:r="{R}"><sheets><sheet name="S" sheetId="1" r:id="{rid}"/></sheets></workbook>'


def worksheet_xml(cell_ref: str) -> str:
    return f'<worksheet xmlns="{X}"><sheetData><row r="1"><c r="{cell_ref}"/></row></sheetData></worksheet>'


def drawing_table_xml(grid_cols: int, row_cells: int, root_tag: str) -> str:
    cols = "".join('<a:gridCol/>' for _ in range(grid_cols))
    cells = "".join('<a:tc/>' for _ in range(row_cells))
    return f'<{root_tag} xmlns:p="{P}" xmlns:xdr="x" xmlns:a="{A}"><a:tbl><a:tblGrid>{cols}</a:tblGrid><a:tr>{cells}</a:tr></a:tbl></{root_tag}>'
