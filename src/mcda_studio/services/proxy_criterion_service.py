"""Disclosed fixed-score proxy pairs, preserving the complete original baseline."""

import hashlib
import json
from typing import Any, Literal

from pydantic import Field

from mcda_studio.domain.common import Issue, Severity
from mcda_studio.domain.derived import DerivedFormula, DerivedModel, SourceFactor
from mcda_studio.domain.errors import McdaError, ModelEditError, StaleRevisionError
from mcda_studio.domain.evidence import Origin, Review
from mcda_studio.domain.external_proposals import ExternalProposals, LocalModelCard, NumericProposal
from mcda_studio.domain.factor_uncertainty import FactorUncertaintyModel
from mcda_studio.domain.feasibility import FeasibilityResult
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.proxy_criterion import (
    ProxyAcknowledgements,
    ProxyCriterionPlan,
    ProxyPlanState,
)
from mcda_studio.domain.results import MavtResult, MavtSortingResult
from mcda_studio.domain.sidecar_common import SidecarModel
from mcda_studio.services import analysis_service as analysis
from mcda_studio.services import derived_service as derived
from mcda_studio.services import factor_analysis_service as factors
from mcda_studio.services import feasibility_service as feasibility
from mcda_studio.services import project_service as projects
from mcda_studio.services import proposal_service as proposals
from mcda_studio.services import proxy_plan_service as plans
from mcda_studio.services.questions_service import Question


class ProxyInputs(SidecarModel):
    project: Project
    plan: ProxyCriterionPlan
    scores: ExternalProposals | None = None
    configuration: AnalysisConfiguration = Field(default_factory=AnalysisConfiguration)
    model: DerivedModel | None = None
    uncertainty: FactorUncertaintyModel | None = None
    factor_parameters: factors.FactorRunParameters | None = None


class ProxyInspection(SidecarModel):
    inputs: ProxyInputs
    state: ProxyPlanState
    baseline: Project
    score_draft_fingerprint: str | None
    score_draft: Project | None
    with_proxy: Project | None
    overlap_removed: Project | None
    calculation: derived.DerivedCompilation | None
    model_card: LocalModelCard | None
    issues: list[Issue]
    questions: list[Question]
    unknown_facts: list[str]
    overlap_findings: list[str]
    weight_shares: dict[str, dict[str, dict[str, float]]]
    review_digest: str
    limitations: list[str]


class ProxyHalf(SidecarModel):
    status: Literal["completed", "unavailable"]
    project: Project
    configuration: AnalysisConfiguration
    result: MavtResult | MavtSortingResult | None = None
    factor_run: factors.FactorRunRecord | None = None
    feasibility: FeasibilityResult | None = None
    reason: str = ""
    coupling_digest: str | None = None
    coupling_draws: int = 0


class ProxyPairRequest(ProxyInputs):
    expected_review_digest: str
    acknowledgements: ProxyAcknowledgements
    review: Review


class ProxyComparisonBundle(SidecarModel):
    artifact_kind: Literal["proxy_comparison"] = "proxy_comparison"
    version: Literal[1] = 1
    request: ProxyPairRequest
    inspection: ProxyInspection
    status: Literal["completed", "unavailable"]
    without_proxy: ProxyHalf
    with_proxy: ProxyHalf
    limitations: list[str]
    digest: str


def _accepted(review: Review | None) -> bool:
    return bool(
        review and review.status == "accepted" and review.reviewer.strip() and review.note.strip()
    )


def _problem(code: str, message: str) -> Issue:
    return Issue(severity=Severity.ERROR, code=code, message=message)


def _draft(project: Project, state: ProxyPlanState) -> tuple[Project, Project | None]:
    tree = project.tree()
    leaf = state.criterion
    if (
        not leaf.id.startswith("disclosed_proxy_")
        or leaf.id in tree
        or any(n.id.startswith("disclosed_proxy_") for n in project.criteria)
        or not leaf.name.startswith("Disclosed model proxy")
    ):
        raise ModelEditError("PROXY_ID: one visibly labelled new disclosed_proxy_ leaf is required")
    if (
        leaf.scale is None
        or not leaf.scale.is_numeric
        or leaf.scale.anchor_mode != "fixed"
        or leaf.value_function is None
        or getattr(leaf.value_function, "out_of_domain", None) != "error"
    ):
        raise ModelEditError(
            "PROXY_DOMAIN: require a fixed numeric scale and an error outside its value domain"
        )
    if leaf.parent_id is not None and (leaf.parent_id not in tree or tree.is_leaf(leaf.parent_id)):
        raise ModelEditError("PROXY_PARENT: choose the root or an existing group")
    ids = [p.id for p in project.weight_profiles]
    if (
        not state.compared_profile_ids
        or len(set(state.compared_profile_ids)) != len(state.compared_profile_ids)
        or set(state.compared_profile_ids) - set(ids)
    ):
        raise ModelEditError("PROXY_PROFILES: explicitly select existing profiles")
    if set(state.swing_ratings) != set(state.compared_profile_ids) or any(
        value is None or value < 0 for value in state.swing_ratings.values()
    ):
        raise ModelEditError("PROXY_SWING: explicitly rate every compared profile; zero is allowed")
    removed = project.model_copy(deep=True)
    removed_ids: set[str] = set()
    for overlap in state.overlaps:
        if overlap.resolution != "remove_criterion":
            if overlap.remove_criterion_ids:
                raise ModelEditError(
                    "PROXY_REMOVAL: removal IDs require an explicit removal resolution"
                )
            continue
        if not overlap.remove_criterion_ids:
            raise ModelEditError("PROXY_REMOVAL: name each criterion to remove")
        for id in overlap.remove_criterion_ids:
            if id not in tree:
                raise ModelEditError("PROXY_REMOVAL: unknown overlapping criterion")
            doomed = set(tree.subtree_ids(id))
            feature = next((f for f in state.features if f.id == overlap.feature_id), None)
            if feature is None or not set(feature.criterion_ids) & doomed:
                raise ModelEditError(
                    "PROXY_REMOVAL: removal must concern the explicitly linked feature"
                )
            if leaf.parent_id in doomed or any(
                r.criterion_id in doomed for r in project.requirements or []
            ):
                raise ModelEditError(
                    "PROXY_REMOVAL: preserve the chosen parent and every feasibility requirement"
                )
            removed_ids.update(doomed)
    for id in tree.all_ids():
        if id in removed_ids and tree.node(id).parent_id not in removed_ids:
            removed = projects.remove_criterion(removed, id)
    draft = removed.model_copy(deep=True)
    draft.id = (
        "proxy_"
        + derived._digest(
            {
                "baseline": project.fingerprint(),
                "criterion": leaf.model_dump(mode="json"),
                "observations": {f.id: f.observed_at.isoformat() for f in state.features},
            }
        )[:24]
    )
    draft.criteria.append(leaf.model_copy(deep=True))
    for profile in draft.weight_profiles:
        if profile.id in state.swing_ratings:
            rating = state.swing_ratings[profile.id]
            assert rating is not None
            profile.judgements[leaf.id] = rating
    return draft, removed if removed_ids else None


def _disclosures(
    inputs: ProxyInputs, state: ProxyPlanState, card: LocalModelCard | None, sources: set[str]
) -> tuple[list[Issue], list[str], list[str]]:
    issues: list[Issue] = []
    unknowns: list[str] = []
    findings: list[str] = []
    for name in plans.CARD_FIELDS:
        fact = state.card_facts.get(name)
        raw = None if card is None else getattr(card, name, card.details.get(name))
        if (
            fact is None
            or not _accepted(fact.review)
            or not fact.source_ids
            or set(fact.source_ids) - sources
            or fact.value != raw
        ):
            issues.append(
                _problem(
                    "PROXY_CARD_FACT",
                    f"Supply and review the exact sourced model-card fact: {name}",
                )
            )
            continue
        words = fact.value.strip().casefold()
        if fact.unknown:
            if not fact.reason.strip():
                issues.append(_problem("PROXY_UNKNOWN_REASON", f"Explain the unknown fact: {name}"))
            unknowns.append(name)
        elif words in {"unknown", "no evidence supplied", "unspecified"}:
            issues.append(
                _problem(
                    "PROXY_UNKNOWN_DISCLOSURE",
                    f"Explicitly mark and explain the unknown fact: {name}",
                )
            )
    if set(state.card_facts) - set(plans.CARD_FIELDS):
        issues.append(
            _problem(
                "PROXY_CARD_FIELDS",
                "Use the declared card fields; put additional details in the raw card",
            )
        )
    if (
        not state.licence_compatible
        or not _accepted(state.licence_review)
        or state.card_facts.get("licence") is None
        or state.card_facts["licence"].unknown
        or state.card_facts.get("use_restrictions") is None
        or state.card_facts["use_restrictions"].unknown
    ):
        issues.append(
            _problem(
                "PROXY_LICENCE",
                "Known licence and use restrictions must be explicitly reviewed as compatible",
            )
        )
    feature_ids = [f.id for f in state.features]
    overlap_ids = [o.feature_id for o in state.overlaps]
    if (
        not feature_ids
        or len(set(feature_ids)) != len(feature_ids)
        or len(set(overlap_ids)) != len(overlap_ids)
        or set(feature_ids) != set(overlap_ids)
    ):
        issues.append(
            _problem(
                "PROXY_FEATURES",
                "Declare unique features and exactly one explicit overlap resolution per feature",
            )
        )
    factor_ids = {s.id for s in inputs.model.sources} if inputs.model else set()
    cutoff = state.card_facts.get("observation_cutoff")
    for feature in state.features:
        if (
            not _accepted(feature.review)
            or set(feature.source_ids) - sources
            or set(feature.criterion_ids) - set(inputs.project.tree().all_ids())
            or set(feature.factor_ids) - factor_ids
        ):
            issues.append(
                _problem(
                    "PROXY_FEATURE_REVIEW",
                    f"Review known feature IDs and source lineage: {feature.id}",
                )
            )
        if cutoff is not None and not cutoff.unknown:
            from datetime import date

            try:
                if feature.observed_at > date.fromisoformat(cutoff.value):
                    issues.append(
                        _problem(
                            "PROXY_CUTOFF",
                            f"Feature {feature.id} is after the declared observation cutoff",
                        )
                    )
            except ValueError:
                issues.append(
                    _problem("PROXY_CUTOFF", "The known observation cutoff must be an ISO date")
                )
        findings.append(
            f"{feature.id}: criteria {feature.criterion_ids}; factors {feature.factor_ids}; "
            + (
                "shared IDs require explicit review"
                if feature.criterion_ids or feature.factor_ids
                else "text-only declaration needs explicit review; no semantic overlap inferred"
            )
        )
    for overlap in state.overlaps:
        if not _accepted(overlap.review) or not overlap.rationale.strip():
            issues.append(
                _problem(
                    "PROXY_OVERLAP", f"Review the explicit overlap resolution: {overlap.feature_id}"
                )
            )
        if overlap.resolution == "baseline_only":
            issues.append(
                _problem(
                    "PROXY_BASELINE_ONLY",
                    f"The chosen resolution for {overlap.feature_id} permits only the baseline",
                )
            )
    if not _accepted(state.plan_review):
        issues.append(
            _problem(
                "PROXY_PLAN_REVIEW",
                "Review the complete card, features, scores and swing judgements",
            )
        )
    return issues, unknowns, findings


def _scores(
    inputs: ProxyInputs, draft: Project, state: ProxyPlanState
) -> tuple[derived.DerivedCompilation, LocalModelCard]:
    workspace = inputs.scores
    if workspace is None or state.score_workspace_digest != workspace.digest:
        raise ModelEditError("PROXY_SCORE_DIGEST: bind the exact reviewed score workspace")
    if (
        workspace.source_project != draft
        or workspace.intake.project_fingerprint != draft.fingerprint()
    ):
        raise StaleRevisionError(
            "Proxy score proposals must be reviewed against this exact analysis draft"
        )
    inspection = proposals.inspect(draft, workspace)
    intake = proposals.resolved_intake(workspace)
    card = intake.model_cards.get(state.card_id or "")
    if card is None or derived._digest(card.model_dump(mode="json")) != state.card_digest:
        raise ModelEditError("PROXY_CARD_DIGEST: retain the exact declared model card")
    sources: list[SourceFactor] = []
    formulas: list[DerivedFormula] = []
    for alternative in draft.alternatives:
        rows = [
            r
            for r in inspection.rows
            if r.original.subject.alternative_id == alternative.id
            and r.original.subject.criterion_id == state.criterion.id
            and r.review
            and r.review.status in {"accepted", "corrected"}
            and proposals.measurement(r.effective) is not None
        ]
        if len(rows) != 1:
            raise ModelEditError(
                "PROXY_SCORE: one accepted fixed numeric score per alternative is required"
            )
        row = rows[0]
        if (
            row.issues
            or not isinstance(row.effective, NumericProposal)
            or row.original.model_card_id != state.card_id
            or row.original.model_card_digest != state.card_digest
        ):
            raise ModelEditError(
                "PROXY_SCORE: resolve score issues and bind the declared model version"
            )
        if any(f.observed_at > row.original.run_at.date() for f in state.features):
            raise ModelEditError(
                "PROXY_SCORE_DATE: a feature cannot be observed after the score was produced"
            )
        assert row.review is not None
        source_id = row.review.primary_source_id
        if source_id not in intake.sources:
            raise ModelEditError("PROXY_SCORE_SOURCE: retain the reviewed primary source")
        id = f"proxy_score_{len(sources)}"
        review = Review(
            status="accepted",
            reviewer=row.review.reviewer,
            reviewed_at=row.review.reviewed_at,
            note=row.review.note,
        )
        if not _accepted(review):
            raise ModelEditError("PROXY_SCORE_REVIEW: disclose the reviewer's reason")
        origin = Origin(
            kind="tool",
            proposed_by=row.original.tool_id,
            tool_id=row.original.tool_id,
            tool_version=row.original.tool_version,
        )
        sources.append(
            SourceFactor(
                id=id,
                value=row.effective.value,
                unit=row.effective.unit or "1",
                source=intake.sources[source_id],
                origin=origin,
                review=review,
            )
        )
        formulas.append(
            DerivedFormula(
                id=f"proxy_measure_{len(formulas)}",
                expression=id,
                unit=row.effective.unit or "1",
                alternative_id=alternative.id,
                criterion_id=state.criterion.id,
                origin=origin,
                review=review,
            )
        )
    model = DerivedModel(
        project_fingerprint=draft.fingerprint(), sources=sources, formulas=formulas
    )
    # Declare dimensional score units explicitly.
    unit = state.criterion.scale.unit if state.criterion.scale else None
    if unit and unit != "1":
        model.units[unit] = {"proxy_score": 1}
    report = derived.preview(draft, model)
    return derived.compilation_bundle(draft, model, report.review_digest), card


def inspect(inputs: ProxyInputs) -> ProxyInspection:
    state = plans.current(inputs.plan)
    project = inputs.project
    issues: list[Issue] = []
    if state.project_fingerprint != project.fingerprint():
        issues.append(
            _problem("PROXY_STALE", "The original project changed; create a newly reviewed plan")
        )
    if inputs.model is not None and inputs.model.project_fingerprint != project.fingerprint():
        issues.append(
            _problem(
                "PROXY_MODEL_STALE",
                "Feature factor links need a model bound to the exact baseline project",
            )
        )
    draft = removed = compiled = card = calculation = None
    shares: dict[str, dict[str, dict[str, float]]] = {}
    try:
        draft, removed = _draft(project, state)
        for id in state.compared_profile_ids:
            cfg = inputs.configuration.model_copy(
                update={"method": "mavt", "weight_profile_id": id}
            )
            before = analysis.preview_weights(project, cfg)
            after = analysis.preview_weights(draft, cfg)
            if not before.weights_ready or not after.weights_ready:
                raise ModelEditError("PROXY_WEIGHTS: resolve every sibling swing rating explicitly")
            shares[id] = {"before": before.global_weights, "after": after.global_weights}
        calculation, card = _scores(inputs, draft, state)
        compiled = calculation.project
    except McdaError as exc:
        issues.append(_problem("PROXY_INPUTS", str(exc)))
    intake = proposals.resolved_intake(inputs.scores) if inputs.scores else None
    if card is None and intake:
        card = intake.model_cards.get(state.card_id or "")
    more, unknowns, findings = _disclosures(
        inputs, state, card, set(intake.sources) if intake else set()
    )
    issues.extend(more)
    try:
        profile = project.resolve_profile(inputs.configuration)
        if profile is None or profile.id not in state.compared_profile_ids:
            issues.append(
                _problem("PROXY_CONFIGURATION", "Select a reviewed compared profile or scenario")
            )
    except McdaError as exc:
        issues.append(_problem("PROXY_CONFIGURATION", str(exc)))
    result = ProxyInspection(
        inputs=inputs.model_copy(deep=True),
        state=state,
        baseline=project.model_copy(deep=True),
        score_draft_fingerprint=draft.fingerprint() if draft else None,
        score_draft=draft,
        with_proxy=compiled,
        overlap_removed=removed,
        calculation=calculation,
        model_card=card,
        issues=issues,
        questions=[
            Question(
                group="blocking",
                code=i.code,
                question=i.message,
                why="Proxy activation requires explicit disclosure and review",
                evidence="proxy plan",
            )
            for i in issues
        ],
        unknown_facts=unknowns,
        overlap_findings=findings,
        weight_shares=shares,
        review_digest="",
        limitations=[
            "The external score is fixed reviewed input, never an engine prediction "
            "or outcome probability.",
            "PROMETHEE II and AHP proxy pairs are unavailable; "
            "ordinary method comparisons remain separate.",
            *[f"Explicitly unknown model-card fact: {name}" for name in unknowns],
        ],
    )
    result.review_digest = derived._digest(
        result.model_dump(mode="json", exclude={"review_digest"})
    )
    return result


def _with_factors(
    inputs: ProxyInputs, inspection: ProxyInspection
) -> tuple[DerivedModel, FactorUncertaintyModel]:
    assert inputs.model is not None and inputs.uncertainty is not None
    assert inspection.with_proxy is not None and inspection.calculation is not None
    # Validate the original bindings first. The new, explicit bundle records this rebind.
    from mcda_studio.services import factor_uncertainty_service

    factor_uncertainty_service.plan(inputs.project, inputs.model, inputs.uncertainty)
    model = inputs.model.model_copy(deep=True)
    model.project_fingerprint = inspection.with_proxy.fingerprint()
    retained = set(inspection.with_proxy.tree().leaves())
    for formula in model.formulas:
        if formula.criterion_id not in retained:
            formula.alternative_id = formula.criterion_id = None
    additions = inspection.calculation.preview.model
    ids = {s.id for s in model.sources} | {f.id for f in model.formulas}
    if ids & ({s.id for s in additions.sources} | {f.id for f in additions.formulas}):
        raise ModelEditError("PROXY_FACTOR_IDS: proxy factor/formula IDs collide with the baseline")
    for unit, dimension in additions.units.items():
        if unit in model.units and model.units[unit] != dimension:
            raise ModelEditError("PROXY_UNITS: explicit score unit conflicts with a baseline unit")
        model.units[unit] = dimension
    model.sources.extend(additions.sources)
    model.formulas.extend(additions.formulas)
    uncertainty = inputs.uncertainty.model_copy(deep=True)
    uncertainty.project_fingerprint = inspection.with_proxy.fingerprint()
    uncertainty.model_digest = derived.preview(inspection.with_proxy, model).model_digest
    return model, uncertainty


def run_pair(request: ProxyPairRequest) -> ProxyComparisonBundle:
    inputs = ProxyInputs.model_validate_json(
        request.model_dump_json(include=set(ProxyInputs.model_fields))
    )
    inspection = inspect(inputs)
    if inspection.review_digest != request.expected_review_digest:
        raise StaleRevisionError("Proxy preview changed; review both copies and weights again")
    if not inspection.state.enabled:
        raise ModelEditError(
            "PROXY_DISABLED: explicitly enable the separate preview before running"
        )
    if inspection.issues:
        raise ModelEditError("PROXY_BLOCKED: " + "; ".join(i.message for i in inspection.issues))
    acks = request.acknowledgements
    if not (
        acks.card
        and acks.overlap
        and acks.weight_changes
        and (acks.unknown_facts or not inspection.unknown_facts)
    ):
        raise ModelEditError(
            "PROXY_ACKNOWLEDGEMENTS: acknowledge card, overlap, changed shares and unknown facts"
        )
    if not _accepted(request.review):
        raise ModelEditError(
            "PROXY_RUN_REVIEW: record the named analyst's reason for the paired run"
        )
    assert inspection.with_proxy is not None
    cfg = inputs.configuration
    halves: list[ProxyHalf] = []
    for project in [inputs.project, inspection.with_proxy]:
        halves.append(
            ProxyHalf(
                status="unavailable",
                project=project.model_copy(deep=True),
                configuration=cfg.model_copy(deep=True),
                reason="Run has not completed",
            )
        )
    supported = cfg.method in {"mavt", "mavt_sorting"}
    pair_factors = None
    pair_factor_error = None
    if inputs.factor_parameters is not None:
        if inputs.factor_parameters.configuration != cfg:
            raise ModelEditError(
                "PROXY_FACTOR_CONFIGURATION: pair and factor configurations must be identical"
            )
        if inputs.model is None or inputs.uncertainty is None:
            raise ModelEditError("PROXY_FACTOR_INPUTS: supply both original model and uncertainty")
        if supported:
            if factors._configuration(inputs.project, inputs.factor_parameters) != cfg:
                raise ModelEditError(
                    "PROXY_FACTOR_CONFIGURATION: use the ordinary factor run's resolved method"
                )
            try:
                pair_factors = _with_factors(inputs, inspection)
            except McdaError as exc:
                pair_factor_error = str(exc)
    factor_ids = sorted(s.id for s in inputs.model.sources) if inputs.model else []
    for index, half in enumerate(halves):
        if not supported:
            half.reason = (
                "PROXY_METHOD_UNAVAILABLE: only MAVT, value-based sorting and "
                "fixed-weight factor SMAA-2 pairs are supported"
            )
            continue
        try:
            if inputs.factor_parameters is None:
                result = analysis.evaluate_project(half.project, cfg)
                assert isinstance(result, MavtResult | MavtSortingResult)
                half.result = result
            else:
                assert inputs.model is not None and inputs.uncertainty is not None
                if index == 1 and pair_factor_error:
                    raise ModelEditError(pair_factor_error)
                if index == 0:
                    model, uncertainty = inputs.model, inputs.uncertainty
                else:
                    assert pair_factors is not None
                    model, uncertainty = pair_factors
                coupling = hashlib.sha256()
                count = 0

                def record(values: dict[str, float], draw: int, coupling: Any = coupling) -> None:
                    nonlocal count
                    coupling.update(
                        (
                            derived._digest(
                                {"index": draw, "factors": {id: values[id] for id in factor_ids}}
                            )
                            + "\n"
                        ).encode()
                    )
                    count += 1

                half.factor_run = factors.execute(
                    half.project, model, uncertainty, inputs.factor_parameters, check_draw=record
                )
                half.result = half.factor_run.result.reference
                half.coupling_digest = coupling.hexdigest()
                half.coupling_draws = count
            reference_project = half.project
            if half.factor_run is not None:
                fp = derived.preview(half.project, half.factor_run.model)
                reference_project = derived.compile_copy(
                    half.project, half.factor_run.model, fp.review_digest
                )
            half.feasibility = (
                feasibility.check_feasibility(reference_project)
                if reference_project.requirements
                else None
            )
            half.reason = ""
            half.status = "completed"
        except McdaError as exc:
            half.reason = str(exc)
    complete = all(half.status == "completed" for half in halves)
    if (
        complete
        and inputs.factor_parameters
        and (
            halves[0].coupling_digest != halves[1].coupling_digest
            or halves[0].coupling_draws != halves[1].coupling_draws
        )
    ):
        raise ModelEditError(
            "PROXY_COUPLING: every non-proxy factor draw must be bit-identical in both halves"
        )
    bundle = ProxyComparisonBundle(
        request=request.model_copy(deep=True),
        inspection=inspection,
        status="completed" if complete else "unavailable",
        without_proxy=halves[0],
        with_proxy=halves[1],
        limitations=[
            *inspection.limitations,
            "Both halves are retained. An unavailable half makes the entire comparison "
            "unavailable; no consensus or average is computed.",
        ],
        digest="",
    )
    bundle.digest = derived._digest(bundle.model_dump(mode="json", exclude={"digest"}))
    return bundle


def verify(document: dict[str, Any]) -> ProxyComparisonBundle:
    bundle = ProxyComparisonBundle.model_validate_json(json.dumps(document))
    if bundle.digest != derived._digest(bundle.model_dump(mode="json", exclude={"digest"})):
        raise ModelEditError("PROXY_BUNDLE_DIGEST: the complete paired bundle changed")
    if run_pair(bundle.request) != bundle:
        raise ModelEditError(
            "PROXY_REPLAY: both projects, reviews, results and all-draw coupling must reproduce"
        )
    return bundle
