# Supplier selection example

A synthetic five-alternative procurement decision with eight leaf criteria, mixed tree depths,
and all supported scale/value-function kinds. It includes a cost-focused preference profile and
a linear defect-rate scenario. It illustrates modelling choices, not recommendations about real
suppliers.

Open this bundled example from **Projects → Examples**, then inspect its tree, measurements,
weights, results and sensitivity. The numerical fixture is checked against an independent oracle
in `tests/regression/test_supplier_selection.py` in the source distribution.

In a source checkout, regenerate with `python examples/supplier_selection/build.py`.
