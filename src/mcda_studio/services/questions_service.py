"""Read-only research questions from model gaps and existing analysis results.

Each signal keeps its own meaning; the result reports coverage and does not claim robustness.
"""

import json
from typing import Any, Literal

from pydantic import Field, ValidationError

from mcda_studio.domain.common import DomainModel, Severity
from mcda_studio.domain.errors import McdaError, ValidationFailed
from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.external_proposals import ExternalProposals
from mcda_studio.domain.model_comparison import ModelComparison
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.results import SmaaResult, SortingSensitivityResult
from mcda_studio.domain.validation import validate_structure
from mcda_studio.methods.mavt.measurement_range import (
    MeasurementRangeResult,
    assess_measurement_range,
)
from mcda_studio.services import (
    analysis_service,
    comparison_service,
    evidence_service,
    evidence_workspace_service,
    feasibility_service,
)


class Question(DomainModel):
    group: Literal["blocking", "decision_sensitive", "evidence_quality"]
    code: str
    question: str
    why: str
    evidence: str
    alternative_id: str | None = None
    criterion_id: str | None = None
    requirement_id: str | None = None
    measurement_range: MeasurementRangeResult | None = None


class QuestionsResult(DomainModel):
    project_fingerprint: str
    configuration: AnalysisConfiguration
    questions: list[Question] = Field(default_factory=list)
    coverage: list[str]
    limitations: list[str]


def evidence_questions(
    project: Project, dossier: EvidenceDossier
) -> tuple[list[Question], list[str]]:
    """Explain unresolved dossier claims without promoting claims to measurements."""
    review = evidence_service.preview(project, dossier)
    errors = [issue for issue in review.issues if issue.severity is Severity.ERROR]
    if errors:
        codes = ", ".join(sorted({issue.code for issue in errors}))
        return [], [f"Evidence questions could not be assessed: {codes}."]
    by_id = {claim.id: claim for claim in dossier.claims}
    found: list[Question] = []
    for support_cell in evidence_workspace_service.inspect(project, dossier).support:
        if support_cell.status not in {"unsupported", "unverified"}:
            continue
        alt = next(a.name for a in project.alternatives if a.id == support_cell.alternative_id)
        leaf = project.tree().node(support_cell.criterion_id).name
        found.append(
            Question(
                group="evidence_quality",
                code="MEASUREMENT_WITHOUT_ACCEPTED_SUPPORT",
                question=f"What supports {alt}'s measurement for {leaf}?",
                why=(
                    f"The entered value {support_cell.measurement!r} has no accepted matching "
                    "claim in this dossier. This is a provenance gap, not a finding that the "
                    "value is invalid. Resolving it may confirm or change this decision input."
                ),
                evidence="Find a source for this value, check its units and review its claim.",
                alternative_id=support_cell.alternative_id,
                criterion_id=support_cell.criterion_id,
            )
        )
    for claim_id in review.unreviewed_claims:
        claim = by_id[claim_id]
        origin = claim.origin.proposed_by
        if claim.origin.kind == "tool":
            origin += f" (tool {claim.origin.tool_id}"
            if claim.origin.tool_version:
                origin += f", version {claim.origin.tool_version}"
            origin += ")"
        found.append(
            Question(
                group="evidence_quality",
                code="UNREVIEWED_CLAIM",
                question=f"Should claim {claim_id} be accepted, corrected or rejected?",
                why=(
                    f"Proposed by {origin}; source: {claim.source.name} "
                    f"({claim.source.classification}), {claim.source.reference}"
                    f"{', ' + claim.source.location if claim.source.location else ''}."
                ),
                evidence="Review the cited source and record a human decision.",
                alternative_id=claim.alternative_id,
                criterion_id=claim.criterion_id,
            )
        )
    for claim_id in review.outdated_claims:
        claim = by_id[claim_id]
        found.append(
            Question(
                group="evidence_quality",
                code="OUTDATED_CLAIM",
                question=f"Is claim {claim_id} still current?",
                why=f"The claim is marked outdated; source date: {claim.source.date.isoformat()}.",
                evidence="Obtain a current source and review its claim.",
                alternative_id=claim.alternative_id,
                criterion_id=claim.criterion_id,
            )
        )
    for cell in review.conflicting_cells:
        found.append(
            Question(
                group="evidence_quality",
                code="CONFLICTING_CLAIMS",
                question="Which conflicting claim is supported?",
                why="Unrejected claims for this alternative and criterion state different values.",
                evidence="Compare sources and explicitly review each claim.",
                alternative_id=cell.alternative_id,
                criterion_id=cell.criterion_id,
            )
        )
    return found, []


def open_questions(
    project: Project,
    configuration: AnalysisConfiguration | None = None,
    dossier: EvidenceDossier | None = None,
    factor_record: dict[str, Any] | None = None,
    proposals: ExternalProposals | None = None,
    model_comparison: ModelComparison | None = None,
    proxy: dict[str, Any] | None = None,
) -> QuestionsResult:
    report = validate_structure(project)
    if not report.ok:
        raise ValidationFailed(report)
    tree = project.tree()
    alternative_names = {a.id: a.name for a in project.alternatives}
    entered = project.performance_index()
    cfg = (configuration or project.analysis).model_copy(deep=True)
    questions: list[Question] = []
    for alternative in project.alternatives:
        for criterion_id in tree.leaves():
            if (alternative.id, criterion_id) not in entered:
                name = tree.node(criterion_id).name
                questions.append(
                    Question(
                        group="blocking",
                        code="MISSING_MEASUREMENT",
                        question=f"What is {alternative.name}'s measurement for {name}?",
                        why="Methods requiring the missing measurement cannot evaluate the model.",
                        evidence="Obtain and review a measurement using the criterion's scale.",
                        alternative_id=alternative.id,
                        criterion_id=criterion_id,
                    )
                )
    if project.requirements:
        try:
            result = feasibility_service.check_feasibility(project)
        except ValidationFailed as exc:
            codes = ", ".join(i.code for i in exc.report.errors)
            questions.append(
                Question(
                    group="blocking",
                    code="INVALID_REQUIREMENTS",
                    question="Can the mandatory requirements be checked?",
                    why=f"The feasibility check cannot run: {codes}.",
                    evidence="Correct the requirements or their referenced criteria.",
                )
            )
        else:
            requirements = {r.id: r for r in result.requirements}
            for checked_alt in result.alternatives:
                for check in checked_alt.checks:
                    if check.status == "unknown":
                        requirement = requirements[check.requirement_id]
                        questions.append(
                            Question(
                                group="blocking",
                                code="UNKNOWN_REQUIREMENT",
                                question=f"Does {checked_alt.name} meet {requirement.name}?",
                                why=f"The mandatory requirement is unresolved: {check.reason}.",
                                evidence="Resolve the measurement and check the requirement.",
                                alternative_id=checked_alt.alternative_id,
                                criterion_id=requirement.criterion_id,
                                requirement_id=requirement.id,
                            )
                        )
    coverage = ["Missing measurements", "Unknown mandatory requirements"]
    limitations = [
        "Measurement sensitivity varies one cell with fixed anchors and other inputs fixed; "
        "it is not global robustness and does not propagate shared factors.",
        "One-way weight sensitivity holds other inputs fixed; it is not global robustness.",
        "An empty list does not establish decision robustness or evidence adequacy.",
    ]
    # MAVT sensitivity has its own configuration; another method's parameters never carry over.
    mavt_cfg = cfg.model_copy(update={"method": "mavt", "parameters": {}})
    if len(project.criteria) > 50:
        limitations.append("Weight sensitivity skipped: this prototype supports at most 50 nodes.")
        limitations.append("Method comparison skipped: this prototype supports at most 50 nodes.")
        limitations.append("Class sensitivity and SMAA-2 skipped above 50 nodes.")
    else:
        try:
            sensitivities = analysis_service.sensitivity_all(project, mavt_cfg, steps=2)
        except McdaError as exc:
            limitations.append(f"Weight sensitivity could not run: {exc}")
        else:
            coverage.append("One-way MAVT weight sensitivity")
            names = {a.id: a.name for a in project.alternatives}
            for sensitivity in sensitivities:
                for change in (
                    sensitivity.first_winner_change_down,
                    sensitivity.first_winner_change_up,
                ):
                    if change is None:
                        continue
                    questions.append(
                        Question(
                            group="decision_sensitive",
                            code="WEIGHT_WINNER_CHANGE",
                            question=f"How strongly should {sensitivity.node_name} be weighted?",
                            why=(
                                f"At local weight {change.weight!r}, MAVT first place can change "
                                f"between {names[change.from_winner]} "
                                f"and {names[change.to_winner]}."
                            ),
                            evidence="Review the swing-weight judgement and its rationale.",
                            alternative_id=change.to_winner,
                            criterion_id=sensitivity.node_id,
                        )
                    )
        comparison = comparison_service.compare_methods(project, cfg, ["mavt", "promethee2", "ahp"])
        available = [c for c in comparison.columns if c.status == "ok"]
        failed = [c.method for c in comparison.columns if c.status != "ok"]
        if failed:
            limitations.append("Methods that could not be compared: " + ", ".join(failed))
        if len(available) < 2:
            limitations.append("Fewer than two methods ran; leader disagreement was not assessed.")
        else:
            coverage.append("Leader comparison across methods that ran")
            if comparison.agreement.leaders_agree is False:
                details = "; ".join(
                    f"{c.method_label}: "
                    f"{', '.join(comparison.alternative_names[i] for i in c.leaders)}"
                    for c in available
                )
                questions.append(
                    Question(
                        group="decision_sensitive",
                        code="METHOD_LEADER_DISAGREEMENT",
                        question="Why do the methods identify different leaders?",
                        why=details,
                        evidence="Compare the methods' inputs, assumptions and explanations.",
                    )
                )
        limitations.append(
            "Agreement between methods sharing inputs is not independent validation."
        )
        if project.sorting is not None:
            try:
                sorting_cfg = mavt_cfg.model_copy(update={"method": "mavt_sorting"})
                class_sweeps = analysis_service.sensitivity_all(project, sorting_cfg, steps=2)
            except McdaError as exc:
                limitations.append(f"Class sensitivity could not run: {exc}")
            else:
                coverage.append("One-way class-boundary sensitivity")
                names = {a.id: a.name for a in project.alternatives}
                class_names = {c.id: c.name for c in project.sorting.classes}
                for sweep in class_sweeps:
                    assert isinstance(sweep, SortingSensitivityResult)
                    for row in sweep.class_changes:
                        for class_change in (row.first_change_down, row.first_change_up):
                            if class_change is None:
                                continue
                            questions.append(
                                Question(
                                    group="decision_sensitive",
                                    code="WEIGHT_CLASS_CHANGE",
                                    question=f"Could {names[row.alternative_id]}'s class change?",
                                    why=(
                                        f"Varying {sweep.node_name}'s local weight crosses a class "
                                        f"boundary at {class_change.weight!r}, between "
                                        f"{class_names[class_change.class_before]} and "
                                        f"{class_names[class_change.class_after]}. "
                                        "At the boundary the higher class applies."
                                    ),
                                    evidence="Review the swing weight and the class definitions.",
                                    alternative_id=row.alternative_id,
                                    criterion_id=sweep.node_id,
                                )
                            )
        else:
            limitations.append("Class sensitivity not assessed: no classes are stated.")
        if project.smaa is not None:
            smaa_cfg = cfg.model_copy(
                update={
                    "method": "smaa2",
                    "parameters": cfg.parameters if cfg.method == "smaa2" else {},
                }
            )
            try:
                smaa = analysis_service.evaluate_project(project, smaa_cfg)
            except McdaError as exc:
                limitations.append(f"SMAA-2 inputs to check could not run: {exc}")
            else:
                assert isinstance(smaa, SmaaResult)
                coverage.append("SMAA-2 inputs-to-check heuristic")
                limitations.append(smaa.inputs_to_check_label)
                if smaa.evaluation == "exact_enumeration":
                    limitations.append("Exact enumeration does not compute inputs to check.")
                cell_refs = {
                    f"smaa.cells[{c.alternative_id},{c.criterion_id}]": c
                    for c in project.smaa.cells
                }
                for item in smaa.inputs_to_check:
                    cell = cell_refs.get(item.path)
                    questions.append(
                        Question(
                            group="decision_sensitive",
                            code="SMAA_INPUT_TO_CHECK",
                            question=f"What supports {item.input}?",
                            why=(
                                f"{smaa.inputs_to_check_label}. Input: {item.path}. "
                                f"Rank-1 frequency difference: {item.difference!r}; "
                                f"{smaa.samples} draws, seed {smaa.seed}, {smaa.algorithm}."
                            ),
                            evidence="Review the stated uncertainty and its supporting evidence.",
                            alternative_id=cell.alternative_id if cell else None,
                            criterion_id=cell.criterion_id if cell else None,
                        )
                    )
        else:
            limitations.append("SMAA-2 inputs to check not assessed: no uncertainty is stated.")
    if dossier is None:
        limitations.append("Evidence quality not assessed: no dossier was supplied.")
        limitations.append("Measurement ranges not assessed: no dossier was supplied.")
    else:
        evidence_items, evidence_limits = evidence_questions(project, dossier)
        questions.extend(evidence_items)
        limitations.extend(evidence_limits)
        if not evidence_limits:
            coverage.append("Evidence dossier review and provenance gaps")
            range_checked = False
            for claim in dossier.claims:
                if claim.review is None or claim.review.status == "rejected":
                    continue
                if claim.uncertainty_lower is None or claim.uncertainty_upper is None:
                    continue
                accepted = (
                    claim.review.corrected_value
                    if claim.review.status == "corrected"
                    else claim.value
                )
                if accepted != claim.value:
                    limitations.append(
                        f"Range for {claim.id} belongs to the original claim, not its correction."
                    )
                    continue
                if entered.get((claim.alternative_id, claim.criterion_id)) != accepted:
                    limitations.append(
                        f"Range for {claim.id} was not assessed: its accepted value is not the "
                        "entered measurement."
                    )
                    continue
                try:
                    screen = assess_measurement_range(
                        project,
                        cfg,
                        claim.alternative_id,
                        claim.criterion_id,
                        claim.uncertainty_lower,
                        claim.uncertainty_upper,
                    )
                except McdaError as exc:
                    limitations.append(f"Range for {claim.id} was not assessed: {exc}")
                    continue
                range_checked = True
                if screen.rank_can_change or screen.class_can_change:
                    effects = []
                    if screen.rank_can_change:
                        effects.append("rank")
                    if screen.class_can_change:
                        effects.append("class")
                    questions.append(
                        Question(
                            group="decision_sensitive",
                            code="MEASUREMENT_RANGE_CHANGE",
                            question=(
                                f"How certain is {alternative_names[claim.alternative_id]}'s "
                                f"{tree.node(claim.criterion_id).name} (claim {claim.id})?"
                            ),
                            why=(
                                f"The stated range [{screen.lower!r}, {screen.upper!r}] can change "
                                f"the alternative's {' and '.join(effects)} with other inputs "
                                "fixed. Check the source and whether this range is justified."
                            ),
                            evidence=(
                                f"Check {claim.source.name}, {claim.source.reference}"
                                f"{', ' + claim.source.location if claim.source.location else ''}; "
                                "review the range and accepted measurement."
                            ),
                            alternative_id=claim.alternative_id,
                            criterion_id=claim.criterion_id,
                            measurement_range=screen,
                        )
                    )
            if range_checked:
                coverage.append("Single-measurement fixed-anchor range screening")
                limitations.append("A stated range is not treated as a probability distribution.")
            else:
                limitations.append("No eligible reviewed measurement ranges were screened.")
    if factor_record is not None:
        from mcda_studio.services import factor_analysis_service

        try:
            recorded = factor_analysis_service.verify(factor_record)
            questions.extend(
                factor_analysis_service.input_questions(
                    project, recorded.model, recorded.uncertainty
                )
            )
            coverage.append("reviewed fundamental-factor dependencies")
        except McdaError as exc:
            limitations.append(f"Factor questions unavailable: {exc}")
    if model_comparison is not None:
        from mcda_studio.services import model_comparison_service

        model_view = model_comparison_service.inspect(project, model_comparison)
        questions.extend(model_view.questions)
        coverage.append("explicit model comparison declarations")

    if proxy is not None:
        from mcda_studio.services import proxy_criterion_service

        try:
            inputs = proxy_criterion_service.ProxyInputs.model_validate_json(json.dumps(proxy))
            inputs.project = project
            inputs.configuration = cfg
            proxy_view = proxy_criterion_service.inspect(inputs)
            questions.extend(proxy_view.questions)
            questions.extend(
                Question(
                    group="evidence_quality",
                    code="PROXY_UNKNOWN_FACT",
                    question=f"What evidence can resolve the unknown model-card fact {name}?",
                    why="Explicitly reviewed unknowns remain disclosed limitations",
                    evidence="Optional disclosed proxy plan",
                )
                for name in proxy_view.unknown_facts
            )
            limitations.extend(proxy_view.limitations)
            coverage.append("Optional disclosed proxy card, licence and overlap reviews")
        except (McdaError, ValidationError) as exc:
            limitations.append(f"Proxy questions unavailable: {exc}")

    if proposals is not None:
        from mcda_studio.services import proposal_service

        intake = proposal_service.inspect(project, proposals)
        questions.extend(intake.questions)
        coverage.append("External proposal review, references and disagreements")
        limitations.extend(intake.limitations)
    return QuestionsResult(
        project_fingerprint=project.fingerprint(),
        configuration=cfg,
        questions=questions,
        coverage=coverage,
        limitations=limitations,
    )
