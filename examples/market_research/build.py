"""Wholly invented generic model inputs, units, scope and separately reviewed uncertainty."""

from datetime import UTC, datetime

from mcda_studio.domain.criteria import LinearValueFunction
from mcda_studio.domain.derived import DerivedFormula, DerivedModel, SourceFactor
from mcda_studio.domain.evidence import Origin, Review, Source
from mcda_studio.domain.factor_uncertainty import FactorDistribution, FactorUncertaintyModel
from mcda_studio.domain.model_comparison import (
    EnclosureRange,
    ModelChecks,
    ModelComparison,
    ModelOutputSpec,
    ModelScope,
    QuantityCheck,
    SourceInterval,
    SourceRange,
)
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.domain.uncertainty import (
    DiscreteDistribution,
    TriangularDistribution,
    UniformDistribution,
)
from mcda_studio.services import derived_service as derived
from mcda_studio.services import model_checks_service as checks
from mcda_studio.services import model_comparison_service as comparisons
from mcda_studio.services import project_service as ps

TIME = datetime(2026, 11, 1, 12, tzinfo=UTC)
REVIEW = Review(
    status="accepted",
    reviewer="Illustrative reviewer",
    reviewed_at=TIME,
    note="Reviewed invented assumptions",
)
ORIGIN = Origin(kind="human", proposed_by="Illustrative modeller")


def inputs(discrete=False):
    project = ps.new_project("Two explicit formula models").model_copy(update={"id": "model_demo"})
    for id in ("a", "b"):
        project = ps.add_alternative(project, f"Option {id.upper()}", alt_id=id)
    project = ps.add_criterion(
        project,
        "Annual quantity",
        crit_id="annual",
        scale=Scale(type=ScaleType.RATIO, unit="money/year", lower=0, upper=2_000_000),
        value_function=LinearValueFunction(),
    )
    project = ps.set_performance(project, "a", "annual", 600000)
    project = ps.set_performance(project, "b", "annual", 480000)
    project = ps.set_judgement(project, "annual", 100)
    units = {
        "customer": {"customer": 1},
        "money/customer/year": {"money": 1, "customer": -1, "time": -1},
        "money/year": {"money": 1, "time": -1},
    }
    sources = []
    for id, value, unit, relationship in (
        ("customers", 10000, "customer", "independent"),
        ("adoption", 0.05, "1", "unknown"),
        ("price", 1200, "money/customer/year", "self_reported"),
        ("other_customers", 8000, "customer", "independent"),
        ("total", 100000000, "money/year", "unknown"),
        ("share", 0.01, "1", "unknown"),
    ):
        sources.append(
            SourceFactor(
                id=id,
                value=value,
                unit=unit,
                source=Source(
                    name=f"Invented {id}",
                    reference=f"local:invented-{id}",
                    date=TIME.date(),
                    description="Invented model input",
                    classification=relationship,
                ),
                origin=ORIGIN,
                review=REVIEW,
            )
        )
    model = DerivedModel(
        project_fingerprint=project.fingerprint(),
        units=units,
        sources=sources,
        formulas=[
            DerivedFormula(
                id="bottom_a",
                expression="customers * adoption * price",
                unit="money/year",
                origin=ORIGIN,
                review=REVIEW,
                alternative_id="a",
                criterion_id="annual",
            ),
            DerivedFormula(
                id="bottom_b",
                expression="other_customers * adoption * price",
                unit="money/year",
                origin=ORIGIN,
                review=REVIEW,
                alternative_id="b",
                criterion_id="annual",
            ),
            DerivedFormula(
                id="top_a",
                expression="total * share",
                unit="money/year",
                origin=ORIGIN,
                review=REVIEW,
            ),
        ],
    )
    digest = derived.preview(project, model).model_digest
    spec = FactorUncertaintyModel(
        project_fingerprint=project.fingerprint(),
        model_digest=digest,
        distributions=[
            FactorDistribution(
                factor_id="customers",
                distribution=DiscreteDistribution(
                    values=[8000, 10000, 12000], probabilities=[0.25, 0.5, 0.25]
                ),
                origin=ORIGIN,
                review=REVIEW,
            ),
            FactorDistribution(
                factor_id="adoption",
                distribution=DiscreteDistribution(
                    values=[0.04, 0.05, 0.06], probabilities=[0.25, 0.5, 0.25]
                )
                if discrete
                else UniformDistribution(lower=0.04, upper=0.06),
                origin=ORIGIN,
                review=REVIEW,
            ),
            FactorDistribution(
                factor_id="price",
                distribution=DiscreteDistribution(values=[1200], probabilities=[1])
                if discrete
                else TriangularDistribution(lower=1000, mode=1200, upper=1400),
                origin=ORIGIN,
                review=REVIEW,
            ),
        ],
    )
    declaration = ModelChecks(
        project_fingerprint=project.fingerprint(),
        model_digest=digest,
        origin=ORIGIN,
        review=REVIEW,
        digest="",
        checks=[
            QuantityCheck(
                id="adoption_fraction",
                quantity_kind="source",
                quantity_id="adoption",
                unit="1",
                lower=0,
                upper=1,
            ),
            QuantityCheck(
                id="positive_price",
                quantity_kind="source",
                quantity_id="price",
                unit="money/customer/year",
                lower=0,
            ),
            QuantityCheck(
                id="customer_count",
                quantity_kind="source",
                quantity_id="customers",
                unit="customer",
                lower=0,
            ),
            QuantityCheck(
                id="output_bounds",
                quantity_kind="formula",
                quantity_id="bottom_a",
                unit="money/year",
                lower=0,
                upper=2000000,
            ),
        ],
    )
    declaration.digest = checks.checks_digest(declaration)
    scope = ModelScope(
        population="Illustrative population",
        geography="Illustrative region",
        period="2026",
        currency_basis="Illustrative constant money",
        unit="money/year",
    )
    left = ModelOutputSpec(
        id="bottom",
        label="Bottom-up formula",
        model=model,
        formula_id="bottom_a",
        scope=scope,
        range=EnclosureRange(),
        uncertainty=spec,
        checks=declaration,
    )
    right = ModelOutputSpec(
        id="top",
        label="Top-down formula",
        model=model,
        formula_id="top_a",
        scope=scope,
        range=SourceRange(
            intervals=[
                SourceInterval(
                    factor_id="total",
                    unit="money/year",
                    lower=80000000,
                    upper=120000000,
                    origin=ORIGIN,
                    review=REVIEW,
                )
            ]
        ),
        checks=declaration,
    )
    comparison = ModelComparison(
        project_fingerprint=project.fingerprint(),
        label="Two invented estimates",
        left=left,
        right=right,
        origin=ORIGIN,
        review=REVIEW,
        digest="",
    )
    comparison.digest = comparisons.comparison_digest(comparison)
    return project, model, spec, declaration, comparison


def write_json(path, value):
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    data = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def build(destination=None, demo_destination=None):
    import hashlib
    import json
    from pathlib import Path

    from mcda_studio.domain.project import Project
    from mcda_studio.domain.starter_templates import StarterArtifact, StarterTemplate
    from mcda_studio.services import proposal_service
    from mcda_studio.services import starter_template_service as starters
    from mcda_studio.services.templates import from_template

    root = Path(__file__).resolve().parents[1]
    destination = Path(destination) if destination is not None else root / "starter_templates"
    project, model, uncertainty, declaration, comparison = inputs()
    from mcda_studio.domain.external_proposals import ExternalProposals

    old_workspace = ExternalProposals.model_validate_json(
        (root / "external_proposals/screening-workspace.json").read_text()
    )
    p = old_workspace.source_project.model_copy(deep=True)
    # The formula criterion is a deliberately separate leaf from classifier-proposed labels.
    p = ps.add_criterion(
        p,
        "Annual reachable quantity",
        crit_id="annual",
        scale=project.criteria[0].scale,
        value_function=project.criteria[0].value_function,
    )
    for alternative, value in (("a", 600000), ("b", 480000)):
        p = ps.set_performance(p, alternative, "annual", value)
    p = ps.set_judgement(p, "annual", 60)
    p.id = "venture_screening_starter"
    p.title = "Venture screening"
    p.description = "Wholly invented Option A/B proposal review and two market models. Illustrative, not investment advice."
    model.project_fingerprint = p.fingerprint()
    uncertainty.project_fingerprint = p.fingerprint()
    uncertainty.model_digest = derived._digest(model.model_dump(mode="json"))
    declaration.project_fingerprint = p.fingerprint()
    declaration.model_digest = uncertainty.model_digest
    declaration.digest = checks.checks_digest(declaration)
    for spec in (comparison.left, comparison.right):
        spec.model = model.model_copy(deep=True)
        spec.checks = declaration.model_copy(deep=True)
        if spec.uncertainty is not None:
            spec.uncertainty = uncertainty.model_copy(deep=True)
    comparison.project_fingerprint = p.fingerprint()
    comparison.digest = comparisons.comparison_digest(comparison)
    # Rebuild invented producer input/review, not an assertion about an earlier reviewed project.
    intake = old_workspace.intake.model_copy(deep=True)
    intake.project_fingerprint = p.fingerprint()
    if intake.human_dossier:
        intake.human_dossier.project_fingerprint = p.fingerprint()
    workspace = proposal_service.start(p, intake)
    for event in old_workspace.reviews:
        inspected = proposal_service.inspect(p, workspace)
        workspace = proposal_service.review(
            p, workspace, [event], inspected.review_digest, workspace.digest
        ).workspace
    ownership = DerivedModel(
        project_fingerprint=p.fingerprint(),
        units={"money": {"money": 1}},
        sources=[
            SourceFactor(
                id=id,
                value=value,
                unit=unit,
                source=Source(
                    name=f"Invented {id}",
                    reference=f"local:invented-{id}",
                    date=TIME.date(),
                    description="Illustrative simple primary round only; excludes option pools, convertibles, preferences, multiple rounds and contractual terms.",
                    classification="unknown",
                ),
                origin=ORIGIN,
                review=REVIEW,
            )
            for id, value, unit in (
                ("pre_money", 4000000, "money"),
                ("new_cash", 1000000, "money"),
                ("prior_share", 0.6, "1"),
            )
        ],
        formulas=[
            DerivedFormula(id=id, expression=expression, unit=unit, origin=ORIGIN, review=REVIEW)
            for id, expression, unit in (
                ("post_money", "pre_money + new_cash", "money"),
                ("new_share", "new_cash / post_money", "1"),
                ("diluted_share", "prior_share * pre_money / post_money", "1"),
            )
        ],
    )
    ownership_checks = ModelChecks(
        project_fingerprint=p.fingerprint(),
        model_digest=derived._digest(ownership.model_dump(mode="json")),
        checks=[
            QuantityCheck(
                id="positive_denominator",
                quantity_kind="formula",
                quantity_id="post_money",
                unit="money",
                lower=0,
                lower_inclusive=False,
            ),
            *[
                QuantityCheck(
                    id=id,
                    quantity_kind="source",
                    quantity_id=id,
                    unit=unit,
                    lower=0,
                    upper=1 if id == "prior_share" else None,
                )
                for id, unit in (
                    ("pre_money", "money"),
                    ("new_cash", "money"),
                    ("prior_share", "1"),
                )
            ],
            *[
                QuantityCheck(
                    id=id, quantity_kind="formula", quantity_id=id, unit="1", lower=0, upper=1
                )
                for id in ("new_share", "diluted_share")
            ],
        ],
        origin=ORIGIN,
        review=REVIEW,
        digest="",
    )
    ownership_checks.digest = checks.checks_digest(ownership_checks)
    definitions = [
        (
            "blank",
            "Blank",
            "Define your alternatives, criteria, measurements and swing judgements.",
            ["Create alternatives and criteria", "Enter measurements and swing ratings"],
            [
                (
                    "project",
                    ps.new_project("Blank").model_copy(update={"id": "blank_starter"}),
                    "project",
                    False,
                    None,
                )
            ],
        ),
    ]
    for name, title, tasks in (
        (
            "supplier_selection",
            "Supplier selection",
            [
                "Review cost, quality and delivery inputs",
                "Compare two preference profiles and a scenario",
            ],
        ),
        (
            "infrastructure_procurement",
            "Infrastructure procurement",
            [
                "Review procurement costs and service trade-offs",
                "Compare balanced and consent-led profiles and a scenario",
            ],
        ),
    ):
        raw = json.loads((root / name / "project.json").read_text())
        identities = {
            item["id"]: f"option_{chr(97 + i)}" for i, item in enumerate(raw["alternatives"])
        }

        def anonymize(value):
            if isinstance(value, dict):
                return {identities.get(k, k): anonymize(v) for k, v in value.items()}
            if isinstance(value, list):
                return [anonymize(v) for v in value]
            return identities.get(value, value) if isinstance(value, str) else value

        raw = anonymize(raw)
        for i, item in enumerate(raw["alternatives"]):
            item["name"] = f"Option {chr(65 + i)}"
            item["metadata"] = {}
        raw.update(
            id=name + "_starter",
            title=title,
            description="Wholly invented inputs for reviewing a decision workflow.",
            decision_maker="Illustrative analyst",
        )
        definitions.append(
            (
                name,
                title,
                "Illustrative alternatives, criteria, measurements, two profiles and one scenario.",
                tasks,
                [("project", Project.model_validate(raw), "project", False, None)],
            )
        )
    definitions.append(
        (
            "venture_screening",
            "Venture screening",
            "Review invented classifier proposals, explicit factor uncertainty, bottom-up and top-down models; choose one reviewed output.",
            [
                "Accept, correct or reject external proposals",
                "Inspect two labelled market model ranges and their disagreement",
                "Review factor assumptions and select one compatible model output",
                "Optionally inspect unattached simple-round arithmetic",
            ],
            [
                ("project", p, "project", False, None),
                ("market_model", model, "derived_model", False, None),
                ("market_uncertainty", uncertainty, "factor_uncertainty", False, "market_model"),
                ("market_checks", declaration, "model_checks", False, "market_model"),
                ("model_comparison", comparison, "model_comparison", False, None),
                ("external_proposals", workspace, "external_proposals", False, None),
                ("ownership_model", ownership, "derived_model", True, None),
                ("ownership_checks", ownership_checks, "model_checks", True, "ownership_model"),
                (
                    "model_output",
                    checks.run_output(p, comparison.left),
                    "model_output_run",
                    False,
                    None,
                ),
            ],
        )
    )
    for id, title, description, tasks, items in definitions:
        folder = destination / id
        artifacts = []
        for artifact_id, value, kind, optional, for_model in items:
            path = folder / (artifact_id + ".json")
            write_json(path, value)
            data = json.loads(path.read_text())
            version = data.get("schema_version", data.get("version", data.get("workspace_version")))
            artifacts.append(
                StarterArtifact(
                    id=artifact_id,
                    path=path.name,
                    kind=kind,
                    schema_version=version,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    optional=optional,
                    reset_policy="omit" if kind in starters.SNAPSHOTS else "draft",
                    for_model=for_model,
                    label=artifact_id.replace("_", " ").capitalize(),
                )
            )
        manifest = StarterTemplate(
            id=id,
            version="1",
            title=title,
            description=description,
            source_example="invented local starter fixtures",
            source_version="1",
            tasks=tasks,
            artifacts=artifacts,
            digest="",
        )
        manifest.digest = starters.template_digest(manifest)
        write_json(folder / "manifest.json", manifest)
    # Preserve the legacy structure-only creation contract as data, separately from the gallery.
    legacy = {
        id: {
            "description": from_template(id, "legacy").description,
            "criteria": from_template(id, "legacy").model_dump(mode="json")["criteria"],
        }
        for id in ("blank", "supplier-selection")
    }
    write_json(destination / "legacy.json", legacy)
    demo_destination = Path(demo_destination) if demo_destination is not None else Path(__file__).resolve().parent
    write_json(demo_destination / "comparison.json", comparison)
    write_json(demo_destination / "model-project.json", p)


if __name__ == "__main__":
    build()
