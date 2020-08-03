"""This module takes the transpiler/compiler output and executes it."""
import ast
import types
from typing import Dict, Optional, List, Callable
import concat.level0.stdlib.importlib
from concat.level0.stdlib.pyinterop import py_call


class ConcatRuntimeError(RuntimeError):
    def __init__(self, stack: List[object], stash: List[object]) -> None:
        super().__init__(stack, stash)
        self._stack = stack
        self._stash = stash

    def __str__(self) -> str:
        return 'Stack: {!r}, Stash: {!r}'.format(self._stack, self._stash)


def _compile(filename: str, ast_: ast.Module) -> types.CodeType:
    return compile(ast_, filename, 'exec')


def _run(
    prog: types.CodeType,
    globals: Optional[Dict[str, object]] = None,
    locals: Optional[Dict[str, object]] = None
) -> None:
    globals = {} if globals is None else globals
    try:
        # FIXME: Imports should be resolved from the location of the source
        # file.
        exec(prog, globals, globals if locals is None else locals)
    except Exception as e:
        # throw away all of the traceback outside the code
        # traceback = e.__traceback__.tb_next
        raise ConcatRuntimeError(globals['stack'], globals['stash']) from e


def _do_preamble(globals: Dict[str, object]) -> None:
    """Add key-value pairs expected by Concat code to the passed-in mapping.

    This mutates the mapping, but anything already in the mapping is preserved."""

    globals.setdefault('concat', concat)

    globals.setdefault('py_call', py_call)

    globals.setdefault('stack', [])
    globals.setdefault('stash', [])

    def push(val: object) -> Callable[[List[object], List[object]], None]:
        def push_func(stack: List[object], _: List[object]):
            stack.append(val)
        return push_func
    globals.setdefault('push', push)


def execute(
    filename: str,
    ast: ast.Module,
    globals: Dict[str, object],
    interactive=False,
    locals: Optional[Dict[str, object]] = None
) -> None:
    _do_preamble(globals)

    _run(_compile(filename, ast), globals, locals)
