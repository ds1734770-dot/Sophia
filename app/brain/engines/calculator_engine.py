import ast
import operator
import re


class UnsafeExpression(ValueError):
    pass


_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

MAX_EXPONENT = 1000
MAX_ABS_VALUE = 10 ** 300


def safe_eval(expression):
    """
    Evaluate an arithmetic expression without eval().

    Supports numbers, + - * / // % **, unary signs and parentheses.
    Exponents and results are capped so input like 9**9**9 cannot
    freeze the program.
    """

    tree = ast.parse(expression.strip(), mode="eval")

    def walk(node):

        if isinstance(node, ast.Expression):
            return walk(node.body)

        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value

        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](walk(node.operand))

        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:

            left = walk(node.left)
            right = walk(node.right)

            if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
                raise UnsafeExpression("exponent too large")

            result = _BINARY[type(node.op)](left, right)

            if abs(result) > MAX_ABS_VALUE:
                raise UnsafeExpression("result too large")

            return result

        raise UnsafeExpression("unsupported expression")

    return walk(tree)


class CalculatorEngine:

    def execute(self, command, context, offline=False):

        command = command.strip()

        # Plain arithmetic only, and it must contain an operator
        # ("2024" alone is a normal message, not a sum).
        if (
            re.fullmatch(r"[0-9+\-*/%(). ]+", command)
            and re.search(r"[+\-*/%]", command)
        ):

            try:
                result = safe_eval(command)

            except ZeroDivisionError:
                return {
                    "handled": True,
                    "response": "I can't divide by zero."
                }

            except (UnsafeExpression, SyntaxError, ValueError, OverflowError):
                return {
                    "handled": False,
                    "response": None
                }

            if isinstance(result, float) and result.is_integer():
                result = int(result)

            return {
                "handled": True,
                "response": str(result)
            }

        return {
            "handled": False,
            "response": None
        }
