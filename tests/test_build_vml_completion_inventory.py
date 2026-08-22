import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_vml_completion_inventory import _canonical_id, _promotion_indexes, _result_status, _state


def test_canonical_id_uses_measured_row_identity():
    row = {"format": "docx", "package_id": "pkg", "part_name": "word/document.xml", "stable_id": "stable"}
    assert _canonical_id(row) == "docx|pkg|word/document.xml|stable"


def test_result_status_requires_one_explicit_status():
    assert _result_status({"results": [{"status": "pass"}]}) == "pass"
    assert _result_status({"results": [{"status": "pass"}, {"status": "timeout"}]}) == "mixed"


def test_state_keeps_office_boundary_out_of_ready_queue():
    hydration = {"blocker_type": "semantic_value_available_pending_proof", "operation_hydration_status": "hydrated"}
    assert _state({}, hydration, {"status": "pass"}, False, {}) == "ready_for_canary"
    assert _state({}, hydration, {"status": "timeout"}, False, {}) == "office_boundary"


def test_state_keeps_free_form_vml_style_structurally_coupled():
    hydration = {
        "blocker_type": "semantic_value_available_pending_proof",
        "operation_hydration_status": "hydrated",
        "attribute_name": "style",
    }
    assert _state({}, hydration, {"status": "pass"}, False, {}) == "structurally_coupled"


def test_state_promoted_wins_over_remaining_classifiers():
    assert _state({}, {}, {}, True, {}) == "already_promoted"


def test_state_terminalizes_reference_and_structure_fields():
    base = {"blocker_type": "semantic_value_available_pending_proof", "operation_hydration_status": "unsupported_mapping"}
    assert _state({"qname": "{urn:schemas-microsoft-com:vml}shape"}, base | {"attribute_name": "type"}, {}, False, {"element_type": "v:CT_Shape"}) == "identity_or_reference"
    assert _state({"qname": "{urn:schemas-microsoft-com:vml}textbox"}, base | {"attribute_name": "inset"}, {}, False, {"element_type": "v:CT_Textbox"}) == "structurally_coupled"


def test_state_terminalizes_empty_container_without_swallowing_boolean():
    base = {"blocker_type": "semantic_value_available_pending_proof", "operation_hydration_status": "unsupported_mapping"}
    assert _state({"qname": "{urn:schemas-microsoft-com:vml}fill"}, base | {"attribute_name": ""}, {}, False, {"element_type": "v:CT_Fill"}) == "no_semantic_value"
    assert _state({"qname": "{urn:schemas-microsoft-com:vml}shadow"}, base | {"attribute_name": "on"}, {}, False, {"element_type": "v:CT_Shadow"}) == "needs_operation"


def test_promotion_indexes_include_operation_target_alias(monkeypatch):
    rows = [{
        "family": "vml_drawing", "pass": True, "source_row_id": "p80|source",
        "package_id": "pkg", "operation_id": "vml.formula.eqn.set_value",
        "operation_target": "word/document.xml::/v:f[1]", "operation_params": {"attribute_name": "eqn"},
    }]
    monkeypatch.setattr("build_vml_completion_inventory._jsonl", lambda _: iter(rows))
    sources, targets = _promotion_indexes()
    assert sources["source"] == rows[0]
    assert targets[("pkg", "vml.formula.eqn.set_value", "word/document.xml::/v:f[1]", "")] == rows[0]
