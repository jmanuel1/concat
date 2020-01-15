"""This module takes the transpiler/compiler output and executes it."""
import concat.level0.execute
import concat.level1.stdlib.pyinterop
import concat.level1.stdlib.pyinterop.user_defined_function
from typing import Dict
import ast


def _do_preamble(globals: Dict[str, object]) -> None:
    """Run the level 1 preamble, which adds objects to the given dictionary."""
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
    globals['user_defined_function'] = concat.level1.stdlib.pyinterop.user_defined_function


def execute(
    filename: str,
    ast: ast.Module,
    globals: Dict[str, object]
) -> None:
    """Run transpiled Concat level 1 code."""
    _do_preamble(globals)
    concat.level0.execute.execute(filename, ast, globals)
