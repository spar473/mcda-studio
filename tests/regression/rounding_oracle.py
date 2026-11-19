"""Independent exact values and forward binary64 error bounds; no application imports.

Higham, Accuracy and Stability of Numerical Algorithms, 2nd ed., §2.2:
fl(a op b) = (a op b)(1 + delta), |delta| <= u = 2**-53.
For exact values x,y and absolute input errors e,f, addition/subtraction contribute
 e+f; multiplication contributes |x|f+|y|e+ef; division contributes
 (e+|x/y|f)/(|y|-f). Add u*(|exact result|+propagated error) for the
operation's rounding. All propagation uses Fraction arithmetic, not float estimates.
The denominator interval must exclude zero. Overflow and wholly subnormal nonzero
result bounds are refused: the relative-error model alone does not cover those cases.
"""

import ast
import math
import sys
from dataclasses import dataclass
from fractions import Fraction

U = Fraction(1, 2**53)
MIN_NORMAL = Fraction.from_float(sys.float_info.min)
MAX_FINITE = Fraction.from_float(sys.float_info.max)


@dataclass(frozen=True)
class Bounded:
    exact: Fraction
    error: Fraction

    @classmethod
    def input(cls, decimal):
        exact = Fraction(str(decimal))
        nearest = float(exact)
        if not math.isfinite(nearest) or (exact and abs(exact) < MIN_NORMAL):
            raise ValueError("input is outside the normal finite arithmetic model")
        error = Fraction() if Fraction.from_float(nearest) == exact else abs(exact) * U
        return cls(exact, error)

    @classmethod
    def operation(cls, exact, propagated):
        magnitude = abs(exact) + propagated
        if magnitude > MAX_FINITE or (magnitude and magnitude < MIN_NORMAL):
            raise ValueError("operation is outside the finite normal rounding model")
        return cls(exact, propagated + U * magnitude)

    def __add__(self, other):
        return self.operation(self.exact + other.exact, self.error + other.error)

    def __sub__(self, other):
        return self.operation(self.exact - other.exact, self.error + other.error)

    def __mul__(self, other):
        propagated = (
            abs(self.exact) * other.error + abs(other.exact) * self.error + self.error * other.error
        )
        return self.operation(self.exact * other.exact, propagated)

    def __truediv__(self, other):
        if abs(other.exact) <= other.error:
            raise ValueError("denominator interval contains zero")
        exact = self.exact / other.exact
        propagated = (self.error + abs(exact) * other.error) / (abs(other.exact) - other.error)
        return self.operation(exact, propagated)

    def __neg__(self):
        return Bounded(-self.exact, self.error)

    def contains(self, value):
        return math.isfinite(value) and abs(Fraction.from_float(value) - self.exact) <= self.error


def evaluate(expression, values):
    """Independently propagate exact values/errors in the declared expression-tree order."""
    inputs = {name: Bounded.input(value) for name, value in values.items()}

    def visit(node):
        if isinstance(node, ast.Name):
            return inputs[node.id]
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Bounded.input(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
            value = visit(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            operations = {
                ast.Add: Bounded.__add__,
                ast.Sub: Bounded.__sub__,
                ast.Mult: Bounded.__mul__,
                ast.Div: Bounded.__truediv__,
            }
            return operations[type(node.op)](left, right)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"min", "max"}
        ):
            values = [visit(argument) for argument in node.args]
            function = min if node.func.id == "min" else max
            # min/max is 1-Lipschitz in the maximum norm; choosing an operand adds no rounding.
            return Bounded(function(value.exact for value in values), max(v.error for v in values))
        raise ValueError("unsupported independent oracle expression")

    return visit(ast.parse(expression, mode="eval").body)
