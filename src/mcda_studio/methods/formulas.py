"""Bounded arithmetic interpreter. Never compiles or executes Python expressions."""

import ast
import math
from collections.abc import Callable
from dataclasses import dataclass


class FormulaError(ValueError):
    def __init__(
        self, code: str, message: str, dimensions: dict[str, dict[str, int]] | None = None
    ) -> None:
        self.code = code
        # The dimensions involved in a dimensional error, for explanations; not in the message.
        self.dimensions = dimensions or {}
        # The innermost formula whose evaluation failed, set by the dependency resolver.
        self.formula_id: str | None = None
        super().__init__(message)


@dataclass(frozen=True)
class Quantity:
    value: float
    dimension: dict[str, int]


def parse(expression: str) -> ast.Expression:
    if len(expression) > 2000:
        raise FormulaError("FORMULA_LIMIT", "expression exceeds 2000 characters")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise FormulaError("FORMULA_SYNTAX", "invalid arithmetic expression") from exc
    if sum(1 for _ in ast.walk(tree)) > 128:
        raise FormulaError("FORMULA_LIMIT", "expression exceeds 128 syntax nodes")
    return tree


def calculate(tree: ast.Expression, resolve: Callable[[str], Quantity]) -> Quantity:
    def visit(node: ast.AST) -> Quantity:
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (float, int))
            and not isinstance(node.value, bool)
        ):
            try:
                value = float(node.value)
            except OverflowError as exc:
                raise FormulaError("FORMULA_NONFINITE", "constant is too large") from exc
            result = Quantity(value, {})
        elif isinstance(node, ast.Name):
            result = resolve(node.id)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operand = visit(node.operand)
            result = Quantity(
                -operand.value if isinstance(node.op, ast.USub) else operand.value,
                operand.dimension,
            )
        elif isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
        ):
            a, b = visit(node.left), visit(node.right)
            dimension = dict(a.dimension)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                if a.dimension != b.dimension:
                    raise FormulaError(
                        "FORMULA_DIMENSION",
                        "addition/subtraction needs matching dimensions",
                        {"left": a.dimension, "right": b.dimension},
                    )
                value = a.value + b.value if isinstance(node.op, ast.Add) else a.value - b.value
            else:
                sign = -1 if isinstance(node.op, ast.Div) else 1
                for key, exponent in b.dimension.items():
                    dimension[key] = dimension.get(key, 0) + sign * exponent
                dimension = {key: exponent for key, exponent in dimension.items() if exponent}
                if any(abs(exponent) > 16 for exponent in dimension.values()):
                    raise FormulaError("FORMULA_DIMENSION_LIMIT", "dimension exponent exceeds 16")
                if isinstance(node.op, ast.Div) and b.value == 0:
                    raise FormulaError("FORMULA_ZERO_DIVISION", "division by zero")
                value = a.value / b.value if isinstance(node.op, ast.Div) else a.value * b.value
            result = Quantity(value, dimension)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"min", "max"}
            and not node.keywords
            and 2 <= len(node.args) <= 16
        ):
            args = [visit(arg) for arg in node.args]
            for arg in args:
                if arg.dimension != args[0].dimension:
                    raise FormulaError(
                        "FORMULA_DIMENSION",
                        "min/max needs matching dimensions",
                        {"left": args[0].dimension, "right": arg.dimension},
                    )
            operation = min if node.func.id == "min" else max
            result = Quantity(operation(arg.value for arg in args), args[0].dimension)
        else:
            raise FormulaError(
                "FORMULA_UNSUPPORTED", "only numbers, names, + - * / and min/max are supported"
            )
        if not math.isfinite(result.value):
            raise FormulaError("FORMULA_NONFINITE", "calculation produced a nonfinite value")
        return result

    try:
        return visit(tree.body)
    except RecursionError as exc:
        raise FormulaError(
            "FORMULA_LIMIT", "combined formula/dependency nesting is too deep"
        ) from exc
