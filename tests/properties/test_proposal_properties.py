"""Bulk review is exactly ordered individual review; imports never select by confidence."""

from hypothesis import given, settings
from hypothesis import strategies as st

from mcda_studio.services import proposal_import_service as imports
from mcda_studio.services import proposal_service as svc
from proposal_builders import apply, event, inputs


@settings(max_examples=30, deadline=None)
@given(
    st.lists(st.integers(min_value=0, max_value=19), min_size=1, max_size=10, unique=True),
    st.sampled_from(["accepted", "corrected", "rejected"]),
)
def test_bulk_equals_individual_review_byte_for_byte(selection, status):
    from mcda_studio.services import project_service as ps

    p, intake = inputs()
    template = intake.proposals[0].model_copy(deep=True)
    intake.proposals = []
    for i in range(20):
        alt = f"option_{i}"
        p = ps.add_alternative(p, f"Option {i}", alt_id=alt)
        proposal = template.model_copy(deep=True)
        proposal.id, proposal.subject.alternative_id = f"proposal_{i}", alt
        intake.proposals.append(proposal)
    intake.project_fingerprint = p.fingerprint()
    workspace = svc.start(p, intake)
    from mcda_studio.domain.external_proposals import NumericProposal

    payload = NumericProposal(value=44.0, unit=None) if status == "corrected" else None
    events = [event(f"proposal_{i}", status, payload) for i in selection]
    bulk = apply(p, workspace, *events, bulk=True).workspace
    individual = workspace
    for e in events:
        individual = apply(p, individual, e).workspace
    assert bulk.model_dump_json() == individual.model_dump_json()
    assert bulk.intake == intake and workspace.reviews == []


@settings(max_examples=20, deadline=None)
@given(st.floats(min_value=0, max_value=1, allow_nan=False), st.booleans())
def test_interchange_order_and_confidence_metadata_are_preserved(value, reversed_order):
    p, intake = inputs()
    other = intake.proposals[0].model_copy(deep=True)
    other.id, other.subject.alternative_id = "quote_b", "b"
    intake.proposals.append(other)
    intake.proposals[0].confidence.value = value
    if reversed_order:
        intake.proposals.reverse()
    csv, registries = imports.csv_files(intake)
    a = imports.parse(p, csv, "csv", registries)
    b = imports.parse(p, intake.model_dump_json())
    assert a.model_dump_json() == b.model_dump_json()
