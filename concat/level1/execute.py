"""This module takes the transpiler/compiler output and executes it."""
import concat.level0.execute
import concat.level1.stdlib.pyinterop
from typing import Dict
import ast


def _do_preamble(globals: Dict[str, object]) -> None:
    globals['to_int'] = concat.level1.stdlib.pyinterop.to_int


def execute(
    filename: str,
    ast: ast.Module,
    globals: Dict[str, object]
) -> None:
    _do_preamble(globals)
    concat.level0.execute.execute(filename, ast, globals)
