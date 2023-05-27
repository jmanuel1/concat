"""This module takes the transpiler/compiler output and executes it."""
import ast
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
import contextlib
import sys
import types
from typing import Callable, Dict, Iterator, List, Optional
import os


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

    def __getitem__(self, i):
        res = super().__getitem__(i)
        if isinstance(i, slice):
            s = LoggableStack(self._name + ' (copy)', self._should_log)
            s.extend(res)
            return s
        return res


def _compile(filename: str, ast_: ast.Module) -> types.CodeType:
    return compile(ast_, filename, 'exec')


def _run(
    prog: types.CodeType,
    import_resolution_start_directory: os.PathLike,
    globals: Optional[Dict[str, object]] = None,
    locals: Optional[Dict[str, object]] = None,
) -> None:
    globals = {} if globals is None else globals
    try:
        with _override_import_resolution_start_directory(
            import_resolution_start_directory
        ):
            exec(prog, globals, globals if locals is None else locals)
    except Exception as e:
        # TODO: throw away all of the traceback outside the code, but have an
        # option to keep the traceback.
        raise ConcatRuntimeError(globals['stack'], globals['stash']) from e


@contextlib.contextmanager
def _override_import_resolution_start_directory(
    import_resolution_start_directory: os.PathLike,
) -> Iterator[None]:
    # This is similar to how Python sets sys.path[0] when running just a file
    # (like `python blah.py`, not `python -m blah`). This should probably be
    # extended when module support is implemented.
    first_path, sys.path[0] = (
        sys.path[0],
        str(import_resolution_start_directory),
    )
    yield
    sys.path[0] = first_path


def _do_preamble(globals: Dict[str, object], should_log_stacks=False) -> None:
    """Add key-value pairs expected by Concat code to the passed-in mapping.

    This mutates the mapping, but anything already in the mapping is preserved.
    """

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
    globals.setdefault('concat', concat)

    globals.setdefault('to_int', concat.stdlib.pyinterop.to_int)
    globals.setdefault('to_bool', concat.stdlib.pyinterop.to_bool)
    globals.setdefault('to_complex', concat.stdlib.pyinterop.to_complex)
    globals.setdefault('len', concat.stdlib.pyinterop.len)
    globals.setdefault('getitem', concat.stdlib.pyinterop.getitem)
    globals.setdefault('to_float', concat.stdlib.pyinterop.to_float)
    globals.setdefault('decode_bytes', concat.stdlib.pyinterop.decode_bytes)
    globals.setdefault('to_tuple', concat.stdlib.pyinterop.to_tuple)
    globals.setdefault('to_bytes', concat.stdlib.pyinterop.to_bytes)
    globals.setdefault('to_list', concat.stdlib.pyinterop.to_list)
    globals.setdefault('to_bytearray', concat.stdlib.pyinterop.to_bytearray)
    globals.setdefault('to_set', concat.stdlib.pyinterop.to_set)
    globals.setdefault('add_to_set', concat.stdlib.pyinterop.add_to_set)
    globals.setdefault('to_frozenset', concat.stdlib.pyinterop.to_frozenset)
    globals.setdefault('to_dict', concat.stdlib.pyinterop.to_dict)
    globals.setdefault('user_defined_function', udf)
    globals.setdefault('method', concat.stdlib.pyinterop.method)
    globals.setdefault('with_async', concat.stdlib.pyinterop.with_async)
    globals.setdefault('for_async', concat.stdlib.pyinterop.for_async)
    globals.setdefault('coroutine', concat.stdlib.pyinterop.coroutine)
    globals.setdefault('math', concat.stdlib.pyinterop.math)
    globals.setdefault('import_module', concat.stdlib.pyinterop.import_module)
    globals.setdefault(
        'import_advanced', concat.stdlib.pyinterop.import_advanced
    )
    globals.setdefault('custom_class', concat.stdlib.pyinterop.custom_class)
    globals.setdefault('instance', concat.stdlib.pyinterop.instance)
    globals.setdefault('open', concat.stdlib.pyinterop.open)
    globals.setdefault('popen', concat.stdlib.pyinterop.popen)
    globals.setdefault('fdopen', concat.stdlib.pyinterop.fdopen)
    globals.setdefault('call', concat.stdlib.pyinterop.call)
    globals.setdefault('curry', concat.stdlib.compositional.curry)
    globals.setdefault('drop', concat.stdlib.shuffle_words.drop)
    globals.setdefault('drop_2', concat.stdlib.shuffle_words.drop_2)
    globals.setdefault('drop_3', concat.stdlib.shuffle_words.drop_3)
    globals.setdefault('nip', concat.stdlib.shuffle_words.nip)
    globals.setdefault('nip_2', concat.stdlib.shuffle_words.nip_2)
    globals.setdefault('dup', concat.stdlib.shuffle_words.dup)
    globals.setdefault('dup_2', concat.stdlib.shuffle_words.dup_2)
    globals.setdefault('swap', concat.stdlib.shuffle_words.swap)
    globals.setdefault('dup_3', concat.stdlib.shuffle_words.dup_3)
    globals.setdefault('over', concat.stdlib.shuffle_words.over)
    globals.setdefault('over_2', concat.stdlib.shuffle_words.over_2)
    globals.setdefault('pick', concat.stdlib.shuffle_words.pick)
    globals.setdefault('to_slice', concat.stdlib.pyinterop.to_slice)
    globals.setdefault('choose', concat.stdlib.execution.choose)
    globals.setdefault('if_then', concat.stdlib.execution.if_then)
    globals.setdefault('if_not', concat.stdlib.execution.if_not)
    globals.setdefault('case', concat.stdlib.execution.case)
    globals.setdefault('loop', concat.stdlib.execution.loop)

    globals.setdefault('True', lambda s, _: s.append(True))
    globals.setdefault('False', lambda s, _: s.append(False))
    globals.setdefault('None', lambda s, _: s.append(None))
    globals.setdefault('NotImplemented', lambda s, _: s.append(NotImplemented))
    globals.setdefault('Ellipsis', lambda s, _: s.append(...))
    globals.setdefault('...', lambda s, _: s.append(...))

    # Operators
    globals.setdefault('is', lambda s, _: s.append(s.pop() is s.pop()))
    globals.setdefault('>=', lambda s, _: s.append(s.pop(-2) >= s.pop()))
    globals.setdefault('<=', lambda s, _: s.append(s.pop(-2) <= s.pop()))
    globals.setdefault('<', lambda s, _: s.append(s.pop(-2) < s.pop()))
    globals.setdefault('-', lambda s, _: s.append(s.pop(-2) - s.pop()))
    globals.setdefault('+', lambda s, _: s.append(s.pop(-2) + s.pop()))


def execute(
    filename: str,
    ast: ast.Module,
    globals: Dict[str, object],
    locals: Optional[Dict[str, object]] = None,
    should_log_stacks=False,
    # By default, sys.path[0] is '' when executing a package.
    import_resolution_start_directory: os.PathLike = '',
) -> None:
    _do_preamble(globals, should_log_stacks)

    _run(
        _compile(filename, ast),
        import_resolution_start_directory,
        globals,
        locals,
    )
