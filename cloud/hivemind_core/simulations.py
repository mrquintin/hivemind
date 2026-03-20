"""Simulation formula runner for Hivemind core.

Provides safe evaluation of mathematical formulas defined by admins.
Supports high-level mathematics via Python's math library.
"""
from __future__ import annotations

import ast
import math
from typing import Any

from hivemind_core.types import SimulationFormula


_ALLOWED_NODE_TYPES = {
    ast.Module,
    ast.Assign,
    ast.Expr,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.FloorDiv,
    ast.USub,
    ast.UAdd,
    ast.Call,
    ast.Constant,
    ast.Tuple,
    ast.List,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.IfExp,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Not,
}


def _validate_ast(tree: ast.AST) -> None:
    """Validate that the AST only contains allowed node types."""
    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODE_TYPES:
            raise ValueError(f"Unsupported expression: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only direct function calls are allowed")


def _allowed_env() -> dict[str, Any]:
    """Build the allowed environment for formula evaluation."""
    allowed = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
    allowed.update(
        {
            "min": min,
            "max": max,
            "abs": abs,
            "pow": pow,
            "round": round,
            "sum": sum,
            "len": len,
            "range": range,
            "float": float,
            "int": int,
            "bool": bool,
            "str": str,
        }
    )
    return allowed


def _evaluate(calculations: str, variables: dict[str, Any]) -> dict[str, Any]:
    """Safely evaluate calculations with the given variables."""
    tree = ast.parse(calculations, mode="exec")
    _validate_ast(tree)

    env = _allowed_env()
    locals_map = dict(variables)

    for node in tree.body:
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise ValueError("Only simple assignments are allowed")
            target = node.targets[0].id
            value = eval(
                compile(ast.Expression(node.value), "<expr>", "eval"), env, locals_map
            )
            locals_map[target] = value
        elif isinstance(node, ast.Expr):
            eval(compile(ast.Expression(node.value), "<expr>", "eval"), env, locals_map)
        else:
            raise ValueError("Only assignments or expressions are allowed")

    return locals_map


def run_simulation(
    formula: SimulationFormula, inputs: dict[str, Any]
) -> dict[str, Any]:
    """Run a simulation formula with the given inputs.

    Args:
        formula: The simulation formula definition
        inputs: Input values to use (overrides defaults)

    Returns:
        Dict with 'outputs' (declared outputs) and 'variables' (all computed values)
    """
    # Build initial variables from defaults
    defaults = {}
    for entry in formula.inputs:
        if isinstance(entry, dict):
            name = entry.get("name")
            default = entry.get("default_value")
        else:
            name = entry.name
            default = entry.default_value
        if name:
            defaults[name] = default

    # Merge with provided inputs
    variables = {**defaults, **inputs}
    variables = {k: v for k, v in variables.items() if v is not None}

    # Run the calculations
    variables = _evaluate(formula.calculations, variables)

    # Extract declared outputs
    outputs = {}
    for output in formula.outputs:
        if isinstance(output, dict):
            name = output.get("name")
        else:
            name = output.name
        if name:
            outputs[name] = variables.get(name)

    return {"outputs": outputs, "variables": variables}


def simulations_to_tools(formulas: list[SimulationFormula]) -> list[dict[str, Any]]:
    """Convert simulation formulas to Anthropic-compatible tool definitions."""
    tools: list[dict[str, Any]] = []
    for formula in formulas:
        if isinstance(formula, dict):
            name = formula.get("name", "sim")
            description = formula.get("description", "")
            inputs_list = formula.get("inputs", [])
            fid = formula.get("id", name)
        else:
            name = formula.name
            description = formula.description or ""
            inputs_list = formula.inputs
            fid = formula.id

        # Build JSON Schema properties from formula inputs
        properties: dict[str, Any] = {}
        required: list[str] = []
        for entry in inputs_list:
            entry_name = entry.get("name") if isinstance(entry, dict) else entry.name
            entry_desc = (entry.get("description") if isinstance(entry, dict) else entry.description) or ""
            entry_unit = (entry.get("unit") if isinstance(entry, dict) else entry.unit) or ""
            entry_default = entry.get("default_value") if isinstance(entry, dict) else entry.default_value
            if not entry_name:
                continue
            properties[entry_name] = {"type": "number", "description": f"{entry_desc} ({entry_unit})".strip()}
            if entry_default is None:
                required.append(entry_name)

        # Tool name must be alphanumeric/underscore, max 64 chars
        tool_name = f"sim_{fid}".replace("-", "_")[:64]

        tools.append({
            "name": tool_name,
            "description": f"Run simulation: {name}. {description}",
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        })
    return tools


def format_simulations_for_prompt(formulas: list[SimulationFormula]) -> str:
    """Format simulation formulas for inclusion in an agent's system prompt."""
    if not formulas:
        return "No simulations are attached to this agent."

    blocks = []
    for formula in formulas:
        # Handle both dataclass and dict-like structures
        if isinstance(formula, dict):
            name = formula.get("name", "Unknown")
            description = formula.get("description", "n/a")
            calculations = formula.get("calculations", "")
            inputs_list = formula.get("inputs", [])
            outputs_list = formula.get("outputs", [])
        else:
            name = formula.name
            description = formula.description or "n/a"
            calculations = formula.calculations
            inputs_list = formula.inputs
            outputs_list = formula.outputs

        inputs = ", ".join(
            f"{(entry.get('name') if isinstance(entry, dict) else entry.name)} "
            f"({(entry.get('unit') if isinstance(entry, dict) else entry.unit) or 'unitless'})"
            for entry in inputs_list
            if (entry.get("name") if isinstance(entry, dict) else entry.name)
        )
        outputs = ", ".join(
            f"{(entry.get('name') if isinstance(entry, dict) else entry.name)} "
            f"({(entry.get('unit') if isinstance(entry, dict) else entry.unit) or 'unitless'})"
            for entry in outputs_list
            if (entry.get("name") if isinstance(entry, dict) else entry.name)
        )

        blocks.append(
            "\n".join(
                [
                    f"FORMULA: {name}",
                    f"DESCRIPTION: {description}",
                    f"INPUTS: {inputs or 'n/a'}",
                    "CALCULATIONS:",
                    calculations,
                    f"OUTPUTS: {outputs or 'n/a'}",
                ]
            )
        )

    return "\n\n".join(blocks)
