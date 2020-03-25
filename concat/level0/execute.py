"""This module takes the transpiler/compiler output and executes it."""
import ast
import types
from typing import Dict, Optional, List, Callable
import concat.level0.stdlib.importlib
from concat.level0.stdlib.pyinterop import py_call


def _compile(filename: str, ast_: ast.Module) -> types.CodeType:
    return compile(ast_, filename, 'exec')


def _run(
    prog: types.CodeType,
    globals: Optional[Dict[str, object]] = None
) -> None:
    exec(prog, {} if globals is None else globals)


def _do_preamble(globals: Dict[str, object], interactive=False) -> None:
    """Add key-value pairs expected by Concat code to the passed-in mapping.

    This mutates the mapping, unless noth interactive and
    globals['@@level-0-interactive'] are true."""
    if interactive and globals.get('@@level-0-interactive', False):
        return
    if interactive:
        globals['@@level-0-interactive'] = True

    globals['concat'] = concat

    globals['py_call'] = py_call

    globals['stack'], globals['stash'] = [], []

    def push(val: object) -> Callable[[List[object], List[object]], None]:
        def push_func(stack: List[object], _: List[object]):
            stack.append(val)
        return push_func
    globals['push'] = push


def execute(
    filename: str,
    ast: ast.Module,
    globals: Dict[str, object],
    interactive=False
) -> None:
    _do_preamble(globals, interactive)

    _run(_compile(filename, ast), globals)
