import threading

import pytest

from app.brain.engines.calculator_engine import (
    CalculatorEngine,
    UnsafeExpression,
    safe_eval,
)
from app.tools.calculator_tool import CalculatorTool

engine = CalculatorEngine()


@pytest.mark.parametrize(
    "text, expected",
    [
        ("12*(5+8)", "156"),
        ("2**10", "1024"),
        ("10/4", "2.5"),
        ("10/5", "2"),
        ("7 % 3", "1"),
        ("-3 + 5", "2"),
    ],
)
def test_arithmetic(text, expected):

    result = engine.execute(text, None)

    assert result["handled"]
    assert result["response"] == expected


@pytest.mark.parametrize("text", ["2024", "hello", "what is 2+2", "__import__('os')"])
def test_not_arithmetic(text):

    assert not engine.execute(text, None)["handled"]


def test_divide_by_zero():

    result = engine.execute("1/0", None)

    assert result["handled"]
    assert "zero" in result["response"]


def test_exponent_bomb_returns_quickly():

    done = {}

    def run():
        done["result"] = engine.execute("9**9**9**9", None)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(2)

    assert "result" in done, "calculator hung on a huge exponent"
    assert not done["result"]["handled"]


def test_safe_eval_rejects_code():

    for bad in ["__import__('os').system('x')", "open('f')", "[1]", "a+1"]:
        with pytest.raises((UnsafeExpression, SyntaxError, ValueError)):
            safe_eval(bad)


def test_tool_uses_safe_eval():

    assert CalculatorTool().run(expression="2+3") == 5
    assert "Error" in str(CalculatorTool().run(expression="__import__('os')"))
