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
