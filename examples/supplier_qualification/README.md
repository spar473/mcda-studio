# Supplier qualification example

A value-based sorting variant of the [supplier selection example](../supplier_selection/README.md).
The same five synthetic suppliers are sorted into three ordered classes by their overall MAVT
value instead of only being ranked. It illustrates the method, not a recommendation about real
suppliers, and its boundaries are illustrative cut-offs.

Open this bundled example from **Projects → Examples**. Its saved method is *Value-based sorting
(MAVT)*, so Results shows the Classes view first, class bands on the ranking chart and a class
column in the ranking CSV; Sensitivity shows the exact weight at which each supplier first changes
class. The Classes tab edits the classes.

## Where every number comes from

- **Suppliers, measurements, criteria, value functions, swing ratings, the cost-focused profile and
  the linear defect-rate scenario** are supplier selection's, taken from its `build.py`. They are
  synthetic.
- **Logistics cost anchors** differ: here they are fixed at 1.0 to 6.0 NZD/unit, just outside the
  observed 1.1 to 5.9, where supplier selection derives them from the alternatives (local anchors).
  With local anchors, adding a supplier could move others between classes, so fixed anchors are
  recommended for sorting. Overall values move by at most 0.0036 as a result.
- **Classes**, best first: Qualified from 0.70, Conditional from 0.60, Not qualified below. A value
  within 1e-12 of a boundary goes to the higher class.
- **Audit sample:** one supplier sorted below Conditional, chosen by the SHA-256 of
  `"2026:<supplier id>"`, for manual review of possible false negatives.

## What it shows

| Context | Qualified | Conditional | Not qualified |
| --- | --- | --- | --- |
| Base | Apex 0.7383, Delta 0.7317 | Evergreen 0.6231 | Brightline 0.5943, Cobalt 0.4036 |
| Cost-focused profile | none (an empty class) | Apex 0.6755, Delta 0.6280, Evergreen 0.6081 | Brightline 0.5922, Cobalt 0.4645 |
| Linear defect-rate scenario | Apex 0.7415, Delta 0.7317 | Evergreen 0.6423, Brightline 0.6263 | Cobalt 0.4357 |

Brightline is a near miss at Base, 0.0057 below Conditional. The audit sample at Base is Cobalt.
The classes are checked against an independent plain-Python oracle in
`tests/regression/test_supplier_qualification.py` in the source distribution.

In a source checkout, regenerate with `python examples/supplier_qualification/build.py`.
