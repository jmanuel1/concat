"""This module takes the transpiler/compiler output and executes it."""
import concat.level0.execute
import concat.level1.stdlib.pyinterop
import concat.level1.stdlib.pyinterop.user_defined_function as udf
import concat.level1.stdlib.pyinterop.method
import concat.level1.stdlib.pyinterop.coroutine
import concat.level1.stdlib.pyinterop.math
import concat.level1.stdlib.pyinterop.custom_class
import concat.level1.stdlib.pyinterop.instance
import concat.level1.stdlib.compositional
import concat.level1.stdlib.shuffle_words
import concat.level1.stdlib.execution
import concat.level1.stdlib.types
from typing import Dict, Optional
import ast


def _do_preamble(globals: Dict[str, object], interactive=False) -> None:
    """Run the level 1 preamble, which adds objects to the given dictionary.

    The dict is not mutated if interactive is True and the dict has a truthy
    '@@level-1-interactive' key."""
    if interactive and globals.get('@@level-1-interactive', False):
        return
    if interactive:
        globals['@@level-1-interactive'] = True

    # needed by generated code to work
    globals['concat'] = concat

    globals['to_int'] = concat.level1.stdlib.pyinterop.to_int
    globals['to_bool'] = concat.level1.stdlib.pyinterop.to_bool
    globals['to_complex'] = concat.level1.stdlib.pyinterop.to_complex
    globals['len'] = concat.level1.stdlib.pyinterop.len
    globals['getitem'] = concat.level1.stdlib.pyinterop.getitem
    globals['to_float'] = concat.level1.stdlib.pyinterop.to_float
    globals['decode_bytes'] = concat.level1.stdlib.pyinterop.decode_bytes
    globals['to_tuple'] = concat.level1.stdlib.pyinterop.to_tuple
    globals['to_bytes'] = concat.level1.stdlib.pyinterop.to_bytes
    globals['to_list'] = concat.level1.stdlib.pyinterop.to_list
    globals['to_bytearray'] = concat.level1.stdlib.pyinterop.to_bytearray
    globals['to_set'] = concat.level1.stdlib.pyinterop.to_set
    globals['add_to_set'] = concat.level1.stdlib.pyinterop.add_to_set
    globals['to_frozenset'] = concat.level1.stdlib.pyinterop.to_frozenset
    globals['to_dict'] = concat.level1.stdlib.pyinterop.to_dict
    globals['user_defined_function'] = udf
    globals['method'] = concat.level1.stdlib.pyinterop.method
    globals['with_async'] = concat.level1.stdlib.pyinterop.with_async
    globals['for_async'] = concat.level1.stdlib.pyinterop.for_async
    globals['coroutine'] = concat.level1.stdlib.pyinterop.coroutine
    globals['math'] = concat.level1.stdlib.pyinterop.math
    globals['import_module'] = concat.level1.stdlib.pyinterop.import_module
    globals['import_advanced'] = concat.level1.stdlib.pyinterop.import_advanced
    globals['custom_class'] = concat.level1.stdlib.pyinterop.custom_class
    globals['instance'] = concat.level1.stdlib.pyinterop.instance
    globals['open'] = concat.level1.stdlib.pyinterop.open
    globals['popen'] = concat.level1.stdlib.pyinterop.popen
    globals['fdopen'] = concat.level1.stdlib.pyinterop.fdopen
    globals['call'] = concat.level1.stdlib.pyinterop.call
    globals['curry'] = concat.level1.stdlib.compositional.curry
    globals['drop'] = concat.level1.stdlib.shuffle_words.drop
    globals['drop_2'] = concat.level1.stdlib.shuffle_words.drop_2
    globals['drop_3'] = concat.level1.stdlib.shuffle_words.drop_3
    globals['nip'] = concat.level1.stdlib.shuffle_words.nip
    globals['nip_2'] = concat.level1.stdlib.shuffle_words.nip_2
    globals['dup'] = concat.level1.stdlib.shuffle_words.dup
    globals['dup_2'] = concat.level1.stdlib.shuffle_words.dup_2
    globals['swap'] = concat.level1.stdlib.shuffle_words.swap
    globals['dup_3'] = concat.level1.stdlib.shuffle_words.dup_3
    globals['over'] = concat.level1.stdlib.shuffle_words.over
    globals['over_2'] = concat.level1.stdlib.shuffle_words.over_2
    globals['pick'] = concat.level1.stdlib.shuffle_words.pick
    globals['to_slice'] = concat.level1.stdlib.pyinterop.to_slice
    globals['choose'] = concat.level1.stdlib.execution.choose
    globals['if_then'] = concat.level1.stdlib.execution.if_then
    globals['if_not'] = concat.level1.stdlib.execution.if_not
    globals['case'] = concat.level1.stdlib.execution.case
    globals['loop'] = concat.level1.stdlib.execution.loop


def execute(
    filename: str,
    ast: ast.Module,
    globals: Dict[str, object],
    interactive=False,
    locals: Optional[Dict[str, object]] = None
) -> None:
    """Run transpiled Concat level 1 code."""
    _do_preamble(globals, interactive)
    concat.level0.execute.execute(
        filename, ast, globals, interactive, locals)
