"""This module takes the transpiler/compiler output and executes it."""
import ast
import types
from typing import Dict, Optional, List, Callable
import concat.stdlib.compositional
import concat.stdlib.execution
import concat.stdlib.importlib
import concat.stdlib.shuffle_words
from concat.stdlib.pyinterop import py_call
import concat.stdlib.pyinterop.coroutine
import concat.stdlib.pyinterop.custom_class
import concat.stdlib.pyinterop.instance
import concat.stdlib.pyinterop.math
import concat.stdlib.pyinterop.method
import concat.stdlib.pyinterop.user_defined_function as udf


class ConcatRuntimeError(RuntimeError):
    def __init__(self, stack: List[object], stash: List[object]) -> None:
        super().__init__(stack, stash)
        self._stack = stack
        self._stash = stash

    def __str__(self) -> str:
        return 'Stack: {!r}, Stash: {!r}'.format(self._stack, self._stash)


class LoggableStack(List[object]):
    def __init__(self, name: str, should_log=False) -> None:
        self._name = name
        self._should_log = should_log

    def append(self, val: object) -> None:
        super().append(val)
        self._should_log and print(
            self._name, ':: after push (.append):', self
        )

    def pop(self, i: int = -1) -> object:
        r = super().pop(i)
        self._should_log and print(self._name, ':: after pop (.pop):', self)
        return r


def _compile(filename: str, ast_: ast.Module) -> types.CodeType:
    return compile(ast_, filename, 'exec')


def _run(
    prog: types.CodeType,
    globals: Optional[Dict[str, object]] = None,
    locals: Optional[Dict[str, object]] = None,
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


def _do_preamble(
    globals: Dict[str, object], should_log_stacks=False, interactive=False
) -> None:
    """Add key-value pairs expected by Concat code to the passed-in mapping.

    This mutates the mapping, but anything already in the mapping is preserved.
    The dict is not mutated if interactive is True and the dict has a truthy
    '@@level-1-interactive' key. The dict is not mutated if interactive is True
    and the dict has a truthy '@@level-2-interactive' key."""

    if interactive and globals.get('@@level-1-interactive', False):
        return
    if interactive:
        globals['@@level-1-interactive'] = True

    if interactive and globals.get('@@level-2-interactive', False):
        return
    if interactive:
        globals['@@level-2-interactive'] = True

    globals.setdefault('concat', concat)

    globals.setdefault('py_call', py_call)

    globals.setdefault('stack', LoggableStack('stack', should_log_stacks))
    globals.setdefault('stash', LoggableStack('stash', should_log_stacks))

    def push(val: object) -> Callable[[List[object], List[object]], None]:
        def push_func(stack: List[object], _: List[object]):
            stack.append(val)

        return push_func

    globals.setdefault('push', push)

    # needed by generated code to work
    globals['concat'] = concat

    globals['to_int'] = concat.stdlib.pyinterop.to_int
    globals['to_bool'] = concat.stdlib.pyinterop.to_bool
    globals['to_complex'] = concat.stdlib.pyinterop.to_complex
    globals['len'] = concat.stdlib.pyinterop.len
    globals['getitem'] = concat.stdlib.pyinterop.getitem
    globals['to_float'] = concat.stdlib.pyinterop.to_float
    globals['decode_bytes'] = concat.stdlib.pyinterop.decode_bytes
    globals['to_tuple'] = concat.stdlib.pyinterop.to_tuple
    globals['to_bytes'] = concat.stdlib.pyinterop.to_bytes
    globals['to_list'] = concat.stdlib.pyinterop.to_list
    globals['to_bytearray'] = concat.stdlib.pyinterop.to_bytearray
    globals['to_set'] = concat.stdlib.pyinterop.to_set
    globals['add_to_set'] = concat.stdlib.pyinterop.add_to_set
    globals['to_frozenset'] = concat.stdlib.pyinterop.to_frozenset
    globals['to_dict'] = concat.stdlib.pyinterop.to_dict
    globals['user_defined_function'] = udf
    globals['method'] = concat.stdlib.pyinterop.method
    globals['with_async'] = concat.stdlib.pyinterop.with_async
    globals['for_async'] = concat.stdlib.pyinterop.for_async
    globals['coroutine'] = concat.stdlib.pyinterop.coroutine
    globals['math'] = concat.stdlib.pyinterop.math
    globals['import_module'] = concat.stdlib.pyinterop.import_module
    globals['import_advanced'] = concat.stdlib.pyinterop.import_advanced
    globals['custom_class'] = concat.stdlib.pyinterop.custom_class
    globals['instance'] = concat.stdlib.pyinterop.instance
    globals['open'] = concat.stdlib.pyinterop.open
    globals['popen'] = concat.stdlib.pyinterop.popen
    globals['fdopen'] = concat.stdlib.pyinterop.fdopen
    globals['call'] = concat.stdlib.pyinterop.call
    globals['curry'] = concat.stdlib.compositional.curry
    globals['drop'] = concat.stdlib.shuffle_words.drop
    globals['drop_2'] = concat.stdlib.shuffle_words.drop_2
    globals['drop_3'] = concat.stdlib.shuffle_words.drop_3
    globals['nip'] = concat.stdlib.shuffle_words.nip
    globals['nip_2'] = concat.stdlib.shuffle_words.nip_2
    globals['dup'] = concat.stdlib.shuffle_words.dup
    globals['dup_2'] = concat.stdlib.shuffle_words.dup_2
    globals['swap'] = concat.stdlib.shuffle_words.swap
    globals['dup_3'] = concat.stdlib.shuffle_words.dup_3
    globals['over'] = concat.stdlib.shuffle_words.over
    globals['over_2'] = concat.stdlib.shuffle_words.over_2
    globals['pick'] = concat.stdlib.shuffle_words.pick
    globals['to_slice'] = concat.stdlib.pyinterop.to_slice
    globals['choose'] = concat.stdlib.execution.choose
    globals['if_then'] = concat.stdlib.execution.if_then
    globals['if_not'] = concat.stdlib.execution.if_not
    globals['case'] = concat.stdlib.execution.case
    globals['loop'] = concat.stdlib.execution.loop

    globals['True'] = lambda s, _: s.append(True)
    globals['False'] = lambda s, _: s.append(False)


def execute(
    filename: str,
    ast: ast.Module,
    globals: Dict[str, object],
    interactive=False,
    locals: Optional[Dict[str, object]] = None,
    should_log_stacks=False,
) -> None:
    _do_preamble(globals, should_log_stacks)

    _run(_compile(filename, ast), globals, locals)
