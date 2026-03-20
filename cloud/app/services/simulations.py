from __future__ import annotations

import ast
import json
import math
import subprocess
import tempfile
from typing import Any

from app.models.simulation_formula import SimulationFormula

PYTHON_SANDBOX_TIMEOUT = 10


def _run_python_program(code: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Run Python program in subprocess. Contract: script reads JSON from stdin (inputs), must set 'outputs' dict and we print it as JSON."""
    input_json = json.dumps(inputs)
    wrapper = (
        "import json,sys\n"
        "inputs = json.load(sys.stdin)\n"
        "outputs = {}\n"
        f"{code}\n"
        "print(json.dumps(outputs))"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(wrapper)
        tmp = f.name
    try:
        import os
        proc = subprocess.run(
            ["python3", tmp],
            input=input_json,
            capture_output=True,
            text=True,
            timeout=PYTHON_SANDBOX_TIMEOUT,
            env={k: v for k, v in os.environ.items() if k in ("PATH", "HOME")},
            cwd=os.path.abspath(os.path.dirname(tmp)),
        )
    except subprocess.TimeoutExpired:
        raise ValueError("Python simulation timed out")
    finally:
        import os
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if proc.returncode != 0:
        raise ValueError(f"Python simulation failed: {proc.stderr or proc.stdout}")
    out = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return {"outputs": out, "variables": {**inputs, **out}}


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
    ast.USub,
    ast.UAdd,
    ast.Call,
    ast.Constant,
    ast.Tuple,
    ast.List,
}


def _validate_ast(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODE_TYPES:
            raise ValueError(f"Unsupported expression: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only direct function calls are allowed")


def _allowed_env() -> dict[str, Any]:
    allowed = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
    allowed.update({"min": min, "max": max, "abs": abs, "pow": pow, "round": round})
    return allowed


def _evaluate(calculations: str, variables: dict[str, Any]) -> dict[str, Any]:
    tree = ast.parse(calculations, mode="exec")
    _validate_ast(tree)

    env = _allowed_env()
    locals_map = dict(variables)

    for node in tree.body:
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise ValueError("Only simple assignments are allowed")
            target = node.targets[0].id
            value = eval(compile(ast.Expression(node.value), "<expr>", "eval"), env, locals_map)
            locals_map[target] = value
        elif isinstance(node, ast.Expr):
            eval(compile(ast.Expression(node.value), "<expr>", "eval"), env, locals_map)
        else:
            raise ValueError("Only assignments or expressions are allowed")

    return locals_map


def run_simulation(formula: SimulationFormula, inputs: dict[str, Any]) -> dict[str, Any]:
    sim_type = getattr(formula, "simulation_type", None) or "formula"
    if sim_type == "python_program" and getattr(formula, "code", None):
        return _run_python_program(formula.code, inputs)

    defaults = {
        entry.get("name"): entry.get("default_value")
        for entry in formula.inputs
        if entry.get("name")
    }
    variables = {**defaults, **inputs}
    variables = {k: v for k, v in variables.items() if v is not None}

    variables = _evaluate(formula.calculations or "", variables)

    outputs = {}
    for output in formula.outputs:
        name = output.get("name")
        if not name:
            continue
        outputs[name] = variables.get(name)

    return {"outputs": outputs, "variables": variables}
