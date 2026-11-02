"""Build two entirely synthetic models with the same domain-neutral calculation service."""

from datetime import UTC, date, datetime
from pathlib import Path

from mcda_studio.domain.criteria import Direction, LinearValueFunction
from mcda_studio.domain.derived import DerivedFormula, DerivedModel, SourceFactor
from mcda_studio.domain.evidence import Origin, Review, Source
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import to_json_text

HERE = Path(__file__).resolve().parent
ORIGIN = Origin(kind="human", proposed_by="Synthetic example author")
REVIEW = Review(
    status="accepted",
    reviewer="Synthetic example reviewer",
    reviewed_at=datetime(2026, 10, 31, tzinfo=UTC),
)
SOURCE = Source(
    name="Synthetic assumption",
    reference="local:illustrative-example",
    date=date(2026, 10, 31),
    description="Invented data for testing, not market evidence",
)


def build(name, title, criterion, unit, upper, direction, units, factors, expressions):
    p = ps.new_project(title).model_copy(update={"id": f"derived-{name}"})
    for alt in ("a", "b"):
        p = ps.add_alternative(p, f"Option {alt.upper()}", alt_id=alt)
    p = ps.add_criterion(
        p,
        criterion,
        crit_id="result",
        scale=Scale(type=ScaleType.RATIO, lower=0, upper=upper, unit=unit),
        value_function=LinearValueFunction(direction=direction),
    )
    # A draft may lack measurements; the preview proposes them without editing it.
    model = DerivedModel(
        project_fingerprint=p.fingerprint(),
        units=units,
        sources=[
            SourceFactor(id=key, value=value, unit=u, source=SOURCE, origin=ORIGIN, review=REVIEW)
            for key, value, u in factors
        ],
        formulas=[
            DerivedFormula(
                id=key,
                expression=expr,
                unit=u,
                alternative_id=alt,
                criterion_id="result" if alt else None,
                origin=ORIGIN,
                review=REVIEW,
            )
            for key, expr, u, alt in expressions
        ],
    )
    (HERE / f"{name}-project.json").write_text(to_json_text(p), encoding="utf-8")
    (HERE / f"{name}-model.json").write_text(to_json_text(model), encoding="utf-8")


if __name__ == "__main__":
    build(
        "venture",
        "Illustrative bottom-up market sizing",
        "Annual addressable revenue",
        "NZD/year",
        1_000_000,
        Direction.INCREASING,
        {
            "customers": {"customer": 1},
            "NZD/customer/year": {"NZD": 1, "customer": -1, "year": -1},
            "NZD/year": {"NZD": 1, "year": -1},
        },
        [
            ("addressable_customers", 10_000, "customers"),
            ("adoption_a", 0.05, "1"),
            ("adoption_b", 0.08, "1"),
            ("annual_price_a", 1200, "NZD/customer/year"),
            ("annual_price_b", 800, "NZD/customer/year"),
        ],
        [
            ("market_a", "addressable_customers * adoption_a * annual_price_a", "NZD/year", "a"),
            ("market_b", "addressable_customers * adoption_b * annual_price_b", "NZD/year", "b"),
        ],
    )
    build(
        "supplier",
        "Illustrative supplier total cost",
        "Three-year total cost of ownership",
        "NZD",
        250_000,
        Direction.DECREASING,
        {
            "NZD": {"NZD": 1},
            "years": {"year": 1},
            "items/year": {"item": 1, "year": -1},
            "items": {"item": 1},
            "NZD/item": {"NZD": 1, "item": -1},
            "NZD/year": {"NZD": 1, "year": -1},
        },
        [
            ("annual_units", 1000, "items/year"),
            ("years", 3, "years"),
            ("price_a", 40, "NZD/item"),
            ("price_b", 45, "NZD/item"),
            ("maintenance_a", 10_000, "NZD/year"),
            ("maintenance_b", 8000, "NZD/year"),
            ("setup_a", 5000, "NZD"),
            ("setup_b", 2000, "NZD"),
        ],
        [
            ("purchase_volume", "annual_units * years", "items", None),
            ("tco_a", "setup_a + purchase_volume * price_a + years * maintenance_a", "NZD", "a"),
            ("tco_b", "setup_b + purchase_volume * price_b + years * maintenance_b", "NZD", "b"),
        ],
    )
