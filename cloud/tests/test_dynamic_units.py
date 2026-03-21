"""Tests for _create_dynamic_units in debate.py."""


from hivemind_core.debate import _create_dynamic_units
from hivemind_core.types import DynamicTheoryUnit

# ---- 1. Empty document list -> returns empty list ----

def test_empty_document_list_returns_empty():
    result = _create_dynamic_units(
        density_value=5000,
        all_document_ids=[],
        document_tokens={"doc-1": 1000},
    )
    assert result == []


# ---- 2. Empty document_tokens -> returns empty list ----

def test_empty_document_tokens_returns_empty():
    result = _create_dynamic_units(
        density_value=5000,
        all_document_ids=["doc-1", "doc-2"],
        document_tokens={},
    )
    assert result == []


# ---- 3. Single document larger than density -> creates 1 unit containing that document ----

def test_single_large_document_creates_one_unit():
    result = _create_dynamic_units(
        density_value=3000,
        all_document_ids=["doc-big"],
        document_tokens={"doc-big": 10000},
    )
    assert len(result) == 1
    unit = result[0]
    assert isinstance(unit, DynamicTheoryUnit)
    assert unit.assigned_document_ids == ["doc-big"]
    assert unit.total_tokens == 10000


# ---- 4. Multiple small documents fitting in one density -> creates 1 unit ----

def test_multiple_small_documents_fit_one_unit():
    doc_ids = ["doc-1", "doc-2", "doc-3"]
    doc_tokens = {"doc-1": 500, "doc-2": 600, "doc-3": 400}
    # Total = 1500, well within density of 5000
    result = _create_dynamic_units(
        density_value=5000,
        all_document_ids=doc_ids,
        document_tokens=doc_tokens,
    )
    assert len(result) == 1
    unit = result[0]
    assert sorted(unit.assigned_document_ids) == sorted(doc_ids)
    assert unit.total_tokens == 1500


# ---- 5. Documents requiring multiple units -> splits correctly ----

def test_documents_split_into_multiple_units():
    doc_ids = [f"doc-{i}" for i in range(6)]
    doc_tokens = {doc_id: 1000 for doc_id in doc_ids}
    # density_value=2000 means each unit targets ~2000 tokens.
    # With 6 docs at 1000 tokens each, we expect 3 units of 2 docs each.
    result = _create_dynamic_units(
        density_value=2000,
        all_document_ids=doc_ids,
        document_tokens=doc_tokens,
    )
    assert len(result) >= 2
    # Verify sequential naming
    for i, unit in enumerate(result, start=1):
        assert unit.id == f"dynamic-unit-{i}"
        assert unit.name == f"Theory Unit {i}"


# ---- 6. Each unit's total_tokens respects density (within 1.2x) ----

def test_unit_tokens_respect_density_threshold():
    doc_ids = [f"doc-{i}" for i in range(10)]
    doc_tokens = {doc_id: 800 for doc_id in doc_ids}
    density_value = 2000
    result = _create_dynamic_units(
        density_value=density_value,
        all_document_ids=doc_ids,
        document_tokens=doc_tokens,
    )
    threshold = density_value * 1.2
    for unit in result:
        # A unit may exceed density only when it has a single document that is
        # itself larger than the density (tested separately above).  For
        # multi-doc units the total should stay within the 1.2x envelope.
        if len(unit.assigned_document_ids) > 1:
            assert unit.total_tokens <= threshold, (
                f"Unit {unit.id} has {unit.total_tokens} tokens, "
                f"exceeding 1.2x density ({threshold})"
            )


# ---- 7. All document IDs appear exactly once across all units ----

def test_all_document_ids_appear_exactly_once():
    doc_ids = [f"doc-{i}" for i in range(8)]
    doc_tokens = {doc_id: 700 for doc_id in doc_ids}
    result = _create_dynamic_units(
        density_value=2000,
        all_document_ids=doc_ids,
        document_tokens=doc_tokens,
    )
    collected_ids: list[str] = []
    for unit in result:
        collected_ids.extend(unit.assigned_document_ids)
    # Every document accounted for, no duplicates
    assert sorted(collected_ids) == sorted(doc_ids)
    assert len(collected_ids) == len(set(collected_ids)), "Duplicate document IDs found"
