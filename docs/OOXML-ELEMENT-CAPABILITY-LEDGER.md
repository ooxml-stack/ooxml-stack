# OOXML Element Capability Ledger

Source: current working-tree ledger. This is a live dashboard, not a release freeze.
Generated: 2026-08-04T05:12:25.306267+00:00

## Purpose

This is the long-lived human and agent entry point for OOXML capability claims.

It answers one question:

> For the measured corpus, how many OOXML things are counted, readable,
> safely writable, semantically writable, fully writable, or not proven?

Use capability names and measured denominators here. Historical run
directories such as `release-evidence/p*/` are audit inputs, not the public
claim surface.

## Commands

- `make ledger` writes `artifacts/ooxml-element-capability-ledger.json`.
- `make dashboard` writes and opens `artifacts/OOXML-ELEMENT-CAPABILITY-DASHBOARD.html`.
- `make dashboard OPEN=0` writes the same HTML without opening it.
- `make dashboard-md OUT=artifacts/ooxml-ledger-dashboard.md` writes a Markdown snapshot.
- `make campaign-ledgers` regenerates local ignored burn-down cache JSONL files.

`artifacts/` is ignored by git. Commit generated evidence only when a
capability-based release bundle is intentionally frozen. Large campaign
cache JSONL files are ignored and should be regenerated locally.

## How To Read The Numbers

| Metric | Unit | Meaning | What it does not prove |
| --- | --- | --- | --- |
| XML element instances | raw XML elements | total XML scale | object support or editability |
| object candidates | object rows | normalized possible objects | readable or writable support |
| readable / inspectable | object rows | can be classified and inspected | safe write |
| surface-editable | object rows | safe bounded object-level mutation | semantic understanding |
| semantic-editable | object rows | modeled semantic edit with exact oracle | full object creation |
| Office output files | files | edited files opened by native Office | per-object semantic pass |

## Claim Summary

| Field | Value |
| --- | --- |
| allowed | Measured surface-editable rows: 296144; measured row-level semantic-editable rows: 275210. |
| forbidden | No full OOXML compatibility, full Office compatibility, all-elements fully editable, or global full-write claim. |
| current | Full semantic editability is not proven while blockers or anti-false-pass gates remain. |
| surface_editable_count | 296,144 |
| semantic_editable_count | 275,210 |
| full_claim_proven | false |
| semantic_blocker_count | 20,934 |
| anti_false_pass_gate | false |

## Unit Definitions

| Level | Unit | Meaning | 中文 |
| --- | --- | --- | --- |
| object_rows | object rows | Normalized object-candidate rows; not raw XML tags. | 归一化对象行，不是原始 XML 标签。 |
| office_output_files | files | Edited packages opened by native Office. | 真实 Office 打开的输出文件数。 |
| package_dependency_rows | dependency rows | Non-XML OPC dependencies tracked outside XML element counts. | XML 元素之外的 OPC 依赖行。 |
| xml_element_instances | raw XML elements | Every XML tag occurrence in measured packages. | 样本包里的每一个 XML 标签出现次数。 |

## Capability Levels

| Level | Count | Unit | Denominator | Strict claim | Evidence |
| --- | --- | --- | --- | --- | --- |
| xml_element_instances | 43,163,913 | xml element instances | raw_xml | Counted inventory only. | release-evidence/p43/ooxml-semantic-status-summary.json |
| object_candidates | 1,488,628 | object rows | semantic_inventory | Classified inventory only. | release-evidence/p43/ooxml-semantic-status-summary.json |
| readable_inspectable | 1,192,484 | object rows | semantic_inventory | Inspectable object inventory. | release-evidence/p43/ooxml-semantic-status-summary.json |
| semantic_handle_object_denominator | 698,760 | object rows | semantic_handle_inventory | Semantic handle denominator only. | release-evidence/p90/sh-semantic-editability-summary.json |
| opaque_binary_package_dependencies | 0 | package dependency rows | opc_dependency_inventory | Tracked separately when generated. | release-evidence/p43/ooxml-semantic-status-summary.json |
| surface_editable | 296,144 | object rows | former_preserve_only_campaign | Safe object-bound write under measured denominator. | release-evidence/p80 |
| semantic_editable | 275,210 | object rows | former_preserve_only_campaign | Rows with exact semantic proof. | release-evidence/p90/sh-semantic-editability-summary.json, release-evidence/p90/anti-false-pass-audit.json, release-evidence/former-preserve-only-semantic-editability/promotion-rows.jsonl, release-evidence/former-preserve-only-semantic-editability/promotion-summary.json, release-evidence/former-preserve-only-semantic-editability/office-results, release-evidence/former-preserve-only-semantic-editability/public-paths |
| full_write | 0 | object rows | family_operation_claim | No global full-write claim. | none |
| unsupported_or_not_proven | 20,934 | object rows | former_preserve_only_campaign | Not proven at semantic tier. | release-evidence/p77/public-api-object-edit-summary.json, release-evidence/p77/public-api-object-edit-rows-shards, release-evidence/p90/anti-false-pass-audit.json, release-evidence/p90/p80-semantic-promotion-feasibility.json, release-evidence/former-preserve-only-semantic-editability/promotion-rows.jsonl |
| office_output_files | 1,198 | Office output files | native_office_file_gate | Office file gate only. | release-evidence/p90/anti-false-pass-audit.json |

## Semantic Blockers

| Reason | Count |
| --- | --- |
| semantic_value_available_pending_proof | 12,097 |
| relationship_identity_like | 2,989 |
| binary_payload_reference | 2,975 |
| needs_family_model | 2,433 |
| needs_vendor_family_model | 440 |

## Families

| Family | Total | Semantic value available | Hydrated | Remaining | Pending proof | Explicit unsupported | No semantic value | Resolve failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| office_extension | 272,319 | 263,810 | 6,698 | 16,599 | 8,312 | 8,287 | 0 | 0 |
| vml_drawing | 3,314 | 3,252 | 155 | 1,047 | 1,014 | 33 | 0 | 0 |
| office_chart_extension | 1,305 | 1,300 | 828 | 833 | 828 | 5 | 0 | 0 |
| math_object | 2,405 | 2,394 | 612 | 621 | 612 | 9 | 0 | 0 |
| wps_extension | 656 | 216 | 72 | 512 | 72 | 440 | 0 | 0 |
| custom_xml_schema | 3,883 | 3,541 | 0 | 342 | 338 | 4 | 0 | 0 |
| chart_drawing | 530 | 530 | 150 | 322 | 322 | 0 | 0 | 0 |
| legacy_office_drawing | 1,089 | 976 | 249 | 249 | 249 | 0 | 0 | 0 |
| alternate_content | 10,147 | 10,147 | 151 | 151 | 151 | 0 | 0 | 0 |
| custom_xml_payload | 274 | 253 | 0 | 129 | 108 | 21 | 0 | 0 |
| vendor_private_extension | 47 | 47 | 47 | 47 | 47 | 0 | 0 | 0 |
| sharepoint_property | 135 | 135 | 38 | 42 | 42 | 0 | 0 | 0 |
| drawing_extension | 36 | 0 | 0 | 36 | 0 | 36 | 0 | 0 |
| office_drawing_sketch_extension | 4 | 2 | 0 | 4 | 2 | 2 | 0 | 0 |

## Remaining Bucket Acceleration

| Field | Value |
| --- | --- |
| remaining_bucket_schema | semantic-editability-remaining-buckets-v1 |
| candidate_package_count | 100 |
| known_boundary_package_count | 121 |
| known_replay_timeout_package_count | 4 |
| known_replay_timeout_entry_count | 5 |
| known_replay_timeout_package_scope_count | 4 |
| known_replay_timeout_operation_scope_count | 1 |
| policy_expansion_opportunity_count | 20 |
| family_model_opportunity_count | 0 |
| top_candidate_package | pptx_chart_dense_203slides |
| top_candidate_family | office_chart_extension |
| top_candidate_planned_rows | 316 |
| top_candidate_action | skip_boundary |

## Chunk Replay Campaign

| Field | Value |
| --- | --- |
| scope | cumulative chunk campaign; not a single-commit delta |
| promoted_row_count | 13,060 |
| promoted_chunk_count | 1,403 |
| slow_replay_promoted_row_count | 853 |
| slow_replay_promoted_chunk_count | 173 |
| chunk_record_count | 1,592 |
| raw_status_counts | office_boundary: 164, planned_row_mismatch: 5, promoted: 1403, public_api_failed: 5, timeout: 15 |
| current_plan_status_counts | none |
| current_plan_failure_count | 0 |
| current_plan_pending_chunk_count | 0 |
| legacy_or_superseded_failure_counts | office_boundary: 164, planned_row_mismatch: 5, public_api_failed: 5, timeout: 15 |
| promotion_row_count_total | 22,467 |
| run_elapsed_seconds | 699.06 |
| cumulative_chunk_elapsed_seconds | 286,621.66 |
| next_plan_scope | global_next_plan |
| next_plan_filters | {"family": "", "format": "", "include_replay_timeout_canary": false, "operation_id": "", "package_id": "", "qname": ""} |
| next_plan_chunk_count | 0 |
| next_plan_row_count | 0 |
| next_package_id |  |
| recommended_next_action | continue_same_package_or_next_safe_chunk |
| slowest_chunks | chunk-pptx-report-344slides-multimedia-office-extension-0003-f4e2ac6517 (promoted, 642.513s); chunk-pptx-report-344slides-multimedia-office-extension-0002-e75ae621df (promoted, 641.779s); chunk-pptx-report-344slides-multimedia-office-extension-0001-d5445c06ee (promoted, 634.495s) |

## Close Error Diagnostics

| Field | Value |
| --- | --- |
| close_error_office_result_count | 149 |
| close_error_package_count | 103 |
| close_error_candidate_rows | 2,646 |
| rerun_allowed_count | 133 |
| office_only_rerun_count | 133 |
| automation_transient_count | 6 |
| confirmed_boundary_count | 125 |
| recovered_promoted_row_count | 0 |

## Anti-False-Pass Gate Scope

| Gate | Value |
| --- | --- |
| aggregate_replay_object_row_count | 0 |
| alias_operation_evidence_row_count | 189 |
| alias_operation_row_count | 0 |
| anti_false_pass_gate | false |
| direct_mcp_function_call_count | 0 |
| exact_after_value_oracle_fail_count | 0 |
| marker_only_mutation_row_count | 0 |
| mcp_call_tool_replay_pass | true |
| mcp_list_tools_pass | true |
| office_expected_output_file_count | 1,198 |
| office_missing_result_file_count | 0 |
| office_result_file_count | 1,198 |
| package_only_office_pass_row_count | 0 |
| real_mcp_protocol_replay_pass | true |
| repair_dialog_count | 0 |
| security_dialog_count | 0 |
| unreadable_content_count | 0 |

## Campaign Office Boundary Scope

| Office status | Files | Candidate rows | Ledger treatment |
| --- | --- | --- | --- |
| close_error | 166 | 2,933 | boundary evidence only |
| pass | 2,745 | 22,872 | Office pass evidence; promotion rules decide count |
| pass_with_dialog | 3 | 21 | boundary evidence only |
| repair_dialog | 2 | 8 | boundary evidence only |
| timeout | 15 | 21 | boundary evidence only |
| unreadable_content | 24 | 280 | boundary evidence only |

## Campaign Office Boundary Details

| Package | Status | Candidate rows | Excluded | Office result | Message |
| --- | --- | --- | --- | --- | --- |
| pptx_chart_dense_203slides | unreadable_content | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-chartdense-long-0003-a3cfd7ad8f-pptx_chart_dense_203slides.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-aggr-chartdense-long-0003-a3cfd7ad8f-pptx_chart_dense_203slides.ppt |
| pptx_chart_dense_203slides | unreadable_content | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-chartdense-long2-0004-f4a7c52f25-pptx_chart_dense_203slides.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-aggr-chartdense-long2-0004-f4a7c52f25-pptx_chart_dense_203slides.pp |
| pptx_chart_dense_203slides | unreadable_content | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-chartdense-long3-0005-6e4f86a410-pptx_chart_dense_203slides.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-aggr-chartdense-long3-0005-6e4f86a410-pptx_chart_dense_203slides.pp |
| docx_travel_record_media | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-docx-travel-office-canary-0001-2f882a7cc2-docx_travel_record_media.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_007_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-docx007-office-canary-0001-8f55c95a27-docx_p18_drawing_007_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_007_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-docx007-office-canary-0002-0c7f2badf5-docx_p18_drawing_007_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_018_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-docx018-0002-131457bfc8-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_018_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-docx018-0003-31fac9424d-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_018_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-docx018-0004-81a8c4a11b-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_018_canvas | close_error | 13 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-docx018-0005-172cbcdba1-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_018_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-docx018-office-canary-0001-131457bfc8-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_018_canvas | close_error | 13 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-docx018-office-tail-0004-172cbcdba1-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_019_canvas | close_error | 13 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-docx019-tail-0005-9805f6f6b3-docx_p18_drawing_019_canvas.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_184_photo-cover-letter | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-docx184-office-canary-0001-4ee5673b1d-docx_ms_expansion_184_photo-cover-letter.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_108_complex-400p | pass_with_dialog | 10 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-legacy-docx-docx-ms-expansion-108-complex-400p-b1-docx_ms_expansion_108_complex-400p.json | BENIGN_DIALOG: AXWindow AXDialog NoYes Microsoft WordThis document contains links that may refer to other files, which could be a security risk. Do you want to  |
| pptx_ms_expansion_028_24p-ppt | close_error | 18 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-pptx028-office-0001-f7dfd1b8f6-pptx_ms_expansion_028_24p-ppt.json | Microsoft PowerPoint got an error: User canceled. |
| pptx_ms_expansion_080_28p-ppt | close_error | 22 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr-pptx080-office-0001-d481633658-pptx_ms_expansion_080_28p-ppt.json | Microsoft PowerPoint got an error: User canceled. |
| docx_ms_expansion_121_office-file | unreadable_content | 12 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-aggr2-docx121-vml-0001-5b5ee89ece-docx_ms_expansion_121_office-file.json | REPAIR_DIALOG: AXWindow AXDialog NoYes Microsoft WordWord found unreadable content in api-aggr2-docx121-vml-0001-5b5ee89ece-docx_ms_expansion_121_.... Do you wa |
| docx_ms_expansion_109_hexagon-labels-30-per-page | close_error | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-altcontent-canary-c03-0001-081f562fdb-docx_ms_expansion_109_hexagon-labels-30-per-page.json | Microsoft Word got an error: User canceled. |
| pptx_ms_expansion_041_office-file | close_error | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-artistic-blur-canary-pptx_ms_expansion_041_office-file.json | Microsoft PowerPoint got an error: User canceled. |
| docx_ms_expansion_108_complex-400p | pass_with_dialog | 10 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-blocker-v1-c02-0001-3b078334b3-docx_ms_expansion_108_complex-400p.json | BENIGN_DIALOG: AXWindow AXDialog NoYes Microsoft WordThis document contains links that may refer to other files, which could be a security risk. Do you want to  |
| docx_founder_intro_media | close_error | 2 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-blocker-v1-c03-0001-f79f1067ad-docx_founder_intro_media.json | Microsoft Word got an error: User canceled. |
| pptx_chart_dense_203slides | unreadable_content | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-c15-showleaderlines-0001-aa88da9323-pptx_chart_dense_203slides.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-c15-showleaderlines-0001-aa88da9323-pptx_chart_dense_203slides.pptx |
| pptx_chart_dense_203slides | unreadable_content | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-c15-showleaderlines-0003-2cfcc1e5f2-pptx_chart_dense_203slides.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-c15-showleaderlines-0003-2cfcc1e5f2-pptx_chart_dense_203slides.pptx |
| pptx_chart_dense_203slides | unreadable_content | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-c15-showleaderlines-0004-51e2ab811a-pptx_chart_dense_203slides.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-c15-showleaderlines-0004-51e2ab811a-pptx_chart_dense_203slides.pptx |
| pptx_chart_dense_203slides | unreadable_content | 17 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-c15-showleaderlines-0005-440ad2d7b5-pptx_chart_dense_203slides.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-c15-showleaderlines-0005-440ad2d7b5-pptx_chart_dense_203slides.pptx |
| docx_p18_drawing_019_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0001-0e33c9b472-docx_p18_drawing_019_canvas.json | Microsoft Word got an error: User canceled. |
| docx_travel_record_media | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0001-6b6a0b2c92-docx_travel_record_media.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_011_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0001-74c3812ad1-docx_p18_drawing_011_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_020_drawing | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0001-a8f75103cc-docx_p18_drawing_020_drawing.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_014_drawing | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0001-b253ef642b-docx_p18_drawing_014_drawing.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_130_classroom-newsletter | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0001-b3ed29e39a-docx_ms_expansion_130_classroom-newsletter.json | Microsoft Word got an error: User canceled. |
| pptx_chart_dense_203slides | unreadable_content | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0001-c807ed39e3-pptx_chart_dense_203slides.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-chunk-0001-c807ed39e3-pptx_chart_dense_203slides.pptx. PowerPoint c |
| pptx_ms_expansion_075_fabrikam-residences-the-ultimate-in- | unreadable_content | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0001-c83d58a165-pptx_ms_expansion_075_fabrikam-residences-the-ultimate-in-.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in <repo>/release-evidence/former-preserve-only-semantic-editability/promo |
| docx_p18_drawing_018_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0001-d0e862abc2-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_184_photo-cover-letter | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0001-f19f5c27d0-docx_ms_expansion_184_photo-cover-letter.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_018_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0002-131457bfc8-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_131_restaurant-brochure | close_error | 10 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0002-13712db088-docx_ms_expansion_131_restaurant-brochure.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_014_drawing | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0002-62d0c21215-docx_p18_drawing_014_drawing.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_203_photo-resume | close_error | 15 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0002-6ec45664d3-docx_ms_expansion_203_photo-resume.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_020_drawing | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0002-72690cc5f5-docx_p18_drawing_020_drawing.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_019_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0002-aba8894c69-docx_p18_drawing_019_canvas.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_146_geometric-cover-letter | close_error | 10 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0002-b86d921288-docx_ms_expansion_146_geometric-cover-letter.json | Microsoft Word got an error: User canceled. |
| pptx_chart_dense_203slides | unreadable_content | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0002-c1db4d8805-pptx_chart_dense_203slides.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-chunk-0002-c1db4d8805-pptx_chart_dense_203slides.pptx. PowerPoint c |
| docx_ms_expansion_158_organic-shapes-letterhead | close_error | 3 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0002-ec89d09ed5-docx_ms_expansion_158_organic-shapes-letterhead.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_020_drawing | close_error | 23 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0003-19992ba459-docx_p18_drawing_020_drawing.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_018_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0003-31fac9424d-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_019_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0003-cac5da9e85-docx_p18_drawing_019_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_014_drawing | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0003-fdf8993472-docx_p18_drawing_014_drawing.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_019_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0004-2395a58002-docx_p18_drawing_019_canvas.json | Microsoft Word got an error: User canceled. |
| pptx_ms_expansion_075_fabrikam-residences-the-ultimate-in- | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0004-75c7f861b2-pptx_ms_expansion_075_fabrikam-residences-the-ultimate-in-.json | Microsoft PowerPoint got an error: User canceled. |
| docx_p18_drawing_018_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0004-81a8c4a11b-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_018_canvas | close_error | 13 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0005-172cbcdba1-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| pptx_ms_expansion_075_fabrikam-residences-the-ultimate-in- | unreadable_content | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-chunk-0005-f9726023d7-pptx_ms_expansion_075_fabrikam-residences-the-ultimate-in-.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in <repo>/release-evidence/former-preserve-only-semantic-editability/promo |
| docx_policy_embedded_objects | close_error | 2 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-close-rerun-recovery-c02-0001-39926a4f22-docx_policy_embedded_objects.json | Microsoft Word got an error: User canceled. |
| docx_finance_tables_track | close_error | 3 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-close-rerun-recovery-c03-0002-cc2dce7b03-docx_finance_tables_track.json | Microsoft Word got an error: User canceled. |
| pptx_p5_animations_15 | close_error | 3 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-film-grain-canary-pptx_p5_animations_15.json | Microsoft PowerPoint got an error: User canceled. |
| pptx_p5_animations_15 | close_error | 3 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-film-grain-retry1-pptx_p5_animations_15.json | Microsoft PowerPoint got an error: User canceled. |
| docx_ms_expansion_118_geometric-business-cards | close_error | 2 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-geometric-cards-c01-0001-7191eb5c7f-docx_ms_expansion_118_geometric-business-cards.json | Microsoft Word got an error: User canceled. |
| docx_meeting_record | close_error | 12 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-docx-meeting-record-b1-docx_meeting_record.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_126_bold-business-report | close_error | 20 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-docx-ms-expansion-126-bold-business-report-b1-docx_ms_expansion_126_bold-business-report.json | Microsoft Word got an error: User canceled. |
| docx_p5_customxml_02 | close_error | 7 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-docx-p5customxml02-b1-docx_p5_customxml_02.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_113_swiss-design-resume | close_error | 4 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-docx113-b1-docx_ms_expansion_113_swiss-design-resume.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_137_mba | close_error | 4 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-docx137-b1-docx_ms_expansion_137_mba.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_169_modern-initials-resume | close_error | 10 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-docx169-b1-docx_ms_expansion_169_modern-initials-resume.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_170_test-segfault-while-save | close_error | 4 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-docx170-b1-docx_ms_expansion_170_test-segfault-while-save.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_189_fly-minimal-wrap | close_error | 0 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-docx189-b1-docx_ms_expansion_189_fly-minimal-wrap.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_190_fdo78333-1-minimized | close_error | 0 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-docx190-b1-docx_ms_expansion_190_fdo78333-1-minimized.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_196_bunny-ears-easter-party-flyer | close_error | 35 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-docx196-b1-docx_ms_expansion_196_bunny-ears-easter-party-flyer.json | Microsoft Word got an error: User canceled. |
| docx_layout21_footer | close_error | 12 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-layout21-b1-docx_layout21_footer.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_007_canvas | close_error | 20 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-p18canvas-b1-docx_p18_drawing_007_canvas.json | Microsoft Word got an error: User canceled. |
| pptx_p5_animations_07 | unreadable_content | 0 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-pptx-p5-animations-07-b1-pptx_p5_animations_07.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-ledger-officeext-pptx-p5-animations-07-b1-pptx_p5_animations_07.ppt |
| pptx_p5_transitions_03 | unreadable_content | 0 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-pptx-p5-transitions-03-b1-pptx_p5_transitions_03.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-ledger-officeext-pptx-p5-transitions-03-b1-pptx_p5_transitions_03.p |
| pptx_ms_expansion_016_office-file | unreadable_content | 0 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-pptx016-office-file-b1-pptx_ms_expansion_016_office-file.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in ooxml-stack/release-evidence/former-preserve-only-semantic-editability/ |
| pptx_ms_expansion_020_80p-ppt | repair_dialog | 8 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-pptx020-b1-pptx_ms_expansion_020_80p-ppt.json | AXWindow AXDialog OK PowerPoint couldn't read some content in api-ledger-officeext-pptx020-b1-pptx_ms_expansion_020_80p-ppt - Repaired and removed it. Please ch |
| pptx_ms_expansion_028_24p-ppt | unreadable_content | 0 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-pptx028-b1-pptx_ms_expansion_028_24p-ppt.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-ledger-officeext-pptx028-b1-pptx_ms_expansion_028_24p-ppt.pptx. Pow |
| pptx_ms_expansion_047_office-file | unreadable_content | 0 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-pptx047-office-file-b1-pptx_ms_expansion_047_office-file.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-ledger-officeext-pptx047-office-file-b1-pptx_ms_expansion_047_offic |
| pptx_ms_expansion_080_28p-ppt | unreadable_content | 0 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-pptx080-b4-pptx_ms_expansion_080_28p-ppt.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in <repo>/release-evidence/former-preserve-only-semantic-editability/promo |
| pptx_ms_expansion_087_2 | unreadable_content | 0 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-pptx087-2-b1-pptx_ms_expansion_087_2.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in <local-path>.pptx. PowerPoint can attempt to repair the presentation. I |
| pptx_ms_expansion_094_37p-ppt | close_error | 0 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-pptx094-b1-pptx_ms_expansion_094_37p-ppt.json | Microsoft PowerPoint got an error: User canceled. |
| pptx_ms_expansion_213_1 | repair_dialog | 0 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-pptx213-1-b1-pptx_ms_expansion_213_1.json | api-ledger-officeext-pptx213-1-b1-pptx_ms_expansion_213_1 AXWindow AXStandardWindow missing valuemissing valuemissing value api-ledger-officeext-pptx213-1-b1-pp |
| pptx_ms_expansion_036_financial-pitch-deck | close_error | 80 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-small-pptx036-financial-pitch-deck-b1-pptx_ms_expansion_036_financial-pitch-deck.json | Microsoft PowerPoint got an error: User canceled. |
| pptx_ms_expansion_211_bevel | close_error | 67 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-small-pptx211-bevel-b1-pptx_ms_expansion_211_bevel.json | Microsoft PowerPoint got an error: User canceled. |
| pptx_ms_expansion_099_oasis | close_error | 40 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-ledger-officeext-small2-pptx099-oasis-b1-pptx_ms_expansion_099_oasis.json | Microsoft PowerPoint got an error: User canceled. |
| docx_p5_customxml_02 | timeout | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next12h-customxml02-join-canary-docx_p5_customxml_02.json | >240s |
| docx_p5_customxml_02 | timeout | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next12h-customxml02-stroke-canary-recheck-docx_p5_customxml_02.json | >240s |
| docx_p5_customxml_02 | timeout | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next12h-customxml02-stroke-expand-docx_p5_customxml_02.json | >240s |
| docx_p5_customxml_02 | timeout | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next12h-customxml02-stroke-expand2-docx_p5_customxml_02.json | >240s |
| docx_p18_drawing_014_drawing | timeout | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next12h-drawing014-stroke-canary-docx_p18_drawing_014_drawing.json | >240s |
| docx_p18_drawing_014_drawing | timeout | 2 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next12h-drawing014-stroke-expand-docx_p18_drawing_014_drawing.json | >240s |
| docx_finance_tables_track | timeout | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next12h-finance-fill-canary-docx_finance_tables_track.json | >240s |
| docx_finance_tables_track | timeout | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next12h-finance-stroke-canary-docx_finance_tables_track.json | >240s |
| docx_production_performance_track | timeout | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next12h-production-fill-canary-docx_production_performance_track.json | >240s |
| docx_realestate_finance_policy | timeout | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next12h-realestate-fill-canary-docx_realestate_finance_policy.json | >240s |
| docx_resume_a4_embedded_charts | timeout | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next12h-resume-fill-canary-docx_resume_a4_embedded_charts.json | >240s |
| docx_resume_a4_embedded_charts | timeout | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next12h-resume-join-canary-docx_resume_a4_embedded_charts.json | >240s |
| docx_resume_a4_embedded_charts | timeout | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next12h-resume-join-expand-docx_resume_a4_embedded_charts.json | >240s |
| docx_p18_drawing_011_canvas | close_error | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-next15h-recovery-docx011-upright-canary-docx_p18_drawing_011_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_017_drawing | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c01-0001-01c5d8569c-docx_p18_drawing_017_drawing.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_012_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c01-0001-1219c8d89e-docx_p18_drawing_012_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_013_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c01-0001-22101feb40-docx_p18_drawing_013_canvas.json | Microsoft Word got an error: User canceled. |
| pptx_ms_expansion_049_7 | close_error | 23 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c01-0002-073c014014-pptx_ms_expansion_049_7.json | Microsoft PowerPoint got an error: User canceled. |
| docx_p18_drawing_012_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c01-0002-181c4bc707-docx_p18_drawing_012_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_017_drawing | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c01-0002-2f8cc221b8-docx_p18_drawing_017_drawing.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_013_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c01-0002-d0bb48ebd4-docx_p18_drawing_013_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_017_drawing | close_error | 16 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c01-0003-78cff51359-docx_p18_drawing_017_drawing.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_013_canvas | close_error | 20 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c01-0003-88ba54f438-docx_p18_drawing_013_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_012_canvas | close_error | 16 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c01-0003-92f6cecf77-docx_p18_drawing_012_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_008_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c02-0001-67bf880c8a-docx_p18_drawing_008_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p5_track_changes_02 | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c02-0001-757ec94e84-docx_p5_track_changes_02.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_010_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c02-0001-bdeb58dc67-docx_p18_drawing_010_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p5_track_changes_02 | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c02-0002-b965c008a6-docx_p5_track_changes_02.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_010_canvas | close_error | 17 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c02-0002-e96c7207dc-docx_p18_drawing_010_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_008_canvas | close_error | 11 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c02-0003-9357a87613-docx_p18_drawing_008_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p5_track_changes_02 | close_error | 10 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c02-0003-b15339263d-docx_p5_track_changes_02.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_147_basic-business-card | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c03-canary-0001-3e90048523-docx_ms_expansion_147_basic-business-card.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_140_headshot-cover-letter | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c04-canary-0001-cf4a9fb3f5-docx_ms_expansion_140_headshot-cover-letter.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_122_eighties-business-cards | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c05-0001-5b0916f28e-docx_ms_expansion_122_eighties-business-cards.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_009_canvas | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c06-canary-0001-1a1ac83fab-docx_p18_drawing_009_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_009_canvas | close_error | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c06-canary-0002-67398e1219-docx_p18_drawing_009_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_016_drawing | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c07-0001-6386e9b9b4-docx_p18_drawing_016_drawing.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_016_drawing | close_error | 17 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c07-0002-735d357251-docx_p18_drawing_016_drawing.json | Microsoft Word got an error: User canceled. |
| docx_procurement_rules_track | unreadable_content | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c08-canary-0001-d4c40f3ed2-docx_procurement_rules_track.json | Manual Word open reported: Word experienced an error trying to open the file and suggested Text Recovery converter. |
| docx_procurement_rules_track | close_error | 7 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c08-canary-0002-0f0f8c8fe0-docx_procurement_rules_track.json | Microsoft Word got an error: User canceled. |
| docx_table_of_contents_01 | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c09-canary-0001-59de1e10f7-docx_table_of_contents_01.json | Microsoft Word got an error: User canceled. |
| docx_table_of_contents_01 | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c09-canary-0002-605656437c-docx_table_of_contents_01.json | Microsoft Word got an error: User canceled. |
| docx_resume_a4_embedded_charts | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c10-canary-0001-3320ac211b-docx_resume_a4_embedded_charts.json | Microsoft Word got an error: User canceled. |
| docx_resume_customxml | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c13-0001-3bff95e5d4-docx_resume_customxml.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_015_drawing | close_error | 21 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c13-0001-5557937bc5-docx_p18_drawing_015_drawing.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_116_winter-holiday-party-checklist | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c13-0001-5b5bbe0209-docx_ms_expansion_116_winter-holiday-party-checklist.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_162_playful-business-cover-letter | close_error | 18 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c13-0001-b54bb4c1bf-docx_ms_expansion_162_playful-business-cover-letter.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_160_tdf160077-layoutincellb | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c13-0001-c88f77e409-docx_ms_expansion_160_tdf160077-layoutincellb.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_204_pink-floral-cover-letter | close_error | 23 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c13-0001-d57a802338-docx_ms_expansion_204_pink-floral-cover-letter.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_117_wdatevalueformat | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c13-0001-dd7fc1c8e5-docx_ms_expansion_117_wdatevalueformat.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_183_modern-calendar-with-highlights | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c13-0001-eca3d36dc6-docx_ms_expansion_183_modern-calendar-with-highlights.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_183_modern-calendar-with-highlights | close_error | 11 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c13-0002-227341b2bd-docx_ms_expansion_183_modern-calendar-with-highlights.json | Microsoft Word got an error: User canceled. |
| docx_resume_customxml | close_error | 14 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c13-0002-572cd2c016-docx_resume_customxml.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_116_winter-holiday-party-checklist | close_error | 8 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c13-0002-ad5eab6a17-docx_ms_expansion_116_winter-holiday-party-checklist.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_117_wdatevalueformat | close_error | 6 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c13-0002-aea592a049-docx_ms_expansion_117_wdatevalueformat.json | Microsoft Word got an error: User canceled. |
| docx_layout_resume | close_error | 8 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c13-0002-cd6a5bd136-docx_layout_resume.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_208_coverletter-a4 | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c14-canary-0001-1df9775bbe-docx_ms_expansion_208_coverletter-a4.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_208_coverletter-a4 | close_error | 15 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c14-canary-0002-4bad1fc197-docx_ms_expansion_208_coverletter-a4.json | Microsoft Word got an error: User canceled. |
| docx_p5_large_docx_01 | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c15-canary-0001-e56310bd8b-docx_p5_large_docx_01.json | Microsoft Word got an error: User canceled. |
| docx_p5_large_docx_01 | close_error | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c15-canary-0002-532299098b-docx_p5_large_docx_01.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_120_whitepaper-with-cover-image | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c16-canary-0001-cfce1f461e-docx_ms_expansion_120_whitepaper-with-cover-image.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_120_whitepaper-with-cover-image | close_error | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c16-canary-0002-f887bcfaa3-docx_ms_expansion_120_whitepaper-with-cover-image.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_119_small-business-email-marketing-templ | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c17-canary-0001-73aae246ea-docx_ms_expansion_119_small-business-email-marketing-templ.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_135_1-resume-docx | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c19-canary-0001-b62bd93e86-docx_ms_expansion_135_1-resume-docx.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_135_1-resume-docx | close_error | 7 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c19-canary-0002-f9a0dc762c-docx_ms_expansion_135_1-resume-docx.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_159_resume-a4 | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c20-canary-0001-5c593d3b41-docx_ms_expansion_159_resume-a4.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_182_modern-chronological-resume | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c21-canary-0001-3bd5273d70-docx_ms_expansion_182_modern-chronological-resume.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_136_1-resume-docx | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c23-canary-0001-5f89bafdea-docx_ms_expansion_136_1-resume-docx.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_136_1-resume-docx | close_error | 6 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c23-canary-0002-f8b8d31632-docx_ms_expansion_136_1-resume-docx.json | Microsoft Word got an error: User canceled. |
| docx_layout16_footer_media | close_error | 23 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c24-full-0001-195cd38391-docx_layout16_footer_media.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_173_resume | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c24-full-0001-444c48042e-docx_ms_expansion_173_resume.json | Microsoft Word got an error: User canceled. |
| docx_realestate_finance_policy | close_error | 23 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c24-full-0001-531cde6511-docx_realestate_finance_policy.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_202_organic-boho-digital-strategist-resu | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c24-full-0001-61869da342-docx_ms_expansion_202_organic-boho-digital-strategist-resu.json | Microsoft Word got an error: User canceled. |
| docx_marketing_strategy_charts | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c24-full-0001-8ac67f311f-docx_marketing_strategy_charts.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_173_resume | close_error | 7 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c24-full-0002-1fa89be5c2-docx_ms_expansion_173_resume.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_202_organic-boho-digital-strategist-resu | close_error | 10 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c24-full-0002-586c8a683a-docx_ms_expansion_202_organic-boho-digital-strategist-resu.json | Microsoft Word got an error: User canceled. |
| docx_project_intro_media | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c25-full-0001-94c549370d-docx_project_intro_media.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_112_generative-ai-at-isb | close_error | 4 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c25-full-0001-cf0b8da866-docx_ms_expansion_112_generative-ai-at-isb.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_207_metro-report | close_error | 19 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c25-full-0001-d01b63d87f-docx_ms_expansion_207_metro-report.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_175_childrens-s-holiday-wish-list | close_error | 21 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c26-full-0001-445ddbce8d-docx_ms_expansion_175_childrens-s-holiday-wish-list.json | Microsoft Word got an error: User canceled. |
| docx_layout_operations_media | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c26-full-0001-f97f552584-docx_layout_operations_media.json | Microsoft Word got an error: User canceled. |
| docx_layout_operations_media | close_error | 2 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c26-full-0002-39d95c9346-docx_layout_operations_media.json | Microsoft Word got an error: User canceled. |
| docx_p5_embedded_objects_01 | close_error | 18 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c27-full-0001-eba351f59a-docx_p5_embedded_objects_01.json | Microsoft Word got an error: User canceled. |
| docx_financing_plan_chart | close_error | 22 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-24h-c27-full-0001-f2ddb55be4-docx_financing_plan_chart.json | Microsoft Word got an error: User canceled. |
| docx_p5_track_changes_01 | close_error | 20 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c01-0001-08e56791a4-docx_p5_track_changes_01.json | Microsoft Word got an error: User canceled. |
| docx_development_history | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c01-0001-68c7da69f6-docx_development_history.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_148_fdo74605 | close_error | 22 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c01-0001-befca382a0-docx_ms_expansion_148_fdo74605.json | Microsoft Word got an error: User canceled. |
| docx_layout_market_analysis | close_error | 24 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c02-0001-51c93ada29-docx_layout_market_analysis.json | Microsoft Word got an error: User canceled. |
| docx_p5_fields_03 | close_error | 21 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c02-0001-a8b534ad92-docx_p5_fields_03.json | Microsoft Word got an error: User canceled. |
| docx_production_performance_track | close_error | 18 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c02-0001-e7dcc3e2c4-docx_production_performance_track.json | Microsoft Word got an error: User canceled. |
| docx_layout11_footer_media | close_error | 13 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c03-0001-1920e9b3e3-docx_layout11_footer_media.json | Microsoft Word got an error: User canceled. |
| docx_policy_embedded_objects | close_error | 2 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c03-0001-39926a4f22-docx_policy_embedded_objects.json | Microsoft Word got an error: User canceled. |
| docx_budget_rules_embedded | close_error | 22 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c03-0001-3ef7c6d861-docx_budget_rules_embedded.json | Microsoft Word got an error: User canceled. |
| docx_policy_embedded_objects | close_error | 21 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c03-0001-a056e20d9c-docx_policy_embedded_objects.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_197_business-report-prefiessional-design | close_error | 17 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c03-0001-cd8850abc9-docx_ms_expansion_197_business-report-prefiessional-design.json | Microsoft Word got an error: User canceled. |
| docx_layout_meeting_arrangement | close_error | 7 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c04-0001-b792a4725b-docx_layout_meeting_arrangement.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_154_tdf143384-tableinfoot-negativemargin | close_error | 12 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c04-0001-c47591f7fc-docx_ms_expansion_154_tdf143384-tableinfoot-negativemargin.json | Microsoft Word got an error: User canceled. |
| docx_budget_embedded_objects | close_error | 11 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c06-0001-62dc000d0a-docx_budget_embedded_objects.json | Microsoft Word got an error: User canceled. |
| docx_budget_embedded_objects | close_error | 16 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c06-0001-8e3ef8e92d-docx_budget_embedded_objects.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_005_smartart | close_error | 11 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c07-0001-312c060be9-docx_p18_drawing_005_smartart.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_114_pinstripes-business-cards | close_error | 12 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c07-0001-cd65c4f078-docx_ms_expansion_114_pinstripes-business-cards.json | Microsoft Word got an error: User canceled. |
| docx_finance_tables_track | close_error | 3 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c10-0001-cc2dce7b03-docx_finance_tables_track.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_141_fdo58949 | close_error | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c12-0001-19b8b6304a-docx_ms_expansion_141_fdo58949.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_138_reader | close_error | 4 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-8h-c12-0001-52e0622a67-docx_ms_expansion_138_reader.json | Microsoft Word got an error: User canceled. |
| docx_layout_financial_statement | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-next-0001-775c502de6-docx_layout_financial_statement.json | Microsoft Word got an error: User canceled. |
| docx_competitive_analysis_charts | close_error | 24 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-next-0001-9b9d9b8fe1-docx_competitive_analysis_charts.json | Microsoft Word got an error: User canceled. |
| docx_layout01_media | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-next-0001-9cf340ddce-docx_layout01_media.json | Microsoft Word got an error: User canceled. |
| docx_layout_service_product | close_error | 25 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-next-0001-adc48bd2e3-docx_layout_service_product.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_181_alt-chunk-header | pass_with_dialog | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-safe-c03-0001-b6f4bb403e-docx_ms_expansion_181_alt-chunk-header.json | BENIGN_DIALOG: AXWindow AXDialog NoYes Microsoft WordThis document contains fields that may refer to other files. Do you want to update the fields in this docum |
| pptx_brainstorm_training | close_error | 4 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-normal-safe-c03-0001-bd0e1b24e8-pptx_brainstorm_training.json | Microsoft PowerPoint got an error: AppleEvent timed out. |
| docx_p18_drawing_018_canvas | close_error | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-officeext-boundary8h-0001-ed1a65e96b-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_018_canvas | close_error | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-officeext-boundary8h-0002-a4387df5a9-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| docx_p18_drawing_018_canvas | close_error | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-officeext-boundary8h-0003-bcf1b63fe2-docx_p18_drawing_018_canvas.json | Microsoft Word got an error: User canceled. |
| pptx_ms_expansion_080_28p-ppt | close_error | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-officeext-boundary8h-0009-d80f043ef1-pptx_ms_expansion_080_28p-ppt.json | Microsoft PowerPoint got an error: User canceled. |
| pptx_ms_expansion_080_28p-ppt | close_error | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-officeext-boundary8h-0036-d84e6c703d-pptx_ms_expansion_080_28p-ppt.json | Microsoft PowerPoint got an error: User canceled. |
| pptx_ms_expansion_080_28p-ppt | close_error | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-officeext-boundary8h-0037-ef2da8df82-pptx_ms_expansion_080_28p-ppt.json | Microsoft PowerPoint got an error: User canceled. |
| pptx_ms_expansion_080_28p-ppt | close_error | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-officeext-boundary8h-0038-d90bd869f8-pptx_ms_expansion_080_28p-ppt.json | Microsoft PowerPoint got an error: User canceled. |
| pptx_ms_expansion_028_24p-ppt | unreadable_content | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-officeext-pptx028-canary-0003-dcf0fe413d-pptx_ms_expansion_028_24p-ppt.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-officeext-pptx028-canary-0003-dcf0fe413d-pptx_ms_expansion_028_24p- |
| pptx_ms_expansion_028_24p-ppt | unreadable_content | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-officeext-pptx028-final-0018-b794a20ad2-pptx_ms_expansion_028_24p-ppt.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-officeext-pptx028-final-0018-b794a20ad2-pptx_ms_expansion_028_24p-p |
| pptx_ms_expansion_028_24p-ppt | unreadable_content | 5 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-officeext-pptx028-followup-0004-94093cee4b-pptx_ms_expansion_028_24p-ppt.json | REPAIR_DIALOG: AXWindow AXDialog CancelRepair PowerPoint found a problem with content in api-officeext-pptx028-followup-0004-94093cee4b-pptx_ms_expansion_028_24 |
| docx_ms_expansion_139_reimbursement-form | close_error | 20 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-quick-proof-c02-0001-252e3ac882-docx_ms_expansion_139_reimbursement-form.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_163_mergers-acquisitions-report | close_error | 14 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-quick-proof-c03-0001-19b0296947-docx_ms_expansion_163_mergers-acquisitions-report.json | Microsoft Word got an error: User canceled. |
| docx_layout10_footer_media | close_error | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-schema-bool-batch2-0001-522aff1086-docx_layout10_footer_media.json | Microsoft Word got an error: User canceled. |
| docx_ms_expansion_171_tdf169843 | timeout | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-schema-vml-idmap-ext-normal-34-docx_ms_expansion_171_tdf169843.json | >240s |
| pptx_six_management_models | timeout | 2 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-theme-family-batch5-0001-fa3467be5d-pptx_six_management_models.json | >240s |
| docx_ms_expansion_121_office-file | unreadable_content | 1 | true | release-evidence/former-preserve-only-semantic-editability/office-results/api-vml-path-metadata-qpb2-0001-ceea4f5a7f-docx_ms_expansion_121_office-file.json | REPAIR_DIALOG: AXWindow AXDialog NoYes Microsoft WordWord found unreadable content in api-vml-path-metadata-qpb2-0001-ceea4f5a7f-docx_ms_expansion.... Do you wa |

## Source Integrity

| Source | Exists | Size | SHA-256 |
| --- | --- | --- | --- |
| semantic_inventory | true | 8,950 | cde9c930ff3b2f49fa58ac834129d76b134708ea917c6d979ec9b754adc8d34d |
| surface_editability | true | n/a | n/a |
| surface_source_summary | true | 2,811 | e94f520165d506957d6fdca07aefd250e3cd64f5b0c9158772ad6d0f7506f4c3 |
| surface_source_shards | true | n/a | n/a |
| semantic_summary | true | 3,842 | 2770242c000fedd4442c2e20d931deb7ac00c79f19c898f6cd1c40987428d100 |
| anti_false_pass_audit | true | 4,471 | 55203f00b9bf8051c90bc5acfd536b2b706867f51e2b382d00448c4270057510 |
| semantic_feasibility | true | 24,305 | 4b66eaf957091a172ee66cfb03d1bb22cc6d82699b6566a4817702423ccf7156 |
| campaign_promotion_rows | true | 74,734,120 | 1bb51baabac7b5951e169161e63413255497cb6472685274a61935ce63cfce2e |
| campaign_alias_operation_rows | true | 598,189 | e3bc4507b0103f06d14887b2b5d3268fe0a9c029b26bd656bc03a5c79d1cb0f9 |
| campaign_promotion_summary | true | 554 | dc84caa215d2b8ce92f87310a8cdde1c01ea2f2eaae6393b07907efe8b4d0ca5 |
| campaign_office_results | true | n/a | n/a |
| campaign_public_paths | true | n/a | n/a |
| operation_hydration | true | 1,778 | 0519a57da1c3fe4a4730ecaa870790f54bb7dbad9ea8fd02b104bde30210df07 |
| schema_policy | true | 2,599 | 166cce055498de0c30a4e148061ea78b5ab222a6d97397fc9e3fa8dcef436092 |
| remaining_bucket_summary | true | 136,501 | f5fce1d5ffcc35a37f9f8ad6dd6a5f01ef7028fd1c80068cffc044834fcb3d33 |
| chunk_plan | true | 1,486 | 6052ee246727af0d08650ab191f4a10ce7ba74397bb80dd83f10fece264c94b6 |
| chunk_checkpoint | true | 4,083,888 | 8bee5c084363dca6333de14e183b381281febdb80a045d41f2602719106b20c9 |
| chunk_timing | true | 575,869 | e49d03bcc634780160d5f83d93460bbe22639886b7f7379277c3fc5fbf5122b9 |
| chunk_boundary | true | 109,091 | aead993c932d041e765f31cbd07a98afb42ddba25e9d92e1f9a8fa1c018e4cd7 |
| close_error_diagnostic | true | 238,408 | 2509656ecf86f14484804e1761fe57b0e85744d2c4dbac3df4ae2d42b418bd1e |
| close_error_rerun | true | 132,496 | 13f652c6bd99798be779cde17de1d233546100c156549ee9626dc50ebd7a3e1a |

## Claim Boundary

- Raw XML element counts are not editable object counts.
- Readable / inspectable rows are not automatically writable.
- Surface-editable rows prove safe bounded writes, not semantic understanding.
- Semantic-editable rows require exact before/requested/after value proof.
- Office output file pass is a file-level gate, not an object-row pass.
- No full OOXML compatibility, full Office compatibility, or global full-write claim is proven.
- Anti-false-pass gate counts and campaign Office boundary counts use different evidence scopes.
