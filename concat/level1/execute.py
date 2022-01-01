"""This module takes the transpiler/compiler output and executes it."""
import concat.level0.execute
import concat.stdlib.pyinterop
import concat.stdlib.pyinterop.user_defined_function as udf
import concat.stdlib.pyinterop.method
import concat.stdlib.pyinterop.coroutine
import concat.stdlib.pyinterop.math
import concat.stdlib.pyinterop.custom_class
import concat.stdlib.pyinterop.instance
import concat.stdlib.compositional
import concat.stdlib.shuffle_words
import concat.stdlib.execution
import concat.stdlib.types
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
    """Run transpiled Concat level 1 code."""
    _do_preamble(globals, interactive)
    concat.level0.execute.execute(
        filename,
        ast,
        globals,
        interactive,
        locals,
        should_log_stacks=should_log_stacks,
    )
