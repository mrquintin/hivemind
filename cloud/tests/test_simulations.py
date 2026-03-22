"""Tests for hivemind_core.simulations."""

import pytest

from hivemind_core.simulations import format_simulations_for_prompt, run_simulation
from hivemind_core.types import SimulationFormula, SimulationIO


def test_run_simulation_basic():
    formula = SimulationFormula(
        id="f1",
        name="Revenue",
        inputs=[SimulationIO(name="price"), SimulationIO(name="quantity")],
        calculations="revenue = price * quantity",
        outputs=[SimulationIO(name="revenue")],
    )
    result = run_simulation(formula, {"price": 10, "quantity": 5})
    assert result["outputs"]["revenue"] == 50


def test_run_simulation_missing_input():
    formula = SimulationFormula(
        id="f1",
        name="Test",
        inputs=[SimulationIO(name="x")],
        calculations="y = x * 2",
        outputs=[SimulationIO(name="y")],
    )
    with pytest.raises(Exception):
        run_simulation(formula, {})


def test_format_simulations_for_prompt_empty():
    result = format_simulations_for_prompt([])
    assert "No simulation" in result or result == "No simulations available."


def test_format_simulations_for_prompt_with_formulas():
    formula = SimulationFormula(
        id="f1",
        name="Revenue Model",
        description="Basic revenue calc",
        inputs=[SimulationIO(name="price", unit="$")],
        calculations="revenue = price * 100",
        outputs=[SimulationIO(name="revenue", unit="$")],
    )
    result = format_simulations_for_prompt([formula])
    assert "Revenue Model" in result


def test_run_simulation_blocks_dangerous_builtin():
    formula = SimulationFormula(
        id="f2",
        name="Unsafe",
        calculations="x = __import__('math')",
        outputs=[SimulationIO(name="x")],
    )
    with pytest.raises(ValueError, match="Blocked function call"):
        run_simulation(formula, {})


def test_run_python_program_simulation():
    formula = SimulationFormula(
        id="f3",
        name="Python Program",
        simulation_type="python_program",
        code="outputs['sum'] = inputs.get('a', 0) + inputs.get('b', 0)",
        outputs=[SimulationIO(name="sum")],
    )
    result = run_simulation(formula, {"a": 2, "b": 3})
    assert result["outputs"]["sum"] == 5
