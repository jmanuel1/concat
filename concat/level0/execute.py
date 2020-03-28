"""This module takes the transpiler/compiler output and executes it."""
import ast
import types
from typing import Dict, Optional, List, Callable
import concat.level0.stdlib.importlib
from concat.level0.stdlib.pyinterop import py_call


class ConcatRuntimeError(RuntimeError):
    def __init__(self):
        super().__init__()
        # self.concat_traceback = traceback


def _compile(filename: str, ast_: ast.Module) -> types.CodeType:
    return compile(ast_, filename, 'exec')


def _run(
    prog: types.CodeType,
    globals: Optional[Dict[str, object]] = None,
    locals: Optional[Dict[str, object]] = None
) -> None:
    globals = {} if globals is None else globals
    try:
        exec(prog, globals, globals if locals is None else locals)
    except Exception as e:
        # throw away all of the traceback outside the code
        # traceback = e.__traceback__.tb_next
        raise ConcatRuntimeError from e


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
    interactive=False,
    locals: Optional[Dict[str, object]] = None
) -> None:
    _do_preamble(globals, interactive)

    _run(_compile(filename, ast), globals, locals)
