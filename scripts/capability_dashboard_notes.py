"""Bilingual tooltip copy for the OOXML capability dashboard."""

from __future__ import annotations

from capability_dashboard_labels import display_text


NOTES = {
    "OOXML Element Capability Dashboard": (
        "中文：当前工作树 evidence 生成的能力看板，回答有多少对象、能读多少、能安全写多少、能语义写多少。\n"
        "EN: Live dashboard from working-tree evidence, covering object totals, readable coverage, safe writes, and semantic writes."
    ),
    "Claim Summary": (
        "中文：当前允许声明、禁止声明和 full claim 是否成立。\n"
        "EN: Current allowed claim, forbidden claim, and whether the full claim is proven."
    ),
    "Unit Definitions": (
        "中文：定义每种数字的单位，防止混淆 XML 元素、对象行和 Office 文件。\n"
        "EN: Defines metric units so XML elements, object rows, and Office files are not mixed."
    ),
    "Capability Levels": (
        "中文：能力总账，从原始 XML 元素到 semantic-editable 分层展示。\n"
        "EN: Capability ledger layered from raw XML elements to semantic-editable rows."
    ),
    "Semantic Blockers": (
        "中文：还不能进入 semantic-editable 的原因和数量。\n"
        "EN: Reasons and counts for rows not yet semantic-editable."
    ),
    "Families": (
        "中文：按 OOXML 对象家族拆分剩余缺口和可推进空间。\n"
        "EN: Remaining gaps and promotion headroom by OOXML object family."
    ),
    "Anti-False-Pass Gate Scope": (
        "中文：防 false-pass 门禁，避免包级、聚合、marker-only 证据被偷算成语义编辑。\n"
        "EN: Anti-false-pass gates that prevent package-level, aggregate, or marker-only evidence from being counted as semantic edits."
    ),
    "Campaign Office Boundary Scope": (
        "中文：campaign Office 结果范围；repair/unreadable/timeout 只算边界证据，不算通过。\n"
        "EN: Campaign Office result scope; repair/unreadable/timeout are boundary evidence, not passes."
    ),
    "Campaign Office Boundary Details": (
        "中文：失败 Office 结果的包级明细，用来解释边界并防止后续重复选择。\n"
        "EN: Package-level drill-down for failed Office results, used to explain boundaries and prevent repeat selection."
    ),
    "Source Integrity": (
        "中文：检查输入 evidence 是否存在，并记录大小和 hash。\n"
        "EN: Checks evidence input existence and records size/hash."
    ),
    "Claim Boundary": (
        "中文：不能越界宣传的红线。\n"
        "EN: Claim boundaries that must not be overstated."
    ),
    "xml_element_instances": (
        "中文：原始 XML 标签出现次数；这是规模指标，不是对象编辑能力。\n"
        "EN: Raw XML tag occurrences; this measures scale, not object editability."
    ),
    "object_candidates": (
        "中文：进入对象能力总账的候选行；不是全部 XML 标签。\n"
        "EN: Candidate rows in the object ledger, not all XML tags."
    ),
    "readable_inspectable": (
        "中文：能归类、定位、展示状态的对象；不等于可写。\n"
        "EN: Objects that can be classified, located, and inspected; this does not imply writing."
    ),
    "semantic_handle_object_denominator": (
        "中文：semantic handle 层看到的对象分母，不能和 campaign 分母相加。\n"
        "EN: Semantic-handle denominator; do not add it to the campaign denominator."
    ),
    "opaque_binary_package_dependencies": (
        "中文：非 XML 包依赖，如宏、OLE、媒体；没有专门模型前不能算语义可写。\n"
        "EN: Non-XML package dependencies such as macros, OLE, and media; not semantic-editable without a model."
    ),
    "surface_editable": (
        "中文：能安全定位对象并做边界内写入；不代表懂内部业务语义。\n"
        "EN: Can safely locate and mutate within object bounds; this does not prove internal semantics."
    ),
    "semantic_editable": (
        "中文：有 semantic model、请求值、写后精确值和 sibling safety 的对象行。\n"
        "EN: Object rows with semantic model, requested value, exact after value, and sibling safety proof."
    ),
    "full_write": (
        "中文：完整写入需要 family 级模型和依赖建模；当前没有全局声明。\n"
        "EN: Full-write requires family-level modeling and dependency modeling; no global claim exists."
    ),
    "unsupported_or_not_proven": (
        "中文：还缺语义值、定位、公开路径或 Office 绑定证明的对象行。\n"
        "EN: Rows still missing semantic value, resolution, public path, or Office-bound proof."
    ),
    "office_output_files": (
        "中文：真实 Office 打开的输出文件数；这是文件级门禁，不是对象行数。\n"
        "EN: Output files opened by native Office; this is a file-level gate, not object rows."
    ),
    "Surface-editable": (
        "中文：安全边界可写，只证明对象级安全写，不证明语义理解。\n"
        "EN: Safe bounded write; proves object-level safety, not semantic understanding."
    ),
    "Semantic-editable": (
        "中文：语义可写，要求 exact before/requested/after oracle。\n"
        "EN: Semantic writing requires exact before/requested/after oracle proof."
    ),
    "Unsupported / not proven": (
        "中文：当前还不能按更强能力层级声明。\n"
        "EN: Not yet claimable at a stronger capability tier."
    ),
    "Office output files": (
        "中文：Office 文件级通过，不可乘成对象级通过。\n"
        "EN: Office file-level pass; must not be multiplied into object-level pass."
    ),
    "Full claim": (
        "中文：全量声明是否成立；剩余阻断或门禁失败时必须是 false。\n"
        "EN: Whether the full claim is proven; must be false while blockers or gates fail."
    ),
    "no_semantic_value": (
        "中文：对象能定位，但当前模型抽不出可请求、可验证的语义值。\n"
        "EN: The object can be located, but no requestable, verifiable semantic value is extracted."
    ),
    "resolve_failure": (
        "中文：stable selector 或 XML 解析不能稳定定位唯一对象。\n"
        "EN: Stable selector or XML parser cannot resolve exactly one object."
    ),
    "semantic_value_available_pending_proof": (
        "中文：语义值已存在，但还缺完整 replay、公开路径、Office 绑定或 manifest 证明。\n"
        "EN: A semantic value exists, but replay, public path, Office binding, or manifest proof is incomplete."
    ),
    "relationship_identity_like": (
        "中文：这是关系或身份类标识，不能用泛化语义写入直接改。\n"
        "EN: Relationship or identity-like marker; do not mutate through generic semantic editing."
    ),
    "binary_payload_reference": (
        "中文：这是二进制或媒体载荷引用，需要专门 payload 模型。\n"
        "EN: Binary or media payload reference; needs a dedicated payload model."
    ),
    "needs_family_model": (
        "中文：需要针对该 OOXML family 建模后才能推进。\n"
        "EN: Needs a family-specific OOXML model before promotion."
    ),
    "needs_vendor_family_model": (
        "中文：厂商私有扩展，需要厂商字段模型或明确保留边界。\n"
        "EN: Vendor-private extension; needs a vendor field model or explicit preserve boundary."
    ),
}


HEADER_NOTES = {
    "Count": "中文：当前 evidence 中统计到的数量。\nEN: Count measured in current evidence.",
    "Unit": "中文：这个数字的单位。\nEN: Unit for this number.",
    "Denominator": "中文：这个数字所属的分母类型。\nEN: Denominator kind for this value.",
    "Strict claim": "中文：这行数字允许支持的最强声明。\nEN: Strongest claim supported by this row.",
    "Evidence": "中文：生成该数字的 evidence 来源。\nEN: Evidence source for this number.",
    "Reason": "中文：阻断进入更强能力层级的原因。\nEN: Reason blocking a stronger capability tier.",
    "Family": "中文：OOXML 对象家族分类。\nEN: OOXML object family.",
    "Pending proof": "中文：已经能抽出语义值，但还缺完整证明的对象数。\nEN: Objects with semantic values that still need complete proof.",
    "Explicit unsupported": "中文：已经有明确原因，不能用当前通用语义编辑推进的对象数。\nEN: Objects with explicit reasons that block current generic semantic promotion.",
    "Gate": "中文：代码或证据门禁项。\nEN: Code or evidence gate.",
    "Source": "中文：输入 evidence 的逻辑来源。\nEN: Logical evidence source.",
    "SHA-256": "中文：输入 evidence 文件 hash。\nEN: Hash of the evidence input file.",
}


def note_for(label: str, context: str = "") -> str:
    if label in NOTES:
        return NOTES[label]
    if label in HEADER_NOTES:
        return HEADER_NOTES[label]
    if context == "Claim Boundary":
        return "中文：这是一条声明红线。\nEN: This is a claim boundary."
    return (
        f"中文：这是「{display_text(label)}」的当前 evidence 值；请结合单位、分母和声明边界理解。\n"
        f"EN: Current evidence for '{display_text(label)}'; interpret it with unit, denominator, and claim boundary."
    )


def value_note(row_label: str, header: str, value: str, context: str = "") -> str:
    return (
        f"中文：「{display_text(row_label)}」在「{display_text(header)}」列的当前值是 {value}。\n"
        f"EN: Current value for '{display_text(row_label)}' under '{display_text(header)}' is {value}."
    )
