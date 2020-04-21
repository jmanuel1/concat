"""This module takes the transpiler/compiler output and executes it."""
import concat.level1.execute
from typing import Dict, Optional
import ast


def _do_preamble(globals: Dict[str, object], interactive=False) -> None:
    """Run the level 2 preamble, which adds objects to the given dictionary.

    The dict is not mutated if interactive is True and the dict has a truthy
    '@@level-2-interactive' key."""
    if interactive and globals.get('@@level-2-interactive', False):
        return
    if interactive:
        globals['@@level-2-interactive'] = True

    # TODO: Replace the level 1 true word with something like this.
    globals['False'] = lambda s, _: s.append(False)


def execute(
    filename: str,
    ast: ast.Module,
    globals: Dict[str, object],
    interactive=False,
    locals: Optional[Dict[str, object]] = None
) -> None:
    """Run transpiled Concat level 1 code."""
    _do_preamble(globals, interactive)
    concat.level1.execute.execute(
        filename, ast, globals, interactive, locals)
