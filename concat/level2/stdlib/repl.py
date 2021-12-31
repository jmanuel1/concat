"""This module provides words that invoke the REPL's mechanisms.

It is like Factor's listener vocabulary."""


import concat
import concat.astutils
import concat.level0.stdlib.importlib
import concat.parse
import concat.level0.transpile
import concat.level1.stdlib.types
import concat.level1.stdlib.repl
import concat.lex
import concat.level1.transpile
import concat.level1.execute
import concat.level2.stdlib.continuations
import sys
from typing import List


sys.modules[__name__].__class__ = concat.level0.stdlib.importlib.Module


def repl(
    stack: List[object], stash: List[object], debug=False, initial_globals={}
) -> None:
    stack.append(
        lambda s, t: concat.level1.stdlib.repl.repl(
            s,
            t,
            debug,
            {
                'return': concat.level2.stdlib.continuations.do_return,
                **initial_globals,
            },
        )
    )
    concat.level2.stdlib.continuations.with_return(stack, stash)
    concat.level1.stdlib.repl.print_exit_message()
