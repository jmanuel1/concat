"""This module takes the transpiler/compiler output and executes it."""
import ast
import types
from typing import Dict, Optional


def _compile(filename: str, ast_: ast.Module) -> types.CodeType:
    return compile(ast_, filename, 'exec')


def _run(
    prog: types.CodeType,
    globals: Optional[Dict[str, object]] = None
) -> None:
    exec(prog, globals or {})


def execute(
    filename: str,
    ast: ast.Module,
    globals: Dict[str, object]
) -> None:
    _run(_compile(filename, ast), globals)
