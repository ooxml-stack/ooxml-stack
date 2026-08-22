# DOCX Drawing Coverage Matrix

Machine-generated from DOCX drawing coverage JSON artifacts.
Do not edit statistics by hand.

## Sources

- Matrix JSON: `p21-docx-drawing-coverage-matrix-office.json`
- Summary JSON: `p21-docx-drawing-coverage-summary-office.json`

## Denominators

| Metric | Result |
| --- | ---: |
| DOCX/DOCM rows | 190 |
| supported-valid DOCX/DOCM rows | 189 |
| DOCX/DOCM files with drawing signals | 148 |
| selected regression cases | 130 |
| DOCM macro rows in denominator | 4 |
| quarantined DOCX rows | 1 |

## Family Matrix

| Family | Corpus files | Selected cases | Status | Tier |
| --- | --- | --- | --- | --- |
| `canvas_wpc` | 10 | 8 | `claimable_measured` | `claimable_measured_high_risk` |
| `chart_in_drawing` | 23 | 10 | `claimable_measured` | `claimable_measured_high_risk` |
| `floating_anchor` | 121 | 15 | `claimable_measured` | `claimable_measured_broad` |
| `group_wpg` | 63 | 15 | `claimable_measured` | `claimable_measured_standard` |
| `inline_drawing` | 72 | 12 | `claimable_measured` | `claimable_measured_broad` |
| `mixed_drawing_case` | 142 | 10 | `claimable_measured` | `claimable_measured_standard` |
| `picture` | 81 | 10 | `claimable_measured` | `claimable_measured_standard` |
| `smartart` | 8 | 8 | `claimable_measured` | `claimable_measured_high_risk` |
| `textbox` | 87 | 15 | `claimable_measured` | `claimable_measured_standard` |
| `wordart` | 49 | 15 | `claimable_measured` | `claimable_measured_standard` |

## Status Counts

| Status | Count |
| --- | ---: |
| `claimable_measured` | 52 |
| `regression_covered` | 36 |
| `smoke_only` | 32 |
| `preserve_only` | 23 |
| `unsupported_gap` | 49 |
| `unknown_unclassified` | 0 |

## Top Gap List

| Priority | Cell | Current status | Recommendation |
| --- | --- | --- | --- |
| 1 | `canvas_wpc:story_part=comment` | `unsupported_gap` | add native samples or classify as out of scope |
| 2 | `canvas_wpc:story_part=endnote` | `unsupported_gap` | add native samples or classify as out of scope |
| 3 | `canvas_wpc:story_part=footer` | `unsupported_gap` | add native samples or classify as out of scope |
| 4 | `canvas_wpc:story_part=footnote` | `unsupported_gap` | add native samples or classify as out of scope |
| 5 | `canvas_wpc:story_part=header` | `unsupported_gap` | add native samples or classify as out of scope |
| 6 | `chart_in_drawing:placement=floating` | `unsupported_gap` | add native samples or classify as out of scope |
| 7 | `chart_in_drawing:placement=inline` | `unsupported_gap` | add native samples or classify as out of scope |
| 8 | `chart_in_drawing:placement=mixed` | `unsupported_gap` | add native samples or classify as out of scope |
| 9 | `chart_in_drawing:story_part=comment` | `unsupported_gap` | add native samples or classify as out of scope |
| 10 | `chart_in_drawing:story_part=endnote` | `unsupported_gap` | add native samples or classify as out of scope |
| 11 | `chart_in_drawing:story_part=footer` | `unsupported_gap` | add native samples or classify as out of scope |
| 12 | `chart_in_drawing:story_part=footnote` | `unsupported_gap` | add native samples or classify as out of scope |
| 13 | `chart_in_drawing:story_part=header` | `unsupported_gap` | add native samples or classify as out of scope |
| 14 | `floating_anchor:placement=inline` | `unsupported_gap` | keep excluded from active-coverage claim denominator |
| 15 | `floating_anchor:placement=mixed` | `unsupported_gap` | keep excluded from active-coverage claim denominator |
| 16 | `floating_anchor:story_part=comment` | `unsupported_gap` | add native samples or classify as out of scope |
| 17 | `floating_anchor:story_part=endnote` | `unsupported_gap` | add native samples or classify as out of scope |
| 18 | `floating_anchor:story_part=footnote` | `unsupported_gap` | add native samples or classify as out of scope |
| 19 | `group_wpg:story_part=comment` | `unsupported_gap` | add native samples or classify as out of scope |
| 20 | `group_wpg:story_part=endnote` | `unsupported_gap` | add native samples or classify as out of scope |
| 21 | `group_wpg:story_part=footnote` | `unsupported_gap` | add native samples or classify as out of scope |
| 22 | `inline_drawing:placement=floating` | `unsupported_gap` | keep excluded from active-coverage claim denominator |
| 23 | `inline_drawing:placement=mixed` | `unsupported_gap` | keep excluded from active-coverage claim denominator |
| 24 | `inline_drawing:story_part=comment` | `unsupported_gap` | add native samples or classify as out of scope |
| 25 | `inline_drawing:story_part=endnote` | `unsupported_gap` | add native samples or classify as out of scope |

## Non-Claims

- No full Office compatibility claim.
- No full Word drawing parity claim.
- No SmartArt/layout/cache/pixel parity claim.
- No renderer or OfficeArt pixel parity claim.
