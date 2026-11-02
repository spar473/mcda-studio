"""Independent rational answers for the two synthetic demos; no application imports."""

from fractions import Fraction


def answers(name: str, model: dict) -> dict[str, Fraction]:
    values = {}
    for source in model["sources"]:
        review = source["review"]
        assert review["status"] in {"accepted", "corrected"}
        value = review["corrected_value"] if review["status"] == "corrected" else source["value"]
        values[source["id"]] = Fraction(str(value))
    if name == "venture":
        return {
            f"market_{alt}": values["addressable_customers"]
            * values[f"adoption_{alt}"]
            * values[f"annual_price_{alt}"]
            for alt in ("a", "b")
        }
    assert name == "supplier"
    count = values["annual_units"] * values["years"]
    # Independent cash-flow formulation: initial setup plus annual cash flows over years.
    return {
        "purchase_volume": count,
        **{
            f"tco_{alt}": values[f"setup_{alt}"]
            + values["years"]
            * (values["annual_units"] * values[f"price_{alt}"] + values[f"maintenance_{alt}"])
            for alt in ("a", "b")
        },
    }
